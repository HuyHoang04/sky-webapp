"""
Detection utilities for periodic reporting
Independent from WebRTC - uses direct camera access
"""
import asyncio
import cv2
import base64
import logging
from datetime import datetime
import numpy as np
from collections import defaultdict

logger = logging.getLogger("drone-client")

# Global control variables
periodic_report_enabled = True
report_interval = 60  # Default 1 minute (60 seconds)
detection_camera = None  # Independent camera for detection
detection_ort_session = None  # ONNX model session
latest_detection_data = {
    "earth_person": 0,
    "sea_person": 0,
    "total": 0,
    "timestamp": None,
    "detections": []
}

# Detection constants
CLASS_NAMES = ["earth_person", "sea_person"]
CONFIDENCE_THRESHOLD = 0.5
NMS_IOU_THRESHOLD = 0.45


def set_detection_camera(camera, ort_session):
    """Set the camera and model for detection (fallback, independent from WebRTC)"""
    global detection_camera, detection_ort_session
    detection_camera = camera
    detection_ort_session = ort_session
    logger.info("Detection camera and model set (independent from WebRTC)")


def get_latest_detection():
    """Get the latest detection data"""
    return latest_detection_data.copy()


def set_report_interval(seconds):
    """Set the interval for periodic reports"""
    global report_interval
    if seconds < 60:  # Minimum 1 minute
        seconds = 60
    report_interval = seconds
    logger.info(f"Report interval set to {seconds} seconds ({seconds/60} minutes)")


def enable_periodic_report():
    """Enable periodic reporting"""
    global periodic_report_enabled
    periodic_report_enabled = True
    logger.info("Periodic reporting enabled")


def disable_periodic_report():
    """Disable periodic reporting"""
    global periodic_report_enabled
    periodic_report_enabled = False
    logger.info("Periodic reporting disabled")


def is_periodic_report_enabled():
    """Check if periodic reporting is enabled"""
    return periodic_report_enabled


def get_report_interval():
    """Get current report interval"""
    return report_interval


def compute_iou(box1, box2):
    """Compute IoU between two boxes [x1, y1, x2, y2]"""
    x1_inter = max(box1[0], box2[0])
    y1_inter = max(box1[1], box2[1])
    x2_inter = min(box1[2], box2[2])
    y2_inter = min(box1[3], box2[3])
    
    inter_area = max(0, x2_inter - x1_inter) * max(0, y2_inter - y1_inter)
    
    box1_area = (box1[2] - box1[0]) * (box1[3] - box1[1])
    box2_area = (box2[2] - box2[0]) * (box2[3] - box2[1])
    union_area = box1_area + box2_area - inter_area
    
    return inter_area / union_area if union_area > 0 else 0


