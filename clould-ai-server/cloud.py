import io
import logging
import time
import os
from typing import Optional

import cv2
import numpy as np
import requests
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import JSONResponse
from ultralytics import YOLO
import uvicorn
import dotenv

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
            cloud_name="de8dmh7iq",
            api_key="878738396278587",
            api_secret="TvLHcRpcWaA4Vl1zmjOl23lc9rY",
            secure=True,
        )
    except Exception:
        _CLOUDINARY_AVAILABLE = False


# ========= CLOUDINARY UPLOAD HELPER =========
def upload_bytes_to_cloudinary(img_bytes: bytes, filename: str):
    """Upload image bytes directly to Cloudinary without saving to disk"""
    if not _CLOUDINARY_AVAILABLE:
        logger.warning("Cloudinary module not available")
        return None
    try:
        result = cloudinary.uploader.upload(
            img_bytes,
            folder="image_result", 
            public_id=filename,
            resource_type="image",
            overwrite=True
        )
        logger.info(f"✅ Upload successful: {filename}")
        return result.get("secure_url") or result.get("url")
    except Exception as e:
        logger.error(f"❌ Upload failed: {e}")
        return None


# ============= LOGGING =============
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cloud_ai")

app = FastAPI(title="Cloud AI - YOLOv11s Inference")


