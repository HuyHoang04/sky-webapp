"""
test_api.py

Script đơn giản để kiểm tra Cloud AI FastAPI server (cloud.py).
- Kiểm tra server chạy (GET /docs)
- Gửi ảnh từ Internet (random từ randomuser.me) tới POST /result
- Gửi ảnh từ local file tới POST /result
- Tải ảnh annotated từ cloud_url trả về và lưu vào ổ đĩa

Cách dùng:
1. Chạy server: python cloud.py
2. Chạy script này: python test_api.py
"""

import requests
import json
import time
import random
from pathlib import Path

# Địa chỉ server (chỉnh nếu server chạy ở host/port khác)
BASE_URL = "http://localhost:8000"

# -------------------------
# Hàm lấy URL ảnh random
# -------------------------
def get_random_image_url():
    """
    Trả về 1 URL ảnh người random từ API randomuser.me.
    randomuser cung cấp avatar ở đường dẫn:
      https://randomuser.me/api/portraits/{men|women}/{index}.jpg
    index: 0..99

    Lưu ý: ảnh này thường chụp rõ mặt, phù hợp để test detect person.
    """
    gender = random.choice(["men", "women"])
    index = random.randint(0, 99)  # random index 0..99
    url = f"https://randomuser.me/api/portraits/{gender}/{index}.jpg"
    return url


# -------------------------
# Hàm download ảnh từ URL
# -------------------------
def download_image(url: str, save_path: str):
    """
    Tải ảnh từ URL và lưu vào save_path.
    - dùng stream để không load toàn bộ file vào bộ nhớ nếu file lớn.
    - timeout để tránh treo nếu server không phản hồi.
    """
    try:
        r = requests.get(url, stream=True, timeout=10)
        if r.status_code == 200:
            with open(save_path, "wb") as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
            print(f"  ✓ Đã lưu ảnh: {save_path}")
            return True
        else:
            print(f"  ✗ Không thể tải ảnh (status {r.status_code}) - {url}")
            return False
    except Exception as e:
        print(f"  ✗ Lỗi khi tải ảnh: {e} - {url}")
        return False


# -------------------------
# Test 1: kiểm tra server chạy
# -------------------------
def test_root():
    print("=" * 60)
    print("TEST 1: Kiểm tra server chạy (GET /docs)")
    print("=" * 60)
    try:
        resp = requests.get(f"{BASE_URL}/docs", timeout=5)
        if resp.status_code == 200:
            print("✓ Server đang chạy! /docs truy cập được.")
            return True
        else:
            print(f"✗ Server trả về status {resp.status_code}")
            return False
    except Exception as e:
        print(f"✗ Không kết nối được tới server: {e}")
        print("  → Hãy chạy: python cloud.py")
        return False


# -------------------------
# Test 2: gửi ảnh URL (random) tới /result
# -------------------------
def test_result_with_random_url():
    print("\n" + "=" * 60)
    print("TEST 2: Gửi ảnh random từ Internet tới POST /result")
    print("=" * 60)

    # Lấy 1 URL random
    image_url = get_random_image_url()
    print(f" Chosen random image URL: {image_url}")

    payload = {
        "image_url": image_url,
        "device_id": "random_internet_001",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "person_type": "earth"
    }

    try:
        resp = requests.post(f"{BASE_URL}/result", data=payload, timeout=30)
        print(f"Status: {resp.status_code}")
        result = resp.json()
        print(json.dumps(result, indent=2))

        if resp.status_code == 200:
            print(f"✓ total_person detected: {result.get('total_person', 0)}")
            cloud_url = result.get("cloud_url")
            if cloud_url:
                save_name = f"output/annotated_random_{int(time.time())}.jpg"
                # Tải ảnh annotated từ Cloudinary (nếu có)
                download_image(cloud_url, save_name)
            else:
                print("✗ cloud_url không được trả về (Cloudinary có thể lỗi).")
        else:
            print("✗ Yêu cầu thất bại, kiểm tra logs server.")

    except Exception as e:
        print(f"✗ Lỗi khi gọi API: {e}")


