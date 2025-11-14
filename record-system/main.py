import requests
import json

# URL server AI, khớp với port 8000 và route /analyze_from_url/
server_url = "http://127.0.0.1:8000/analyze_from_url/"

# URL audio Cloudinary
audio_url = "https://res.cloudinary.com/dj74ln3mo/video/upload/v1763008365/rescue_audio/k7a27ijgvbrfmp0aj8zk.mp4"

print(f"Đang gửi yêu cầu đến: {server_url}")
print(f"Với audio URL: {audio_url}")

try:
    # POST dữ liệu lên server
    response = requests.post(server_url, json={"audio_url": audio_url})
    response.raise_for_status()  # Raise error nếu HTTP không phải 200

    print("Đã nhận phản hồi từ server.")
    data = response.json()
    
    if data.get("success"):
        print("✅ Phân tích thành công:")
        result = data["result"]
        print("Text gốc:", result["text_goc"])
        print("Analysis:", json.dumps(result["analysis"], ensure_ascii=False, indent=2))
        print("Thời gian xử lý:", result["time"], "giây")
    else:
        print("❌ Lỗi khi phân tích:", data.get("error"))

except requests.exceptions.ConnectionError as e:
    print("\n❌ LỖI KẾT NỐI SERVER:", str(e))
    print("Hãy chắc chắn rằng bạn đã chạy file 'ai_service.py' trong một terminal khác.")
except requests.exceptions.RequestException as e:
    print(f"❌ Lỗi HTTP (có thể server bị lỗi): {str(e)}")