# ============= LOAD YOLO MODEL =============
try:
    model = YOLO(
        r"D:\STUDY\Ky1_Nam4\Thiet_Ke_Dien_Tu_PTIT\AI_Human\Dataset\yolo11s.pt"
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


# ============= MAIN API: /analyze (với webhook) =============
@app.post("/analyze")
async def analyze_with_webhook(
    image_url: str = Form(...),
    device_id: str = Form(...),
    record_id: int = Form(...),
    webhook_url: str = Form(...),
):
    """
    Endpoint mới cho capture analysis với webhook callback
    - Nhận image_url, record_id, webhook_url
    - Xử lý YOLO detection
    - Upload annotated image lên Cloudinary
    - Gửi kết quả về webhook
    """
    try:
        # Download image from URL
        img = read_image_from_url(image_url)
        
        if img is None:
            error_response = {
                "record_id": record_id,
                "success": False,
                "error": "Unable to download or decode image"
            }
            # Try to notify webhook about failure
            try:
                requests.post(webhook_url, json=error_response, timeout=5)
            except Exception:
                logger.error(f"Failed to send error callback to {webhook_url}")
            return JSONResponse(error_response, status_code=400)
        
        # YOLO Inference
        try:
            results = model(img, verbose=False)[0]
        except Exception as e:
            logger.exception("Inference failed")
            error_response = {
                "record_id": record_id,
                "success": False,
                "error": f"Model inference failed: {str(e)}"
            }
            try:
                requests.post(webhook_url, json=error_response, timeout=5)
            except Exception:
                pass
            return JSONResponse(error_response, status_code=500)
        
        # Count persons by class
        earth_person_count = 0
        sea_person_count = 0
        detections = []
        
        for box in results.boxes:
            cls_id = int(box.cls[0])
            if cls_id not in [0, 1]:  # Only earth_person (0) and sea_person (1)
                continue
            
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            conf = float(box.conf[0]) if hasattr(box, "conf") else 0.0
            
            label = "earth_person" if cls_id == 0 else "sea_person"
            color = (0, 255, 0) if cls_id == 0 else (0, 165, 255)  # Green for earth, Orange for sea
            
            # Draw bbox
            cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
            cv2.putText(
                img, label, (x1, max(0, y1 - 5)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2
            )
            
            detections.append({
                "label": label,
                "bbox": [x1, y1, x2, y2],
                "confidence": conf
            })
            
            if cls_id == 0:
                earth_person_count += 1
            else:
                sea_person_count += 1
        
        total_person_count = earth_person_count + sea_person_count
        
        # Encode annotated image to memory buffer
        image_id = int(time.time() * 1000)
        _, buffer = cv2.imencode('.jpg', img)
        img_bytes = buffer.tobytes()
        
        # Upload directly to Cloudinary from memory (no local save)
        if not _CLOUDINARY_AVAILABLE:
            logger.error("Cloudinary not available, cannot upload annotated image")
            cloud_url = None
        else:
            try:
                result = cloudinary.uploader.upload(
                    img_bytes,
                    folder="image_result",
                    public_id=f"analyzed_{record_id}_{image_id}",
                    resource_type="image",
                    overwrite=True
                )
                cloud_url = result.get("secure_url") or result.get("url")
                logger.info(f"✅ Annotated image uploaded: {cloud_url}")
            except Exception as upload_error:
                logger.error(f"❌ Failed to upload annotated image: {upload_error}")
                cloud_url = None
        
        # Prepare result payload
        result_payload = {
            "record_id": record_id,
            "success": True,
            "result": {
                "total_person": total_person_count,
                "earth_person_count": earth_person_count,
                "sea_person_count": sea_person_count,
                "detections": detections,
                "cloud_url": cloud_url
            }
        }
        
        logger.info(f"✅ Analysis complete for record {record_id}: {total_person_count} persons detected")
        
        # Send to webhook
        try:
            webhook_response = requests.post(webhook_url, json=result_payload, timeout=10)
            if webhook_response.status_code == 200:
                logger.info(f"✅ Webhook callback sent successfully to {webhook_url}")
            else:
                logger.error(f"❌ Webhook callback failed: {webhook_response.status_code}")
        except Exception as webhook_error:
            logger.error(f"❌ Failed to send webhook: {str(webhook_error)}")
        
        # Return result to caller as well
        return JSONResponse(result_payload)
        
    except Exception as e:
        logger.exception(f"Unexpected error in analyze_with_webhook")
        error_response = {
            "record_id": record_id,
            "success": False,
            "error": str(e)
        }
        try:
            requests.post(webhook_url, json=error_response, timeout=5)
        except Exception:
            pass
        return JSONResponse(error_response, status_code=500)


# ============= LEGACY API: /result (giữ lại cho tương thích) =============
@app.post("/result")
async def result(
    file: Optional[UploadFile] = File(None),
    image_url: Optional[str] = Form(None),
    device_id: Optional[str] = Form(None),
    timestamp: Optional[str] = Form(None),
    person_type: Optional[str] = Form(None),
):
    """Xử lý 1 ảnh → detect YOLO → annotate → lưu local → upload Cloudinary (legacy endpoint)"""

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

    # --------- YOLO INFERENCE ---------
    try:
        results = model(img, verbose=False)[0]
    except Exception:
        logger.exception("Inference failed")
        return JSONResponse({"error": "Model inference failed"}, status_code=500)

    # --------- DRAW BBOX ---------
    detections = []
    label_text = "earth_person" if (person_type or "").lower() != "sea" else "sea_person"

    for box in results.boxes:
        cls_id = int(box.cls[0])
        if cls_id != 0:   # chỉ detect class 0 (person)
            continue

        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
        conf = float(box.conf[0]) if hasattr(box, "conf") else 0.0

        # Draw bbox & label
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(
            img, label_text, (x1, max(0, y1 - 5)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2
        )

        detections.append({
            "label": label_text,
            "bbox": [x1, y1, x2, y2],
            "confidence": conf
        })

    total_person = len(detections)

    # --------- UPLOAD TO CLOUDINARY (from memory, no local save) ---------
    image_id = int(time.time() * 1000)
    _, buffer = cv2.imencode('.jpg', img)
    img_bytes = buffer.tobytes()
    
    cloud_url = upload_bytes_to_cloudinary(
        img_bytes,
        filename=f"annotated_{image_id}"
    )

    # --------- RETURN RESPONSE ---------
    return JSONResponse({
        "total_person": total_person,
        "detections": detections,
        "cloud_url": cloud_url,
        "device_id": device_id,
        "timestamp": timestamp,
    })


# ============= MAIN ENTRY =============
if __name__ == "__main__":
    uvicorn.run("cloud:app", host="0.0.0.0", port=8000, log_level="info")