# -------------------------
# Test 3: gửi ảnh local (file upload) tới /result
# -------------------------
def test_result_with_file():
    print("\n" + "=" * 60)
    print("TEST 3: Gửi ảnh từ local folder tới POST /result (file upload)")
    print("=" * 60)

    # Path đến dataset (chỉnh theo máy của bạn)
    dataset_path = Path(r"D:\STUDY\Ky1_Nam4\Thiet_Ke_Dien_Tu_PTIT\AI_Human\Dataset\tiny-person-dataset_4")
    test_images = list(dataset_path.glob("test/images/*.jpg"))

    if not test_images:
        print("✗ Không tìm thấy ảnh test trong folder:")
        print(f"   {dataset_path}/test/images/*.jpg")
        return

    test_image_path = test_images[0]
    print(f" Dùng ảnh local: {test_image_path}")

    try:
        with open(test_image_path, "rb") as f:
            files = {"file": (test_image_path.name, f, "image/jpeg")}
            data = {
                "device_id": "local_file_001",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "person_type": "sea"
            }
            resp = requests.post(f"{BASE_URL}/result", files=files, data=data, timeout=30)

        print(f"Status: {resp.status_code}")
        result = resp.json()
        print(json.dumps(result, indent=2))

        if resp.status_code == 200:
            cloud_url = result.get("cloud_url")
            if cloud_url:
                save_name = f"output/annotated_local_{int(time.time())}.jpg"
                download_image(cloud_url, save_name)
            else:
                print("✗ cloud_url không được trả về.")
        else:
            print("✗ Yêu cầu thất bại, kiểm tra logs server.")

    except Exception as e:
        print(f"✗ Lỗi khi gửi file: {e}")


# -------------------------
# Test 4: Nhiều lần random để đánh giá sơ bộ accuracy
# -------------------------
def test_random_multiple(n=5, pause_sec=1):
    """
    Thực hiện n lần lấy ảnh random và gửi lên server.
    - Mục đích: có 1 chuỗi kết quả để đánh giá nhanh (không phải benchmark chính thức).
    - pause_sec: tạm dừng giữa các lần (tránh spam server).
    """
    print("\n" + "=" * 60)
    print(f"TEST 4: Gửi {n} ảnh random liên tiếp để test sơ bộ độ chính xác")
    print("=" * 60)

    stats = {"total_tests": n, "total_person_detected": 0, "results": []}

    for i in range(n):
        print(f"\n-- Round {i+1}/{n} --")
        image_url = get_random_image_url()
        payload = {
            "image_url": image_url,
            "device_id": f"random_round_{i+1}",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "person_type": "earth"
        }
        try:
            resp = requests.post(f"{BASE_URL}/result", data=payload, timeout=30)
            if resp.status_code == 200:
                result = resp.json()
                tp = result.get("total_person", 0)
                stats["total_person_detected"] += tp
                stats["results"].append({"url": image_url, "total_person": tp, "cloud_url": result.get("cloud_url")})
                print(f" Detected persons: {tp}")
            else:
                print(f" Request failed: status {resp.status_code}")
                stats["results"].append({"url": image_url, "error": f"status_{resp.status_code}"})
        except Exception as e:
            print(f" Error calling API: {e}")
            stats["results"].append({"url": image_url, "error": str(e)})

        time.sleep(pause_sec)  # đợi một chút trước khi lần kế tiếp

    print("\n--- Summary ---")
    print(json.dumps(stats, indent=2))
    return stats


# -------------------------
# Main: gọi các test
# -------------------------
def main():
    print("\n" + "=" * 60)
    print(" CLOUD AI FASTAPI SERVER TEST (with random internet images)")
    print("=" * 60)

    if not test_root():
        return

    # Test 2: 1 ảnh random
    test_result_with_random_url()

    # Test 3: 1 ảnh local upload
    test_result_with_file()

    # Test 4: chạy nhiều lần random (thay đổi n nếu muốn)
    _ = test_random_multiple(n=5, pause_sec=1)

    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)


if __name__ == "__main__":
    main()
