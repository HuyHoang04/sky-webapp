import asyncio
import cv2
import numpy as np
from aiortc import VideoStreamTrack
from av import VideoFrame
import onnxruntime as ort
import time
import logging
from fractions import Fraction
import threading
from collections import defaultdict


logger = logging.getLogger("drone-client")

# Custom class names for your model
CLASS_NAMES = ["earth_person", "sea_person"]
CLASS_COLORS = {
    "earth_person": (0, 255, 0),    # Green
    "sea_person": (255, 0, 0)        # Blue
}


class FrameBuffer:
    """Buffer to store frames from camera to reduce latency"""
    def __init__(self, max_size=3):
        self.buffer = []
        self.max_size = max_size
        self.lock = threading.Lock()
   
    def add_frame(self, frame):
        with self.lock:
            self.buffer.append(frame)
            if len(self.buffer) > self.max_size:
                self.buffer.pop(0)
   
    def get_latest_frame(self):
        with self.lock:
            if not self.buffer:
                return None
            return self.buffer[-1]


class ObjectDetectionStreamTrack(VideoStreamTrack):
    """
    Optimized video stream track that captures from a camera and performs object detection
    """


    def __init__(self, camera, fps, width, height, ort_session, detection_callback=None):
        super().__init__()
        self.camera = camera
        self.fps = fps
        self.width = width
        self.height = height
        self.counter = 0
        self.last_frame_time = time.time()
        self.ort_session = ort_session
        self.frame_buffer = FrameBuffer()
        self.running = True
        self.active = True
        self.detection_callback = detection_callback  # Callback to send detection data
        
        # Detection statistics
        self.last_detection_data = {
            "earth_person": 0,
            "sea_person": 0,
            "total": 0,
            "timestamp": None
        }
       
        # Start background thread for camera capture
        self.capture_thread = threading.Thread(target=self._capture_frames)
        self.capture_thread.daemon = True
        self.capture_thread.start()
   
    def _capture_frames(self):
        """Background thread to continuously capture frames"""
        while self.running:
            try:
                frame = self.camera.capture_array()  # Picamera2 uses capture_array(), not read()
                # Convert RGB to BGR for cv2 compatibility
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                self.frame_buffer.add_frame(frame)
            except Exception as e:
                # If camera capture fails, wait a bit before trying again
                time.sleep(0.01)
                if self.counter % 30 == 0:  # Log errors occasionally
                    logger.error(f"Camera capture error: {e}")
   
    def is_active(self):
        """Check if the track is active"""
        return self.active
   
    def stop(self):
        """Stop the track and release resources"""
        self.running = False
        self.active = False
        if hasattr(self, 'capture_thread') and self.capture_thread.is_alive():
            self.capture_thread.join(timeout=1.0)


    async def recv(self):
        self.counter += 1


        # Limit frame rate
        now = time.time()
        elapsed = now - self.last_frame_time
        target_elapsed = 1.0 / self.fps
        if elapsed < target_elapsed:
            await asyncio.sleep(target_elapsed - elapsed)
       
        # Get the latest frame from buffer
        frame = self.frame_buffer.get_latest_frame()
       
        # If no frame is available, create a blank one
        if frame is None:
            frame = np.zeros((self.height, self.width, 3), np.uint8)
            cv2.putText(
                frame,
                "Camera Error",
                (self.width // 4, self.height // 2),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (255, 255, 255),
                2
            )
        else:
            # Only perform object detection if ort_session exists and not every frame
            # to reduce CPU usage (e.g., every 3rd frame)
            if self.ort_session is not None and self.counter % 3 == 0:
                frame, detection_data = self.detect_objects(frame)
                
                # Call callback to send detection data via websocket
                if self.detection_callback and detection_data:
                    try:
                        self.detection_callback(detection_data)
                    except Exception as e:
                        logger.error(f"Error in detection callback: {e}")


        # Convert to VideoFrame with proper timing
        video_frame = VideoFrame.from_ndarray(frame, format="bgr24")
        video_frame.pts = self.counter
        video_frame.time_base = Fraction(1, self.fps)
        self.last_frame_time = time.time()


        return video_frame


    def detect_objects(self, frame):
        """
        Perform object detection on the frame using ONNX model
        Returns: (frame_with_boxes, detection_data)
        """
        if self.ort_session is None:
            return frame, None

        try:
            # Store original dimensions
            orig_h, orig_w = frame.shape[:2]
            
            # Resize and preprocess
            input_size = (640, 640)
            input_frame = cv2.resize(frame, input_size)
           
            # Normalize and transpose
            input_frame = input_frame.astype(np.float32) / 255.0
            input_frame = np.transpose(input_frame, (2, 0, 1))
            input_frame = np.expand_dims(input_frame, axis=0)

            # Run inference
            outputs = self.ort_session.run(None, {"images": input_frame})
            
            # Parse YOLOv8 output
            # YOLOv8 output shape: (1, 6, 8400) for 2 classes
            # Format: [x, y, w, h, conf_class0, conf_class1]
            predictions = outputs[0]  # Shape: (1, 6, 8400)
            predictions = np.squeeze(predictions)  # Shape: (6, 8400)
            predictions = predictions.T  # Shape: (8400, 6)
            
            # Extract boxes and scores
            boxes = predictions[:, :4]  # x, y, w, h
            scores_earth = predictions[:, 4]  # confidence for earth_person
            scores_sea = predictions[:, 5]  # confidence for sea_person
            
            # Get class with highest confidence and filter by threshold
            conf_threshold = 0.5
            detections = []
            
            for i in range(len(boxes)):
                if scores_earth[i] > conf_threshold:
                    detections.append({
                        'box': boxes[i],
                        'class': 0,  # earth_person
                        'confidence': scores_earth[i]
                    })
                elif scores_sea[i] > conf_threshold:
                    detections.append({
                        'box': boxes[i],
                        'class': 1,  # sea_person
                        'confidence': scores_sea[i]
                    })
            
            # Apply NMS (Non-Maximum Suppression)
            detections = self.non_max_suppression(detections, iou_threshold=0.45)
            
            # Count detections by class
            counts = {"earth_person": 0, "sea_person": 0}
            
            # Draw boxes on frame
            for det in detections:
                box = det['box']
                class_id = det['class']
                confidence = det['confidence']
                class_name = CLASS_NAMES[class_id]
                color = CLASS_COLORS[class_name]
                
                # Convert from YOLO format (center_x, center_y, w, h) to (x1, y1, x2, y2)
                x_center, y_center, w, h = box
                x1 = int((x_center - w/2) * orig_w / 640)
                y1 = int((y_center - h/2) * orig_h / 640)
                x2 = int((x_center + w/2) * orig_w / 640)
                y2 = int((y_center + h/2) * orig_h / 640)
                
                # Draw bounding box
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                
                # Draw label with confidence
                label = f"{class_name}: {confidence:.2f}"
                label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                label_y = max(y1 - 10, label_size[1])
                cv2.rectangle(frame, (x1, label_y - label_size[1] - 5), 
                            (x1 + label_size[0], label_y + 5), color, -1)
                cv2.putText(frame, label, (x1, label_y), 
                          cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                
                # Update count
                counts[class_name] += 1
            
            # Draw summary on frame
            total_count = counts["earth_person"] + counts["sea_person"]
            summary_text = [
                f"Earth Person: {counts['earth_person']}",
                f"Sea Person: {counts['sea_person']}",
                f"Total: {total_count}"
            ]
            
            y_offset = 30
            for text in summary_text:
                cv2.rectangle(frame, (5, y_offset - 20), (250, y_offset + 5), (0, 0, 0), -1)
                cv2.putText(frame, text, (10, y_offset), 
                          cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                y_offset += 30
            
            # Prepare detection data to send
            detection_data = {
                "earth_person": counts["earth_person"],
                "sea_person": counts["sea_person"],
                "total": total_count,
                "timestamp": time.time(),
                "detections": [{
                    "class": CLASS_NAMES[det['class']],
                    "confidence": float(det['confidence']),
                    "bbox": det['box'].tolist()
                } for det in detections]
            }
            
            self.last_detection_data = detection_data
            
            return frame, detection_data
           
        except Exception as e:
            # Log error but don't spam the log
            if self.counter % 30 == 0:  # Log only every 30 frames
                logger.error(f"Object detection error: {e}")
            return frame, None

    def non_max_suppression(self, detections, iou_threshold=0.45):
        """Apply Non-Maximum Suppression to remove overlapping boxes"""
        if len(detections) == 0:
            return []
        
        # Sort by confidence
        detections = sorted(detections, key=lambda x: x['confidence'], reverse=True)
        
        keep = []
        while len(detections) > 0:
            keep.append(detections[0])
            detections = detections[1:]
            
            # Remove boxes with high IoU
            filtered = []
            for det in detections:
                if self.compute_iou(keep[-1]['box'], det['box']) < iou_threshold:
                    filtered.append(det)
            detections = filtered
        
        return keep
    
    def compute_iou(self, box1, box2):
        """Compute IoU between two boxes in YOLO format (cx, cy, w, h)"""
        # Convert to (x1, y1, x2, y2)
        b1_x1 = box1[0] - box1[2]/2
        b1_y1 = box1[1] - box1[3]/2
        b1_x2 = box1[0] + box1[2]/2
        b1_y2 = box1[1] + box1[3]/2
        
        b2_x1 = box2[0] - box2[2]/2
        b2_y1 = box2[1] - box2[3]/2
        b2_x2 = box2[0] + box2[2]/2
        b2_y2 = box2[1] + box2[3]/2
        
        # Intersection area
        inter_x1 = max(b1_x1, b2_x1)
        inter_y1 = max(b1_y1, b2_y1)
        inter_x2 = min(b1_x2, b2_x2)
        inter_y2 = min(b1_y2, b2_y2)
        
        if inter_x2 < inter_x1 or inter_y2 < inter_y1:
            return 0.0
        
        inter_area = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
        
        # Union area
        b1_area = box1[2] * box1[3]
        b2_area = box2[2] * box2[3]
        union_area = b1_area + b2_area - inter_area
        
        return inter_area / union_area if union_area > 0 else 0.0
