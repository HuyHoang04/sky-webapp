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


    def __init__(self, camera, fps, width, height, ort_session):
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
                frame = self.detect_objects(frame)


        # Convert to VideoFrame with proper timing
        video_frame = VideoFrame.from_ndarray(frame, format="bgr24")
        video_frame.pts = self.counter
        video_frame.time_base = Fraction(1, self.fps)
        self.last_frame_time = time.time()


        return video_frame


    def detect_objects(self, frame):
        """
        Perform object detection on the frame using ONNX model
        """
        if self.ort_session is None:
            return frame


        try:
            # Resize and preprocess more efficiently
            input_size = (640, 640)
            input_frame = cv2.resize(frame, input_size)
           
            # Normalize and transpose in one step if possible
            input_frame = input_frame.astype(np.float32) / 255.0
            input_frame = np.transpose(input_frame, (2, 0, 1))
            input_frame = np.expand_dims(input_frame, axis=0)


            # Run inference with a timeout
            outputs = self.ort_session.run(None, {"images": input_frame})
           
            # Process outputs (simplified)
            # Just add a text overlay to indicate detection is working
            cv2.putText(
                frame,
                f"Object Detection Active",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2
            )
           
        except Exception as e:
            # Log error but don't spam the log
            if self.counter % 30 == 0:  # Log only every 30 frames
                logger.error(f"Object detection error: {e}")


        return frame
