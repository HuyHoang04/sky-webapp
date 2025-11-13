import cv2
import asyncio
import onnxruntime as ort
import logging
import threading
import time
from collections import deque


logger = logging.getLogger("drone-client")


class CameraManager:
    """Singleton-like camera manager that runs one background capture thread
    and provides thread-safe access to the latest frame.

    API:
      - start(): start capture thread
      - stop()/release(): stop capture thread and release device
      - get_frame(): return the last captured frame (BGR ndarray) or None
    """

    def __init__(self, width=640, height=480, fps=15, device=0):
        self.width = width
        self.height = height
        self.fps = fps
        self.device = device

        self._lock = threading.Lock()
        self._frame = None
        self._running = False
        self._thread = None

        # Try to use Picamera2 when available (Raspberry Pi), otherwise fallback to OpenCV
        try:
            from picamera2 import Picamera2

            self._use_picamera2 = True
            self._picam2 = Picamera2()
            # configure preview size/format but don't assume advanced configs
            try:
                self._picam2.preview_configuration.main.size = (self.width, self.height)
                self._picam2.preview_configuration.main.format = "BGR888"
                self._picam2.configure("preview")
            except Exception:
                # Some versions expose a different API; ignore if not available
                pass
            self._backend = "picamera2"
        except Exception:
            # Fallback to OpenCV VideoCapture
            self._use_picamera2 = False
            self._picam2 = None
            self._cap = None
            self._backend = "opencv"

    def start(self):
        if self._running:
            return
        self._running = True
        # Open backend if necessary
        if not self._use_picamera2:
            self._cap = cv2.VideoCapture(self.device)
            # Try to set width/height
            try:
                self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                self._cap.set(cv2.CAP_PROP_FPS, self.fps)
            except Exception:
                pass
        else:
            try:
                self._picam2.start()
            except Exception as e:
                logger.debug(f"Picamera2 start error: {e}")

        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def _capture_loop(self):
        target_delay = 1.0 / max(1, self.fps)
        while self._running:
            frame = None
            try:
                if self._use_picamera2 and self._picam2 is not None:
                    frame = self._picam2.capture_array()
                elif not self._use_picamera2 and self._cap is not None:
                    ret, frame = self._cap.read()
                    if not ret:
                        frame = None
                # Ensure frame is the requested size
                if frame is not None:
                    # If RGB, try to detect and convert to BGR: assume colors are already BGR for common backends
                    # Resize if needed
                    h, w = frame.shape[:2]
                    if (w, h) != (self.width, self.height):
                        frame = cv2.resize(frame, (self.width, self.height))
                    with self._lock:
                        self._frame = frame
            except Exception as e:
                logger.error(f"Camera capture error: {e}")

            time.sleep(target_delay)

    def get_frame(self):
        with self._lock:
            if self._frame is None:
                return None
            # Return a copy to avoid accidental modification by caller
            return self._frame.copy()

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        # Release backend
        if not self._use_picamera2 and getattr(self, '_cap', None) is not None:
            try:
                self._cap.release()
            except Exception:
                pass
        if self._use_picamera2 and getattr(self, '_picam2', None) is not None:
            try:
                self._picam2.stop()
            except Exception:
                pass

    # Backwards-compatible alias
    def release(self):
        self.stop()


async def setup_camera(width, height, fps):
    """Create and start a CameraManager and return it. Compatible with existing code that
    awaits setup_camera and expects an object with capture/release style methods.
    """
    cam = CameraManager(width=width, height=height, fps=fps)
    cam.start()
    # Wait a short time for first frame
    await asyncio.sleep(0.1)
    if cam.get_frame() is not None:
        logger.info(f"CameraManager initialized: {width}x{height}@{fps}")
        return cam
    else:
        logger.warning("CameraManager started but no frames available yet")
        return cam


async def load_onnx_model(model_path):
    """Load ONNX model for object detection"""
    try:
        session = ort.InferenceSession(model_path)
        logger.info(f"ONNX model loaded from {model_path}")
        return session
    except Exception as e:
        logger.error(f"Failed to load ONNX model: {e}")
        return None
