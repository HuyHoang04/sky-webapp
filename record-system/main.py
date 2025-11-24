#!/usr/bin/env python3
"""
SkyAid Record System
Audio recording and capture system with GPIO integration

Copyright (c) 2025 HuyHoang04
Licensed under MIT License - see LICENSE file for details
"""

import json
import RPi.GPIO as GPIO
import os
import subprocess
from time import sleep
import time
import signal
import sys
import atexit
import fcntl
import cloudinary
import cloudinary.uploader
import requests
import socketio
import threading
from dotenv import load_dotenv
load_dotenv()


# ----------------- CẤU HÌNH -----------------
BUTTON_PIN = 17
RECORD_SECONDS = 15
SAMPLE_RATE = 48000
VOLUME_GAIN = 3.5

HELP_SOUND = "/home/pi/Documents/Drone2025/music/Help_me.wav"
SAVE_DIR = "/home/pi/Documents/Drone2025/mic_help"
COUNTER_FILE = os.path.join(SAVE_DIR, "counter.txt")
PULSE_SERVER = "/run/user/1000/pulse/native"
MIC_DEVICE = "plughw:2,0"

# Cloudinary
CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
CLOUD_KEY = os.getenv("CLOUDINARY_API_KEY")
CLOUD_SECRET = os.getenv("CLOUDINARY_API_SECRET")
if not CLOUD_NAME or not CLOUD_KEY or not CLOUD_SECRET:
    raise ValueError("[CONFIG] CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET must be set in environment variables")
cloudinary.config(
  cloud_name = CLOUD_NAME,
  api_key = CLOUD_KEY,
  api_secret = CLOUD_SECRET
)
CLOUD_FOLDER = "help"

WEB_APP_URL = os.getenv("WEB_APP_URL")
if not WEB_APP_URL:
    WEB_APP_URL = "http://localhost:5000/api/voice/records"
    print(f"[CONFIG]  WEB_APP_URL not set in environment, using default: {WEB_APP_URL}")
    print("[CONFIG] Set WEB_APP_URL environment variable to configure the production endpoint")
else:
    print(f"[CONFIG] Using Web App URL: {WEB_APP_URL}")

# Validate URL format
if not WEB_APP_URL.startswith(("http://", "https://")):
    raise ValueError(f"[CONFIG] Invalid WEB_APP_URL: '{WEB_APP_URL}' - Must start with http:// or https://")

DEVICE_ID = os.environ.get("DEVICE_ID", "rescue_mic_01")  # Device identifier (configurable)
print(f"[CONFIG] Device ID: {DEVICE_ID}")

# Web App Socket.IO URL
WEB_APP_SOCKET_URL = "https://kanisha-unannexable-laraine.ngrok-free.dev/"
print(f"[CONFIG] Web App Socket URL: {WEB_APP_SOCKET_URL}")

os.makedirs(SAVE_DIR, exist_ok=True)

GPIO.setmode(GPIO.BCM)
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# Socket.IO client
sio = socketio.Client()

# Global flag for web trigger
web_trigger_flag = False
web_trigger_lock = threading.Lock()

def cleanup_resources():
    """Clean up GPIO and other resources before exit"""
    print("\n[CLEANUP] Cleaning up resources...")
    try:
        GPIO.cleanup()
        print("[CLEANUP] GPIO cleaned up successfully")
    except Exception as e:
        print(f"[CLEANUP] Error cleaning GPIO: {e}")

def signal_handler(signum, frame):
    """Handle SIGINT (Ctrl+C) and SIGTERM signals"""
    print(f"\n[SIGNAL] Received signal {signum}, shutting down gracefully...")
    cleanup_resources()
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
signal.signal(signal.SIGTERM, signal_handler)  # kill command
atexit.register(cleanup_resources)
print("[SYSTEM] Initialized. Waiting for button press...")
print("[SYSTEM] Press Ctrl+C to exit gracefully")

