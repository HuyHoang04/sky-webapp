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

    # --------- SAVE LOCAL OUTPUT ---------
    os.makedirs("output", exist_ok=True)
    image_id = int(time.time() * 1000)
    save_path = f"output/annotated_{image_id}.jpg"
    cv2.imwrite(save_path, img)

    # --------- UPLOAD TO CLOUDINARY ---------
    cloud_url = upload_path_to_cloudinary(
        save_path,
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
