import uvicorn
import torch
import whisper
import os
import time
import json
import requests
import tempfile
import re
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
import fastapi
import threading
import queue

app = fastapi.FastAPI()

# Web App callback URL (to update analysis results)
WEB_CALLBACK_URL = "https://your-webapp-url.dev/api/voice/analysis/callback"

# ============================================
# QUEUE SYSTEM FOR ANALYSIS
# ============================================
# Analysis queue: Only 1 LLM analysis at a time (slow, resource-intensive)
analysis_queue = queue.Queue()
analysis_queue_lock = threading.Lock()

def analysis_worker():
    """
    Background worker that processes analysis jobs one by one
    Prevents multiple LLM analyses from running simultaneously
    """
    print("[QUEUE WORKER] Analysis queue worker started")
    
    while True:
        try:
            # Get next job from queue (blocks until available)
            job = analysis_queue.get()
            
            if job is None:  # Poison pill to stop worker
                break
            
            print(f"[QUEUE] Processing analysis job for record {job['record_id']} (Queue size: {analysis_queue.qsize()})")
            
            # Run the actual analysis
            _process_analysis_job(job)
            
            # Mark job as done
            analysis_queue.task_done()
            
        except Exception as e:
            print(f"[QUEUE WORKER ERROR] {str(e)}")
            analysis_queue.task_done()

# Start background worker thread
analysis_worker_thread = threading.Thread(target=analysis_worker, daemon=True)
analysis_worker_thread.start() 

# ==== DEVICE & DTYPE ====
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print("[DEVICE] Using device:", device)

# ==== WHISPER MODEL ====
print("[WHISPER] Loading Whisper model...")
whisper_model = whisper.load_model("small", device=device) 
print("[WHISPER] Whisper model loaded.")

# ==== LLM MODEL CONFIG - 4BIT QUANTIZATION ====
LLM_MODEL_NAME = "microsoft/Phi-3-mini-4k-instruct"

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_use_double_quant=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.float16
)

print("[PHI3] Loading LLM model (this may take a moment)...")
llm_model = AutoModelForCausalLM.from_pretrained(
    LLM_MODEL_NAME,
    quantization_config=bnb_config,
    device_map="auto",
    trust_remote_code=True
)

llm_model.config.use_cache = False
llm_tokenizer = AutoTokenizer.from_pretrained(LLM_MODEL_NAME)
print("[PHI3] LLM model loaded.")

# ==== HELPER GENERATE FUNCTION (max_tokens = 200) ====
def generate_text(prompt, max_tokens=200): 
    inputs = llm_tokenizer(prompt, return_tensors="pt").to(llm_model.device)
    prompt_length = inputs.input_ids.shape[-1]
    
    with torch.no_grad():
        output_ids = llm_model.generate(
            **inputs,
            max_new_tokens=max_tokens, 
            do_sample=False,
            use_cache=False,
            pad_token_id=llm_tokenizer.eos_token_id
        )
    generated_text = llm_tokenizer.decode(output_ids[0][prompt_length:], skip_special_tokens=True)
    return generated_text.strip()

# ==== SYSTEM PROMPT ====
SYSTEM_PROMPT = """<|system|>
Bạn là AI phân tích cứu hộ lũ lụt. Trích xuất INTENT (Bị thương, Đói/Khát, Cứu Gấp, Không rõ) và ITEMS (Thuốc, Đồ ăn, Nước, Vật dụng y tế).
Phản hồi CỰC KỲ NGẮN GỌN, CHỈ JSON hợp lệ. **Intent: 1 dòng. Items: Tối đa 3 vật dụng cô đọng.**
</|system|>"""

# ==== BUILD PROMPT ====
def build_prompt(text):
    return f"""{SYSTEM_PROMPT}
<|user|>Văn bản: "{text}"</|user|>
<|assistant|>
```json
"""

# ==== PARSE LLM OUTPUT ====
def parse_llm_output(text_output):
    try:
        json_match = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", text_output, re.DOTALL)
        
        if json_match:
            json_str = json_match.group(1)
            return json.loads(json_str)
        else:
            json_start = text_output.find("{")
            json_end = text_output.rfind("}") + 1
            
            if json_start != -1 and json_end != 0 and json_end > json_start:
                 json_str = text_output[json_start:json_end]
                 try:
                     return json.loads(json_str)
                 except json.JSONDecodeError as e:
                     return {"error": f"JSON Decode Error (Fallback): {str(e)}", "raw_output": text_output}
            
            return {"error": "No valid JSON structure found in LLM output", "raw_output": text_output}
    except Exception as e:
        return {"error": str(e), "raw_output": text_output}

RESULTS = []

