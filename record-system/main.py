#!/usr/bin/env python3
import json
import RPi.GPIO as GPIO
import os
import subprocess
from time import sleep
import time
import cloudinary
import cloudinary.uploader
import requests 

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

# Web App API (receives voice + GPS, then triggers AI)
WEB_APP_URL = "https://your-webapp-url.dev/api/voice/records"
DEVICE_ID = "rescue_mic_01"  # Device identifier 

os.makedirs(SAVE_DIR, exist_ok=True)

GPIO.setmode(GPIO.BCM)
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

print("[SYSTEM] Initialized. Waiting for button press...")

def play_sound():
    subprocess.run(
        ["ffplay", "-nodisp", "-autoexit", HELP_SOUND],
        env={"PULSE_SERVER": PULSE_SERVER},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

def get_next_filename():
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
    print(f"[RECORD] recording started for {RECORD_SECONDS}s... → {wav_file}")

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
    print(f"[RECORD] recording finished and saved successfully: {wav_file}")
    return wav_file

def convert_to_mp3(wav_path):
    """Chuyển WAV sang MP3 và xóa file WAV"""
    if not os.path.exists(wav_path):
        print("[CONVERT] WAV file not found, skipping MP3 conversion.")
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
    print(f"[CONVERT] MP3 file saved: {mp3_path}")
    return mp3_path

def send_to_web_app(audio_url):
    """Send audio URL to Web App (Web App will add GPS from drone stream)"""
    print(f"[API] Sending to Web App: {WEB_APP_URL}")
    
    payload = {
        "device_id": DEVICE_ID,
        "audio_url": audio_url,
        "duration": RECORD_SECONDS
    }
    
    try:
        response = requests.post(WEB_APP_URL, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        print("[API] Response from Web App:")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return True
    except requests.exceptions.RequestException as e:
        print(f"[API] Failed to send to Web App: {e}")
        return False
    except json.JSONDecodeError:
        print(f"[API] Response is not valid JSON: {response.text}")
        return False

def upload_to_cloudinary(mp3_path):
    """Upload file MP3 lên Cloudinary và xóa sau khi upload thành công"""
    if not os.path.exists(mp3_path):
        print("[UPLOAD] MP3 file not found, skipping upload.")
        return None # Trả về None nếu không thành công

    try:
        print(f"[UPLOAD] Uploading {mp3_path} ...")
        response = cloudinary.uploader.upload(
            mp3_path,
            resource_type="auto",
            folder=CLOUD_FOLDER
        )
        secure_url = response.get("secure_url")
        print("[UPLOAD] Uploaded successfully:", secure_url)

        # Xóa file sau khi upload thành công
        os.remove(mp3_path)
        print(f"[UPLOAD] MP3 file deleted: {mp3_path}")
        return secure_url # Trả về URL thành công
    except Exception as e:
        print(f"[UPLOAD] Upload failed: {e}")
        return None

# ----------------- VÒNG LẶP CHÍNH -----------------
while True:
    if GPIO.input(BUTTON_PIN) == GPIO.LOW:  # Nhấn nút
        print("[BUTTON] Button pressed — playing Help_me.wav then recording...")

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
            
        # 🚀 Gửi URL + GPS tới Web App (Web App sẽ trigger AI service)
        if cloudinary_url:
            send_to_web_app(cloudinary_url)

        print("[BUTTON] Returning to standby mode...\n")
        sleep(1) 
    sleep(0.05)