def detect_objects_from_camera():
    """
    Capture frame from camera and run detection
    Returns: (frame, detection_data) or (None, None) if failed
    """
    global detection_camera, detection_ort_session, latest_detection_data
    
    if detection_camera is None or detection_ort_session is None:
        return None, None
    
    try:
        # Capture frame from camera
        frame = detection_camera.capture_array()
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        
        if frame is None:
            return None, None
        
        # Run detection
        img = frame.copy()
        original_height, original_width = img.shape[:2]
        
        # Preprocess for ONNX model (YOLOv8 expects 640x640)
        img_resized = cv2.resize(img, (640, 640))
        img_rgb = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)
        img_normalized = img_rgb.astype(np.float32) / 255.0
        img_transposed = np.transpose(img_normalized, (2, 0, 1))
        img_batch = np.expand_dims(img_transposed, axis=0)
        
        # Run inference
        input_name = detection_ort_session.get_inputs()[0].name
        outputs = detection_ort_session.run(None, {input_name: img_batch})
        output = outputs[0]
        
        # Parse YOLOv8 output [1, 6, 8400]
        output = output[0]  # Remove batch dimension -> [6, 8400]
        num_detections = output.shape[1]
        
        # Count detections per class
        class_counts = defaultdict(int)
        all_detections = []
        
        for i in range(num_detections):
            detection = output[:, i]
            x_center, y_center, width, height = detection[:4]
            class_probs = detection[4:]
            
            class_id = np.argmax(class_probs)
            confidence = class_probs[class_id]
            
            if confidence >= CONFIDENCE_THRESHOLD:
                # Convert to original image coordinates
                x_center *= original_width / 640
                y_center *= original_height / 640
                width *= original_width / 640
                height *= original_height / 640
                
                x1 = int(x_center - width / 2)
                y1 = int(y_center - height / 2)
                x2 = int(x_center + width / 2)
                y2 = int(y_center + height / 2)
                
                all_detections.append({
                    'box': [x1, y1, x2, y2],
                    'confidence': float(confidence),
                    'class_id': int(class_id),
                    'class_name': CLASS_NAMES[class_id]
                })
        
        # Apply NMS
        final_detections = []
        all_detections.sort(key=lambda x: x['confidence'], reverse=True)
        
        while all_detections:
            best = all_detections.pop(0)
            final_detections.append(best)
            class_counts[best['class_name']] += 1
            
            # Remove overlapping boxes
            all_detections = [
                det for det in all_detections
                if compute_iou(best['box'], det['box']) < NMS_IOU_THRESHOLD
            ]
        
        # Draw boxes on frame (improved style)
        for det in final_detections:
            x1, y1, x2, y2 = det['box']
            class_name = det['class_name']
            confidence = det['confidence']
            
            # Colors matching WebRTC stream
            color = (0, 255, 0) if class_name == 'earth_person' else (255, 0, 0)
            
            # Draw bounding box with thicker line
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            
            # Draw label with background
            label = f"{class_name}: {confidence:.2f}"
            label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            label_y = max(y1 - 10, label_size[1])
            
            # Draw filled rectangle for label background
            cv2.rectangle(frame, 
                         (x1, label_y - label_size[1] - 5), 
                         (x1 + label_size[0], label_y + 5), 
                         color, -1)
            
            # Draw text on top of background
            cv2.putText(frame, label, (x1, label_y), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        # Draw summary overlay (top-left corner)
        y_offset = 30
        for text_line in [
            f"Earth Person: {class_counts.get('earth_person', 0)}",
            f"Sea Person: {class_counts.get('sea_person', 0)}",
            f"Total: {sum(class_counts.values())}"
        ]:
            # Draw background
            text_size, _ = cv2.getTextSize(text_line, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
            cv2.rectangle(frame, (5, y_offset - 20), 
                         (text_size[0] + 15, y_offset + 5), 
                         (0, 0, 0), -1)
            # Draw text
            cv2.putText(frame, text_line, (10, y_offset), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
            y_offset += 30
        
        # Update latest detection data
        latest_detection_data = {
            'earth_person': class_counts.get('earth_person', 0),
            'sea_person': class_counts.get('sea_person', 0),
            'total': sum(class_counts.values()),
            'timestamp': datetime.now().isoformat(),
            'detections': final_detections
        }
        
        return frame, latest_detection_data
        
    except Exception as e:
        logger.error(f"Error in detect_objects_from_camera: {e}", exc_info=True)
        return None, None


async def periodic_report_task(sio, device_id, device_name, video_track=None, interval=None):
    """
    Periodic task to capture snapshot and send detection report
    Uses independent camera, not dependent on WebRTC
    Args:
        sio: Socket.IO client instance
        device_id: Device ID
        device_name: Device name
        video_track: Video track instance (optional, for backwards compatibility)
        interval: Report interval in seconds (default: use global report_interval)
    """
    global report_interval, periodic_report_enabled
    
    # Use global interval if not specified
    if interval is None:
        interval = report_interval
    
    logger.info(f"Started periodic detection report task (interval: {interval}s, enabled: {periodic_report_enabled})")
    
    while True:
        try:
            # Check if periodic reporting is enabled
            if not periodic_report_enabled:
                # If disabled, sleep for a short time and check again
                await asyncio.sleep(5)
                continue
            
            # Use current global interval
            current_interval = report_interval
            await asyncio.sleep(current_interval)
            
            # Capture frame and run detection
            frame, detection_data = detect_objects_from_camera()
            
            if frame is None or detection_data is None:
                logger.warning("Failed to capture frame or run detection for report")
                continue
            
            # Encode frame to JPEG
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            image_base64 = base64.b64encode(buffer).decode('utf-8')
            
            # Prepare report data
            report_data = {
                'device_id': device_id,
                'device_name': device_name,
                'detection_data': {
                    'earth_person': detection_data.get('earth_person', 0),
                    'sea_person': detection_data.get('sea_person', 0),
                    'total': detection_data.get('total', 0),
                    'timestamp': datetime.now().isoformat()
                },
                'image': image_base64
            }
            
            # Send report to server
            await sio.emit('detection_snapshot', report_data)
            
            logger.info(f"Sent detection report: Earth={detection_data.get('earth_person', 0)}, "
                       f"Sea={detection_data.get('sea_person', 0)}, "
                       f"Total={detection_data.get('total', 0)}, "
                       f"Image size: {len(image_base64)} bytes")
            
        except asyncio.CancelledError:
            logger.info("Periodic report task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in periodic report task: {e}", exc_info=True)
            # Continue running despite errors
            await asyncio.sleep(10)


async def on_demand_report(sio, device_id, device_name, video_track=None):
    """
    Capture and send detection report on demand
    Uses independent camera, not dependent on WebRTC
    Args:
        video_track: Optional, for backwards compatibility (ignored)
    """
    try:
        # Capture frame and run detection
        frame, detection_data = detect_objects_from_camera()
        
        if frame is None or detection_data is None:
            logger.warning("Failed to capture frame or run detection for on-demand report")
            return False
        
        # Encode frame to JPEG
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        image_base64 = base64.b64encode(buffer).decode('utf-8')
        
        # Prepare report data
        report_data = {
            'device_id': device_id,
            'device_name': device_name,
            'detection_data': {
                'earth_person': detection_data.get('earth_person', 0),
                'sea_person': detection_data.get('sea_person', 0),
                'total': detection_data.get('total', 0),
                'timestamp': datetime.now().isoformat()
            },
            'image': image_base64
        }
        
        # Send report to server
        await sio.emit('detection_snapshot', report_data)
        
        logger.info(f"Sent on-demand detection report: Earth={detection_data.get('earth_person', 0)}, "
                   f"Sea={detection_data.get('sea_person', 0)}, "
                   f"Total={detection_data.get('total', 0)}")
        return True
        
    except Exception as e:
        logger.error(f"Error in on-demand report: {e}", exc_info=True)
        return False
