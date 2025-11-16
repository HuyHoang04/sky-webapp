import cv2
import asyncio
import onnxruntime as ort
import logging
import threading
import time

logger = logging.getLogger("drone-client")


# =====================================================================
#                          CameraManager
# =====================================================================

class CameraManager:
    """Optimized for Raspberry Pi Camera Module 3.
       Auto-detects Picamera2 → fallback to OpenCV.
    """

    def __init__(self, width=1280, height=720, fps=30, device=0):
        self.width = width
        self.height = height
        self.fps = fps
        self.device = device

        self._lock = threading.Lock()
        self._frame = None
        self._running = False
        self._thread = None

        # Try Picamera2 first
        try:
            from picamera2 import Picamera2

            self._use_picamera2 = True
            self.picam2 = Picamera2()

            # ----------------------------------------------------------
            # BEST CONFIGURATION FOR CAMERA MODULE 3
            # ----------------------------------------------------------
            config = self.picam2.create_video_configuration(
                main={"size": (self.width, self.height), "format": "XBGR8888"},
                buffer_count=4,
            )
            self.picam2.configure(config)

            # Best autofocus + exposure settings
            self.picam2.set_controls({
                "FrameRate": int(self.fps),
                "AeEnable": True,             # Auto exposure
                "AwbEnable": True,            # Auto white balance
                "AwbMode": 1,                 # Auto
                "ExposureValue": 0.0,
                "AfMode": 2,                  # Continuous autofocus
                "AfSpeed": 1,                 # Fast AF
                "NoiseReductionMode": 2,      # High-quality noise reduction
                "Sharpness": 1.2,             # Best sharpness (no halo)
                "Contrast": 1.0,
                "Saturation": 1.0,
            })

            logger.info(f"[Picamera2] Configured {self.width}x{self.height}@{self.fps}")
            self._backend = "picamera2"

        except Exception:
            # Fallback to OpenCV
            self._use_picamera2 = False
            self.picam2 = None
            self._cap = None
            self._backend = "opencv"
            logger.warning("Picamera2 not available → Using OpenCV backend")

    # -----------------------------------------------------------------
    def start(self):
        if self._running:
            return
        self._running = True

        if not self._use_picamera2:
            self._cap = cv2.VideoCapture(self.device)
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            self._cap.set(cv2.CAP_PROP_FPS, self.fps)

        else:
            self.picam2.start()

        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    # -----------------------------------------------------------------
    def _capture_loop(self):
        delay = 1.0 / max(1, self.fps)

        while self._running:
            frame = None

            try:
                if self._use_picamera2:
                    frame = self.picam2.capture_array()

                else:
                    ret, frame = self._cap.read()
                    if not ret:
                        frame = None

                if frame is not None:
                    with self._lock:
                        self._frame = frame

            except Exception as e:
                logger.error(f"Camera read error: {e}")

            time.sleep(delay)

    # -----------------------------------------------------------------
    def get_frame(self):
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    # -----------------------------------------------------------------
    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

        if self._use_picamera2:
            try:
                self.picam2.stop()
            except:
                pass
        else:
            try:
                self._cap.release()
            except:
                pass

    # Backwards compatibility
    def release(self):
        self.stop()


# =====================================================================
#                          Helper Functions
# =====================================================================

async def setup_camera(width, height, fps):
    cam = CameraManager(width=width, height=height, fps=fps)
    cam.start()
    await asyncio.sleep(0.2)

    if cam.get_frame() is not None:
        logger.info(f"Camera initialized: {width}x{height}@{fps}")
    else:
        logger.warning("Camera started but no frames captured yet")

    return cam


async def load_onnx_model(model_path):
    try:
        session = ort.InferenceSession(model_path)
        logger.info(f"ONNX model loaded: {model_path}")
        return session
    except Exception as e:
        logger.error(f"Failed to load ONNX model: {e}")
        return None
