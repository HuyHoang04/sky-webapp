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


logger = logging.getLogger("drone-client")


# The camera capture is now handled by CameraManager in drone-app/camera_utils.py
# Video stream will call camera.get_frame() to retrieve the latest frame.


# Class names and colors for bounding boxes
CLASS_NAMES = {0: 'earth_person', 1: 'sea_person'}
CLASS_COLORS = {0: (0, 255, 0), 1: (0, 165, 255)}  # Green for earth_person, Orange for sea_person


class ObjectDetectionStreamTrack(VideoStreamTrack):
    """
    Optimized video stream track that captures from a camera and performs object detection
    """


    def __init__(self, camera, fps, width, height, ort_session):
        super().__init__()
        self.camera = camera
        self.fps = fps
        self.width = width
        self.height = height
        self.counter = 0
        self.last_frame_time = time.time()
        self.ort_session = ort_session
        self.running = True
        self.active = True
        self.cached_detections = []
        self.detection_update_interval = 3  # Update detections every N frames for smoothness
   
    def _capture_frames(self):
        """Background thread to continuously capture frames"""
        while self.running:
            try:
                # Legacy: capture loop moved to CameraManager. Keep method for compatibility but not used.
                frame = None
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
       
        # Get the latest frame from the shared camera manager
        try:
            # camera_manager.get_frame() should return a BGR ndarray or None
            frame = None
            if hasattr(self.camera, 'get_frame'):
                frame = self.camera.get_frame()
            else:
                # Fallback to legacy API (capture_array)
                frame = self.camera.capture_array()
                # If capture_array returns RGB, convert to BGR conservatively
                try:
                    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Error getting frame from camera: {e}")
            frame = None
       
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
            # Defensive normalization: ensure frame has 3 channels in BGR order
            try:
                if isinstance(frame, np.ndarray):
                    if frame.ndim == 2:
                        # grayscale -> BGR
                        frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
                    elif frame.ndim == 3 and frame.shape[2] == 4:
                        # 4-channel image (e.g., RGBA/BGRA) -> try to convert to BGR
                        try:
                            frame = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)
                        except Exception:
                            try:
                                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                            except Exception:
                                # Fallback: drop alpha
                                frame = frame[:, :, :3]
            except Exception as e:
                logger.debug(f"Frame normalization error: {e}")
            # Update detections periodically for efficiency
            if self.ort_session is not None and self.counter % self.detection_update_interval == 0:
                self.cached_detections = self.detect_objects(frame)
            
            # Draw bounding boxes on every frame using cached detections
            if self.cached_detections:
                frame = self.draw_bboxes(frame, self.cached_detections)


        # Convert to VideoFrame with proper timing
        # Ensure the ndarray has shape (H, W, 3) and dtype uint8 before converting
        try:
            if not (isinstance(frame, np.ndarray) and frame.ndim == 3 and frame.shape[2] == 3):
                # As a last resort, convert or create a blank frame
                frame = cv2.resize(np.zeros((self.height, self.width, 3), np.uint8), (self.width, self.height))
            video_frame = VideoFrame.from_ndarray(frame, format="bgr24")
        except Exception as e:
            logger.error(f"Failed to convert ndarray to VideoFrame: {e}")
            # Fallback to a blank frame
            fallback = np.zeros((self.height, self.width, 3), np.uint8)
            video_frame = VideoFrame.from_ndarray(fallback, format="bgr24")
        video_frame.pts = self.counter
        video_frame.time_base = Fraction(1, self.fps)
        self.last_frame_time = time.time()


        return video_frame


    def detect_objects(self, frame):
        """
        Perform object detection on the frame using ONNX model
        Returns list of detections: [{'bbox':[x1,y1,x2,y2], 'class':int, 'score':float}, ...]
        """
        if self.ort_session is None:
            return []

        try:
            input_size = (640, 640)
            input_frame = cv2.resize(frame, input_size)
            input_frame = input_frame.astype(np.float32) / 255.0
            input_frame = np.transpose(input_frame, (2, 0, 1))
            input_frame = np.expand_dims(input_frame, axis=0)

            outputs = self.ort_session.run(None, {self.ort_session.get_inputs()[0].name: input_frame})
            
            # Parse detections using helper from main.py
            h, w = frame.shape[:2]
            from main import parse_onnx_detections
            detections = parse_onnx_detections(outputs, input_size=(640, 640), orig_size=(w, h))
            return detections
           
        except Exception as e:
            if self.counter % 30 == 0:
                logger.error(f"Object detection error: {e}")
            return []

    def draw_bboxes(self, frame, detections):
        """
        Draw bounding boxes on frame for detected objects
        """
        for det in detections:
            bbox = det['bbox']
            cls = det.get('class', 0)
            score = det.get('score', 0.0)
            
            x1, y1, x2, y2 = map(int, bbox)
            color = CLASS_COLORS.get(cls, (255, 255, 255))
            label = CLASS_NAMES.get(cls, f'class_{cls}')
            
            # Draw rectangle
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            
            # Draw label background
            label_text = f"{label}: {score:.2f}"
            (tw, th), _ = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(frame, (x1, y1 - th - 4), (x1 + tw, y1), color, -1)
            
            # Draw label text
            cv2.putText(frame, label_text, (x1, y1 - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        return frame
