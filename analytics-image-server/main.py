"""
SkyAid Image Analytics Server
AI-powered image analysis service using YOLO for object detection

Copyright (c) 2025 HuyHoang04
Licensed under MIT License - see LICENSE file for details
"""

import io
import logging
import time
import os
from typing import Optional

import cv2
import dotenv
import numpy as np
import requests
from fastapi import FastAPI, UploadFile, File, Form, Body
from fastapi.responses import JSONResponse
from ultralytics import YOLO
import uvicorn

# Load environment variables
dotenv.load_dotenv()

# ============= CLOUDINARY =============
import tempfile
try:
    import cloudinary
    import cloudinary.uploader
    _CLOUDINARY_AVAILABLE = True
except Exception:
    cloudinary = None
    _CLOUDINARY_AVAILABLE = False


# --- Cloudinary Config ---
if _CLOUDINARY_AVAILABLE:
    try:
        cloudinary.config(
            cloud_name=dotenv.get_key("CLOUD_NAME"),
            api_key=dotenv.get_key("CLOUD_API_KEY"),
            api_secret=dotenv.get_key("CLOUD_API_SECRET"),
            secure=True,
        )
    except Exception:
        _CLOUDINARY_AVAILABLE = False


# ========= UPLOAD SINGLE FILE TO CLOUDINARY, PRINT LOG =========
def upload_path_to_cloudinary(path: str, filename: str):
    if not _CLOUDINARY_AVAILABLE:
        print("Cloudinary module không khả dụng.")
        return None
    try:
        result = cloudinary.uploader.upload(
            path,
            folder="image_result", 
            public_id=filename,
            overwrite=True
        )
        print(f"Upload thành công: {result}")
        return result.get("secure_url") or result.get("url")
    except Exception as e:
        print(f"Lỗi upload lần 1: {e}")
        try:
            result = cloudinary.uploader.upload(
                path,
                folder="image_result",
                public_id=filename,
                overwrite=True
            )
            print(f"Upload lại thành công: {result}")
            return result.get("secure_url") or result.get("url")
        except Exception as e2:
            print(f"Lỗi upload lần 2: {e2}")
            return None


# ============= LOGGING =============
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cloud_ai")

app = FastAPI(title="Cloud AI - YOLOv11s Inference")


# ============= LOAD YOLO MODEL =============
try:
    model = YOLO(
        r"./best.pt"
    )
    logger.info("Loaded YOLOv11s model successfully.")
except Exception as e:
    logger.exception("Failed to load YOLO model.")
    raise e