def play_sound():
    subprocess.run(
        ["ffplay", "-nodisp", "-autoexit", HELP_SOUND],
        env={"PULSE_SERVER": PULSE_SERVER},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

def get_next_filename():
    """
    Atomically read and increment the counter file with exclusive file locking.
    Prevents race conditions when multiple processes try to get filenames concurrently.
    """
    # Open counter file in read-write mode, create if doesn't exist
    try:
        # Use 'r+' if file exists, otherwise 'w+' to create
        # Open in 'a+' mode (create if doesn't exist, read/write if exists)
        f = open(COUNTER_FILE, "a+")        
        try:
            # Acquire exclusive lock (blocks until lock is available)
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            
            # Read current counter value
            f.seek(0)
            content = f.read().strip()
            
            if content and content.isdigit():
                count = int(content)
            else:
                count = 1  # Default to 1 if file is empty or invalid
            
            filename = os.path.join(SAVE_DIR, f"record_{count}.wav")
            
            # Write incremented counter atomically
            f.seek(0)
            f.truncate()
            f.write(str(count + 1))
            f.flush()  # Ensure data is written to disk
            os.fsync(f.fileno())  # Force OS to write to disk
            
            # Lock is automatically released when file is closed
            
        finally:
            # Release lock and close file
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            f.close()
        
        return filename
        
    except Exception as e:
        print(f"[COUNTER] Error accessing counter file: {e}")
        # Fallback to timestamp-based filename if counter fails
        timestamp = int(time.time())
        filename = os.path.join(SAVE_DIR, f"record_{timestamp}.wav")
        print(f"[COUNTER] Using timestamp-based filename: {filename}")
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
        "-d", str(RECORD_SECONDS),  # Duration in seconds (proper way to record fixed length)
        wav_file
    ]

    try:
        # No timeout needed since -d parameter handles recording duration
        result = subprocess.run(cmd_record, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"[RECORD] arecord error: {result.stderr}")
            raise RuntimeError(f"arecord failed with exit code {result.returncode}")
    except Exception as e:
        print(f"[RECORD] Recording failed: {e}")
        raise

    # Tăng âm lượng trực tiếp trên cùng file WAV (same as old code)
    tmp_file = wav_file + ".tmp.wav"
    
    # Use shell=True like old code (safe since we control all parameters)
    ffmpeg_cmd = f"ffmpeg -y -i {wav_file} -filter:a 'volume={VOLUME_GAIN}' {tmp_file}"
    
    result = subprocess.run(
        ffmpeg_cmd,
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    if result.returncode == 0 and os.path.exists(tmp_file):
        os.replace(tmp_file, wav_file)
        print(f"[RECORD] recording finished and saved successfully: {wav_file}")
    else:
        print(f"[RECORD] Warning: ffmpeg volume adjustment may have failed")
        # Continue anyway, original WAV file still exists
        if os.path.exists(tmp_file):
            os.remove(tmp_file)
    
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

def process_recording():
    """Xử lý ghi âm - function chung cho cả GPIO và web trigger"""
    print("[TRIGGER] Recording triggered — playing Help_me.wav then recording...")

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

    print("[TRIGGER] Returning to standby mode...\n")

# ----------------- SOCKET.IO EVENT HANDLERS -----------------
@sio.on('connect')
def on_connect():
    print("[SOCKET] Connected to Web App")
    sio.emit('register_record_device', {'device_id': DEVICE_ID})

@sio.on('disconnect')
def on_disconnect():
    print("[SOCKET] Disconnected from Web App")

@sio.on('trigger_recording')
def on_trigger_recording(data):
    """Nhận lệnh trigger recording từ web"""
    global web_trigger_flag
    
    print(f"[SOCKET] Received trigger_recording event: {data}")
    
    with web_trigger_lock:
        if web_trigger_flag:
            print("[SOCKET] Recording already in progress, ignoring trigger")
            return
        web_trigger_flag = True
        print("[SOCKET] Web trigger flag set to True")

# Connect to Web App Socket.IO server
def connect_to_web_app():
    """Kết nối đến Web App Socket.IO server"""
    try:
        print(f"[SOCKET] Connecting to {WEB_APP_SOCKET_URL}...")
        sio.connect(WEB_APP_SOCKET_URL)
        print("[SOCKET] Connection initiated")
    except Exception as e:
        print(f"[SOCKET] Failed to connect: {e}")
        print("[SOCKET] Will retry in background...")

# Start Socket.IO connection in background
connection_thread = threading.Thread(target=connect_to_web_app, daemon=True)
connection_thread.start()

# ----------------- VÒNG LẶP CHÍNH -----------------
try:
    while True:
        # Kiểm tra nút GPIO vật lý
        if GPIO.input(BUTTON_PIN) == GPIO.LOW:
            print("[BUTTON] Physical button pressed")
            process_recording()
            sleep(1)
        
        # Kiểm tra web trigger từ Socket.IO
        with web_trigger_lock:
            if web_trigger_flag:
                print("[WEB] Web trigger activated")
                web_trigger_flag = False  # Reset flag
                process_recording()
                sleep(1)
        
        sleep(0.05)

except KeyboardInterrupt:
    print("\n[INTERRUPT] Keyboard interrupt detected")
except Exception as e:
    print(f"\n[ERROR] Unexpected error in main loop: {e}")
finally:
    cleanup_resources()
    print("[SYSTEM] Script terminated")