def _process_analysis_job(job):
    """
    Process a single analysis job (runs in background queue)
    Job structure: {
        "record_id": int,
        "audio_url": str,
        "text": str,
        "start_time": float
    }
    """
    record_id = job['record_id']
    audio_url = job['audio_url']
    text = job['text']
    start_time = job['start_time']
    
    try:
        print(f"[ANALYSIS JOB] Starting LLM analysis for record {record_id}")
        full_prompt = build_prompt(text)
        
        llm_output_text = generate_text(full_prompt) 
        analysis_json = parse_llm_output(llm_output_text)
        print(f"[ANALYSIS JOB] Analysis complete for record {record_id}: {analysis_json.get('intent')}")

        # ============ CALLBACK 2: GỬI ANALYSIS SAU KHI PHÂN TÍCH XONG ============
        analysis_result = {
            "audio_url": audio_url,
            "text_goc": text,
            "analysis": analysis_json,
            "time": round(time.time() - start_time, 2)
        }
        
        RESULTS.append(analysis_result)

        try:
            callback_payload = {
                "record_id": record_id,
                "success": True,
                "result": analysis_result,
                "stage": "analysis"  # Đánh dấu đây là callback analysis
            }
            requests.post(WEB_CALLBACK_URL, json=callback_payload, timeout=30) 
            print(f"[CALLBACK 2] ✅ Analysis sent to Web App for record {record_id}")
        except Exception as send_e:
            print(f"[CALLBACK 2] ❌ Failed to send analysis to Web App: {send_e}")
            
    except Exception as e:
        print(f"[ANALYSIS JOB ERROR] Record {record_id}: {str(e)}")
        
        # Callback error to Web App
        try:
            error_payload = {
                "record_id": record_id,
                "success": False,
                "error": str(e),
                "stage": "analysis"
            }
            requests.post(WEB_CALLBACK_URL, json=error_payload, timeout=30)
            print(f"[CALLBACK 2] ❌ Analysis error sent to Web App")
        except Exception as send_e:
            print(f"[CALLBACK 2] Failed to send error: {send_e}")

@app.get("/")
def read_root():
    return {"message": "AI Service is running.", "queue_size": analysis_queue.qsize()}

# ==== ROUTES ====
@app.post("/analyze")
async def analyze_voice(payload: dict):
    """
    Receive analysis request from Web App
    Expected payload: {
        "record_id": int,
        "audio_url": "cloudinary_url"
    }
    """
    start = time.time()
    audio_url = payload.get("audio_url")
    record_id = payload.get("record_id")  # Get record_id from Web App

    if not audio_url:
        return {"success": False, "error": "Thiếu audio_url"}
    
    if not record_id:
        return {"success": False, "error": "Thiếu record_id"}

    tmp_path = None
    try:
        # Tải file âm thanh từ URL (Cloudinary trả về MP3)
        print(f"[DOWNLOAD] Downloading audio from {audio_url}...")
        r = requests.get(audio_url)
        r.raise_for_status()
        
        # Lưu với suffix .mp3 (vì Raspberry Pi upload MP3 lên Cloudinary)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3", mode='wb') as tmp: 
            tmp.write(r.content)
            tmp_path = tmp.name
        print(f"[DOWNLOAD] Download complete, saved to: {tmp_path}")

        # Whisper chuyển giọng nói thành text
        print("[WHISPER] Starting Whisper transcription...")
        trans = whisper_model.transcribe(tmp_path, language="vi", fp16=(device.type=="cuda"))
        text = trans["text"].strip()
        print(f"[WHISPER] Transcribed Text: '{text}'")

        if not text:
            # Không có văn bản → vẫn callback về Web App
            print("[WHISPER] No text transcribed")
            result = {
                "audio_url": audio_url,
                "text_goc": "",
                "analysis": {"intent": "Không rõ", "items": []},
                "time": round(time.time() - start, 2)
            }
            
            # Callback to Web App
            try:
                callback_payload = {
                    "record_id": record_id,
                    "success": True,
                    "result": result
                }
                requests.post(WEB_CALLBACK_URL, json=callback_payload, timeout=30)
                print(f"[API] Empty transcription result sent to Web App")
            except Exception as send_e:
                print(f"[API] Failed to send to Web App: {send_e}")
            
            return {"success": True, "result": result}

        # ============ CALLBACK 1: GỬI TEXT NGAY SAU KHI TRANSCRIBE XONG ============
        print("==== CALLBACK 1: SENDING TRANSCRIPTION TO WEB APP ====")
        transcription_result = {
            "audio_url": audio_url,
            "text_goc": text,
            "analysis": None,  # Chưa có analysis
            "time": round(time.time() - start, 2)
        }
        
        try:
            callback_payload = {
                "record_id": record_id,
                "success": True,
                "result": transcription_result,
                "stage": "transcription"  # Đánh dấu đây là callback transcription
            }
            requests.post(WEB_CALLBACK_URL, json=callback_payload, timeout=30)
            print(f"[CALLBACK 1] ⚡ Transcription sent to Web App (fast response)")
        except Exception as send_e:
            print(f"[CALLBACK 1] ❌ Failed to send transcription to Web App: {send_e}")

        # ============ ADD ANALYSIS JOB TO QUEUE (CHẠY BACKGROUND) ============
        analysis_job = {
            "record_id": record_id,
            "audio_url": audio_url,
            "text": text,
            "start_time": start
        }
        
        with analysis_queue_lock:
            queue_size = analysis_queue.qsize()
            analysis_queue.put(analysis_job)
            print(f"[QUEUE] Analysis job added for record {record_id} (Queue position: {queue_size + 1})")
        
        # Return immediately - analysis will run in background
        return {
            "success": True, 
            "message": "Transcription completed, analysis queued",
            "queue_position": queue_size + 1,
            "transcription": text
        }

    except Exception as e:
        print(f"[API] An error occurred: {str(e)}")
        
        # Callback error to Web App
        try:
            error_payload = {
                "record_id": record_id,
                "success": False,
                "error": str(e)
            }
            requests.post(WEB_CALLBACK_URL, json=error_payload, timeout=30)
            print(f"[API] Error sent to Web App callback")
        except Exception as send_e:
            print(f"[API] Failed to send error to Web App: {send_e}")
        
        return {"success": False, "error": str(e)}

    finally:
        # Dọn dẹp file tạm
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

@app.get("/queue/status")
def queue_status():
    """Get current analysis queue status"""
    return {
        "queue_size": analysis_queue.qsize(),
        "message": f"{analysis_queue.qsize()} analysis jobs in queue"
    }

@app.get("/results")
def get_results():
    """Get all analysis results"""
    return {"results": RESULTS}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)