# ============= IMAGE DECODERS =============
def read_image_from_bytes(image_bytes: bytes):
    arr = np.frombuffer(image_bytes, np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def read_image_from_url(url: str):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, timeout=15, headers=headers, allow_redirects=True)
    except Exception:
        return None

    if r.status_code != 200:
        return None

    ct = r.headers.get("Content-Type", "")
    if "image" not in ct and not url.lower().endswith(
        (".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp")
    ):
        return None

    arr = np.frombuffer(r.content, np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


# ============= HELPER FUNCTION: Process Image =============
def process_image_analysis(img, person_type="earth"):
    """
    Process image with YOLO detection and annotation
    Returns: (annotated_img, earth_count, sea_count, total_count)
    """
    # YOLO Inference
    try:
        results = model(img, verbose=False)[0]
    except Exception:
        logger.exception("Inference failed")
        return None, 0, 0, 0

    # Draw BBOX and count by type
    earth_count = 0
    sea_count = 0
    
    for box in results.boxes:
        cls_id = int(box.cls[0])
        if cls_id != 0:   # chỉ detect class 0 (person)
            continue

        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
        conf = float(box.conf[0]) if hasattr(box, "conf") else 0.0

        # Determine label based on person_type (can be enhanced with actual classification)
        if person_type.lower() == "sea":
            label_text = "sea_person"
            sea_count += 1
            color = (255, 0, 0)  # Blue for sea
        else:
            label_text = "earth_person"
            earth_count += 1
            color = (0, 255, 0)  # Green for earth

        # Draw bbox & label
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
        cv2.putText(
            img, label_text, (x1, max(0, y1 - 5)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2
        )

    total_count = earth_count + sea_count
    return img, earth_count, sea_count, total_count


# ============= BACKGROUND TASK: Process & Callback =============
import asyncio
from concurrent.futures import ThreadPoolExecutor

executor = ThreadPoolExecutor(max_workers=4)

# Webhook URL configuration
WEBHOOK_URL = os.getenv('WEBHOOK_URL', 'http://localhost:5000/api/capture/webhook')

def process_and_callback(image_url: str, capture_id: int):
    """
    Background task: Download → Analyze → Upload → POST to webhook
    """
    try:
        logger.info(f"[AI BACKGROUND] Processing capture_id={capture_id}")
        logger.info(f"[AI BACKGROUND] Webhook URL: {WEBHOOK_URL}")
        
        # Download image
        img = read_image_from_url(image_url)
        if img is None:
            logger.error(f"[AI BACKGROUND]  Failed to download image")
            # Call webhook with error
            requests.post(WEBHOOK_URL, json={
                "capture_id": capture_id,
                "success": False,
                "error": "Failed to download image"
            }, timeout=10)
            return
        
        logger.info(f"[AI BACKGROUND] Image loaded: {img.shape}")
        
        # YOLO analysis
        annotated_img, earth_count, sea_count, total_count = process_image_analysis(img, person_type="earth")
        
        if annotated_img is None:
            logger.error(f"[AI BACKGROUND] Inference failed")
            requests.post(WEBHOOK_URL, json={
                "capture_id": capture_id,
                "success": False,
                "error": "Model inference failed"
            }, timeout=10)
            return
        
        logger.info(f"[AI BACKGROUND]  Detected: Total={total_count}, Earth={earth_count}, Sea={sea_count}")
        
        # Save & upload
        os.makedirs("output", exist_ok=True)
        image_id = int(time.time() * 1000)
        save_path = f"output/analyzed_{image_id}.jpg"
        cv2.imwrite(save_path, annotated_img)
        
        cloud_url = upload_path_to_cloudinary(save_path, filename=f"analyzed_{image_id}")
        
        if not cloud_url:
            logger.error("[AI BACKGROUND]  Upload failed")
            requests.post(WEBHOOK_URL, json={
                "capture_id": capture_id,
                "success": False,
                "error": "Failed to upload analyzed image"
            }, timeout=10)
            return
        
        logger.info(f"[AI BACKGROUND] ☁️ Uploaded: {cloud_url}")
        
        # Call webhook with results
        result_payload = {
            "capture_id": capture_id,
            "success": True,
            "analyzed_image_url": cloud_url,
            "person_count": total_count,
            "earth_person_count": earth_count,
            "sea_person_count": sea_count
        }
        
        logger.info(f"[AI BACKGROUND]  Calling webhook: {WEBHOOK_URL}")
        response = requests.post(WEBHOOK_URL, json=result_payload, timeout=10)
        logger.info(f"[AI BACKGROUND]  Webhook response: {response.status_code}")
        
    except Exception as e:
        logger.exception(f"[AI BACKGROUND]  Error: {str(e)}")
        try:
            requests.post(WEBHOOK_URL, json={
                "capture_id": capture_id,
                "success": False,
                "error": str(e)
            }, timeout=10)
        except:
            pass


# ============= NEW API: /analyze (for capture feature) =============
@app.post("/analyze")
async def analyze_image(payload: dict = Body(...)):
    """
    Analyze captured image from drone (ASYNC with webhook callback)
    
    Expected JSON: 
    {
        "image_url": "cloudinary_url",
        "capture_id": 123
    }
    
    Returns 200 OK immediately, processes in background, then POSTs results to hardcoded WEBHOOK_URL
    """
    try:
        image_url = payload.get("image_url")
        capture_id = payload.get("capture_id")
        
        if not image_url:
            return JSONResponse({"error": "image_url is required"}, status_code=400)
        if not capture_id:
            return JSONResponse({"error": "capture_id is required"}, status_code=400)
        
        logger.info(f"[AI ANALYZE] 📥 Received request for capture_id={capture_id}")
        logger.info(f"[AI ANALYZE] 📸 Image URL: {image_url}")
        
        # Start background task
        loop = asyncio.get_event_loop()
        loop.run_in_executor(executor, process_and_callback, image_url, capture_id)
        
        logger.info(f"[AI ANALYZE] ✅ Accepted - processing in background")
        
        # Return 200 OK immediately
        return JSONResponse({
            "status": "accepted",
            "message": "Image analysis started in background",
            "capture_id": capture_id
        }, status_code=200)
        
    except Exception as e:
        logger.exception(f"[AI ANALYZE]  Error: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)


# ============= MAIN API: /result =============
@app.post("/result")
async def result(
    file: Optional[UploadFile] = File(None),
    image_url: Optional[str] = Form(None),
    device_id: Optional[str] = Form(None),
    timestamp: Optional[str] = Form(None),
    person_type: Optional[str] = Form(None),
):
    """Xử lý 1 ảnh → detect YOLO → annotate → lưu local → upload Cloudinary"""

    # --------- INPUT HANDLING ---------
    try:
        if file is not None:
            bytes_img = await file.read()
            img = read_image_from_bytes(bytes_img)
        elif image_url:
            img = read_image_from_url(image_url)
        else:
            return JSONResponse({"error": "No image provided"}, status_code=400)

        if img is None:
            return JSONResponse({"error": "Unable to decode image"}, status_code=400)

    except Exception:
        return JSONResponse({"error": "Unable to decode image"}, status_code=400)

    # --------- YOLO INFERENCE & ANNOTATION ---------
    annotated_img, earth_count, sea_count, total_count = process_image_analysis(
        img, 
        person_type=person_type or "earth"
    )
    
    if annotated_img is None:
        return JSONResponse({"error": "Model inference failed"}, status_code=500)

    # --------- SAVE LOCAL OUTPUT ---------
    os.makedirs("output", exist_ok=True)
    image_id = int(time.time() * 1000)
    save_path = f"output/annotated_{image_id}.jpg"
    cv2.imwrite(save_path, annotated_img)

    # --------- UPLOAD TO CLOUDINARY ---------
    cloud_url = upload_path_to_cloudinary(
        save_path,
        filename=f"annotated_{image_id}"
    )

    # --------- RETURN RESPONSE ---------
    return JSONResponse({
        "total_person": total_count,
        "earth_person_count": earth_count,
        "sea_person_count": sea_count,
        "cloud_url": cloud_url,
        "device_id": device_id,
        "timestamp": timestamp,
    })


# ============= MAIN ENTRY =============
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, log_level="info")
