import asyncio
import logging
from aiohttp import web
import cv2
import numpy as np

logger = logging.getLogger("drone-client")


async def start_capture_server(webcam, ort_session=None, host='0.0.0.0', port=8080, get_latest_gps=None, cloud_url=None, device_id='drone-camera'):
    """Start a simple HTTP server that serves /capture endpoint.

    Query params:
      - detect=true|1 : run ONNX detection before returning image (overlay only)
      - quality=0-100 : JPEG quality (default 95 for high quality)

    This function runs until cancelled. Call with asyncio.create_task(...).
    """

    app = web.Application()

    async def handle_capture(request):
        detect = request.query.get('detect', 'false').lower() in ('1', 'true', 'yes')
        quality = int(request.query.get('quality', '95'))  # High quality by default
        camera = webcam
        frame = None

        # Try new CameraManager API first
        try:
            if hasattr(camera, 'get_frame'):
                frame = camera.get_frame()
            else:
                # Fallback to older API
                if hasattr(camera, 'capture_array'):
                    frame = camera.capture_array()
                    try:
                        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"Error reading frame from camera: {e}")
            frame = None

        if frame is None:
            return web.Response(status=503, text='No frame available')

        if detect and ort_session is not None:
            try:
                input_size = (640, 640)
                input_frame = cv2.resize(frame, input_size)
                input_frame = input_frame.astype(np.float32) / 255.0
                input_frame = np.transpose(input_frame, (2, 0, 1))
                input_frame = np.expand_dims(input_frame, axis=0)
                _ = ort_session.run(None, {"images": input_frame})
                cv2.putText(frame, "Detection OK", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            except Exception as e:
                logger.error(f"ONNX detection error: {e}")

        # Encode as high-quality JPEG
        try:
            encode_params = [cv2.IMWRITE_JPEG_QUALITY, quality]
            ret, jpg = cv2.imencode('.jpg', frame, encode_params)
            if not ret:
                raise RuntimeError('JPEG encode failed')
            return web.Response(body=jpg.tobytes(), content_type='image/jpeg')
        except Exception as e:
            logger.error(f"Failed to encode frame: {e}")
            return web.Response(status=500, text='Failed to encode frame')

    app.router.add_get('/capture', handle_capture)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()

    logger.info(f"Capture API running on http://{host}:{port}/capture")

    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        logger.info('Shutting down capture API')
        await runner.cleanup()
        raise
