import cv2
import asyncio
import onnxruntime as ort
import logging

logger = logging.getLogger("drone-client")

async def setup_camera(width, height, fps):
    """Set up the camera with specified parameters"""
    print(f"Attempting to open camera with index 0...")
    camera = cv2.VideoCapture(0)

    if not camera.isOpened():
        print("Camera index 0 failed, trying index 1...")
        camera = cv2.VideoCapture(1)

    if not camera.isOpened():
        print("Camera index 1 failed, trying index -1...")
        camera = cv2.VideoCapture(-1)

    if not camera.isOpened():
        logger.error("Failed to open any camera")
        return None

    # Set camera properties
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    camera.set(cv2.CAP_PROP_FPS, fps)

    # Test reading a frame
    ret, test_frame = camera.read()
    if ret:
        print(f"Camera opened successfully! Frame shape: {test_frame.shape}")
        logger.info(f"Camera initialized: {width}x{height} @ {fps}fps")
    else:
        print("Camera opened but failed to read test frame")
        camera.release()
        return None

    return camera


async def load_onnx_model(model_path):
    """Load ONNX model for object detection"""
    try:
        session = ort.InferenceSession(model_path)
        logger.info(f"ONNX model loaded from {model_path}")
        return session
    except Exception as e:
        logger.error(f"Failed to load ONNX model: {e}")
        return None
