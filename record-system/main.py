#!/usr/bin/env python3
import json
import RPi.GPIO as GPIO
import os
import subprocess
from time import sleep
import time
import cloudinary
import cloudinary.uploader
import requests # 👈 THÊM: Thư viện để gửi yêu cầu HTTP

# ----------------- CẤU HÌNH -----------------
BUTTON_PIN = 17
RECORD_SECONDS = 15
SAMPLE_RATE = 48000
VOLUME_GAIN = 3.5

HELP_SOUND = "/home/pi/Documents/Drone2025/music/Help_me.wav"
SAVE_DIR = "/home/pi/Documents/Drone2025/mic_help"
COUNTER_FILE = os.path.join(SAVE_DIR, "counter.txt")
PULSE_SERVER = "/run/user/1000/pulse/native"
MIC_DEVICE = "plughw:1,0"

# Cloudinary
cloudinary.config(
  cloud_name = "dk3hfleib",
  api_key = "476417423893251",
  api_secret = "4oBdZ9bPANC5_Eg1pLWAnKyr3m8"
)
CLOUD_FOLDER = "help"

# 🚀 CẤU HÌNH AI SERVICE MỚI
# Thay thế IP và Port bằng địa chỉ thực tế của server đang chạy FastAPI
AI_SERVICE_URL = "https://vincent-subporphyritic-nonextrinsically.ngrok-free.dev/analyze_from_url/" 
# Ví dụ: "http://192.168.1.100:8000/analyze_from_url/"
# --------------------------------------------

# Tạo thư mục lưu file nếu chưa có
os.makedirs(SAVE_DIR, exist_ok=True)

# Thiết lập GPIO polling với pull-up
GPIO.setmode(GPIO.BCM)
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

print("Hệ thống sẵn sàng — nhấn nút để phát Help_me.wav rồi ghi âm...")

# ----------------- HÀM -----------------
# ... (Các hàm play_sound, get_next_filename, record_audio, convert_to_mp3 không đổi)
# ...

def play_sound():
    """Phát Help_me.wav qua PulseAudio"""
    subprocess.run(
        ["ffplay", "-nodisp", "-autoexit", HELP_SOUND],
        env={"PULSE_SERVER": PULSE_SERVER},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

def get_next_filename():
    """Tạo file WAV theo số thứ tự 1,2,3,..."""
    if os.path.exists(COUNTER_FILE):
        with open(COUNTER_FILE, "r") as f:
            count = int(f.read().strip())
    else:
        count = 1

    filename = os.path.join(SAVE_DIR, f"record_{count}.wav")
    
    # Cập nhật counter cho lần sau
    with open(COUNTER_FILE, "w") as f:
        f.write(str(count + 1))
    
    return filename

def record_audio():
    """Ghi âm 15 giây và tăng âm lượng trực tiếp"""
    wav_file = get_next_filename()
    print(f"Bắt đầu ghi âm {RECORD_SECONDS}s... → {wav_file}")

    # Đệm tránh tiếng xẹt đầu
    time.sleep(0.5)

    cmd_record = [
        "arecord",
        "-D", MIC_DEVICE,
        "-f", "S16_LE",
        "-r", str(SAMPLE_RATE),
        "-c", "1",
        wav_file
    ]

    try:
        subprocess.run(cmd_record, timeout=RECORD_SECONDS)
    except subprocess.TimeoutExpired:
        pass

    # Tăng âm lượng trực tiếp trên cùng file WAV
    tmp_file = wav_file + ".tmp.wav"
    subprocess.run(
        f"ffmpeg -y -i {wav_file} -filter:a 'volume={VOLUME_GAIN}' {tmp_file}",
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    os.replace(tmp_file, wav_file)
    print(f"Đã lưu file tăng âm: {wav_file}")
    return wav_file

def convert_to_mp3(wav_path):
    """Chuyển WAV sang MP3 và xóa file WAV"""
    if not os.path.exists(wav_path):
        print("Không tạo được file WAV, bỏ qua chuyển MP3.")
        return None

    mp3_path = wav_path.replace(".wav", ".mp3")
    subprocess.run([
        "ffmpeg", "-y",
        "-i", wav_path,
        "-codec:a", "libmp3lame",
        "-qscale:a", "2",
        mp3_path
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    os.remove(wav_path)
    print(f"Đã lưu file MP3: {mp3_path}")
    return mp3_path

def send_to_ai_service(url):
    """Gửi URL Cloudinary tới AI Service để phân tích"""
    print(f"Gửi URL tới AI Service: {AI_SERVICE_URL}")
    payload = {"audio_url": url}
    try:
        # Sử dụng timeout 120s (2 phút) vì mô hình LLM có thể chậm
        response = requests.post(AI_SERVICE_URL, json=payload, timeout=120) 
        response.raise_for_status() # Raise exception cho 4xx hoặc 5xx lỗi
        data = response.json()
        print("✅ Phân tích AI thành công:")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return True
    except requests.exceptions.RequestException as e:
        print(f" Gửi yêu cầu tới AI Service thất bại: {e}")
        return False
    except json.JSONDecodeError:
        print(f"Phản hồi từ AI Service không phải JSON: {response.text}")
        return False

def upload_to_cloudinary(mp3_path):
    """Upload file MP3 lên Cloudinary và xóa sau khi upload thành công"""
    if not os.path.exists(mp3_path):
        print("File MP3 không tồn tại, bỏ qua upload.")
        return None # Trả về None nếu không thành công

    try:
        print(f"Uploading {mp3_path} ...")
        response = cloudinary.uploader.upload(
            mp3_path,
            resource_type="auto",
            folder=CLOUD_FOLDER
        )
        secure_url = response.get("secure_url")
        print("Uploaded successfully:", secure_url)

        # Xóa file sau khi upload thành công
        os.remove(mp3_path)
        print(f"File MP3 đã bị xóa: {mp3_path}")
        return secure_url # Trả về URL thành công
    except Exception as e:
        print("Upload thất bại:", e)
        return None

# ----------------- VÒNG LẶP CHÍNH -----------------
while True:
    if GPIO.input(BUTTON_PIN) == GPIO.LOW:  # Nhấn nút
        print("Nút được nhấn — phát Help_me.wav rồi ghi âm...")

        # Phát âm thanh Help_me
        play_sound()

        # Ghi âm + tăng âm lượng
        wav_file = record_audio()

        # Chuyển sang MP3
        mp3_file = convert_to_mp3(wav_file)

        # Upload lên Cloudinary và lấy URL
        cloudinary_url = None
        if mp3_file:
            cloudinary_url = upload_to_cloudinary(mp3_file)
            
        # 🚀 Gửi URL tới AI Service nếu upload thành công
        if cloudinary_url:
            send_to_ai_service(cloudinary_url)

        print("Quay lại chế độ chờ...\n")
        sleep(1)  # chống dội nút
    sleep(0.05)