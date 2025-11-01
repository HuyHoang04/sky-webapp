import cv2
import asyncio
import onnxruntime as ort
import logging
from picamera2 import Picamera2


logger = logging.getLogger("drone-client")


async def setup_camera(width, height, fps):
    """Set up the camera with specified parameters using Picamera2 for CSI camera on Raspberry Pi"""
    try:
        picam2 = Picamera2()
        picam2.preview_configuration.main.size = (width, height)
        picam2.preview_configuration.main.format = "BGR888"
        picam2.configure("preview")
        picam2.start()
       
        # Test reading a frame
        test_frame = picam2.capture_array()
        if test_frame is not None:
            print(f"CSI Camera opened successfully! Frame shape: {test_frame.shape}")
            logger.info(f"CSI Camera initialized: {width}x{height}")
            return picam2  # Trả về Picamera2 object
        else:
            print("CSI Camera opened but failed to read test frame")
            picam2.stop()
            return None
    except Exception as e:
        logger.error(f"Failed to setup CSI camera with Picamera2: {e}")
        return None


async def load_onnx_model(model_path):
    """Load ONNX model for object detection"""
    try:
        session = ort.InferenceSession(model_path)
        logger.info(f"ONNX model loaded from {model_path}")
        return session
    except Exception as e:
        logger.error(f"Failed to load ONNX model: {e}")
        return None
