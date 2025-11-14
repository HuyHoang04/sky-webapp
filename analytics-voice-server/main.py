import uvicorn
import torch
import whisper
import os
import time
import json
import requests
import tempfile
import re
import signal
import atexit
from collections import deque
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
import fastapi
from fastapi import Query
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
                print("[QUEUE WORKER] Received shutdown signal, exiting gracefully")
                analysis_queue.task_done()
                break
            
            print(f"[QUEUE] Processing analysis job for record {job['record_id']} (Queue size: {analysis_queue.qsize()})")
            
            # Run the actual analysis
            _process_analysis_job(job)
            
            # Mark job as done
            analysis_queue.task_done()
            
        except Exception as e:
            print(f"[QUEUE WORKER ERROR] {str(e)}")
            analysis_queue.task_done()
    
    print("[QUEUE WORKER] Worker thread terminated cleanly")

# Start background worker thread (non-daemon for graceful shutdown)
analysis_worker_thread = threading.Thread(target=analysis_worker, daemon=False)
analysis_worker_thread.start()

# Shutdown state flag to prevent duplicate shutdowns
_shutdown_initiated = False
_shutdown_lock = threading.Lock()

def shutdown_analysis_worker():
    """
    Gracefully shutdown the analysis worker thread (idempotent)
    Sends poison pill and waits for thread to finish current job
    Safe to call multiple times - will only shutdown once
    """
    global _shutdown_initiated
    
    with _shutdown_lock:
        if _shutdown_initiated:
            print("[SHUTDOWN] Already initiated, skipping duplicate shutdown")
            return
        _shutdown_initiated = True
    
    print("[SHUTDOWN] Initiating graceful shutdown of analysis worker...")
    
    # Send poison pill to stop the worker
    analysis_queue.put(None)
    
    # Wait for worker to finish with timeout
    print("[SHUTDOWN] Waiting for worker thread to complete (timeout: 30s)...")
    analysis_worker_thread.join(timeout=30)
    
    if analysis_worker_thread.is_alive():
        print("[SHUTDOWN]  Worker thread did not finish within timeout")
    else:
        print("[SHUTDOWN]  Worker thread finished cleanly")

# Register shutdown handlers
def signal_handler(signum, frame):
    """
    Handle SIGTERM and SIGINT signals
    Cleanup worker thread and let FastAPI/Uvicorn handle graceful shutdown
    """
    print(f"[SIGNAL] Received signal {signum}, initiating graceful shutdown...")
    shutdown_analysis_worker()
    # Don't call exit() - let FastAPI/Uvicorn handle graceful shutdown

# Register for SIGTERM (docker stop, systemd stop, etc.)
signal.signal(signal.SIGTERM, signal_handler)

# Register for SIGINT (Ctrl+C)
signal.signal(signal.SIGINT, signal_handler)

# Register for normal exit (atexit) - this will handle non-signal exits
atexit.register(shutdown_analysis_worker) 

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

# Bounded results storage (keeps last 1000 results)
RESULTS = deque(maxlen=1000)
results_lock = threading.Lock()

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
        
        # Thread-safe append to results
        with results_lock:
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
            print(f"[CALLBACK 2]  Analysis error sent to Web App")
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
    
    # Initialize variables early to avoid UnboundLocalError in exception handlers
    record_id = None
    audio_url = None
    tmp_path = None
    
    try:
        # Extract and validate required fields
        audio_url = payload.get("audio_url")
        record_id = payload.get("record_id")

        if not audio_url:
            return {"success": False, "error": "Thiếu audio_url"}
        
        if not record_id:
            return {"success": False, "error": "Thiếu record_id"}
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
            print(f"[CALLBACK 1]  Transcription sent to Web App (fast response)")
        except Exception as send_e:
            print(f"[CALLBACK 1]  Failed to send transcription to Web App: {send_e}")

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
        
        # Callback error to Web App (only if we have a valid record_id)
        if record_id is not None:
            try:
                error_payload = {
                    "record_id": record_id,
                    "success": False,
                    "error": str(e)
                }
                requests.post(WEB_CALLBACK_URL, json=error_payload, timeout=30)
                print(f"[API] Error sent to Web App callback for record {record_id}")
            except Exception as send_e:
                print(f"[API] Failed to send error to Web App: {send_e}")
        else:
            print(f"[API] No record_id available, skipping error callback")
        
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
def get_results(
    limit: int = Query(default=100, ge=1, le=1000, description="Number of results to return"),
    offset: int = Query(default=0, ge=0, description="Number of results to skip")
):
    """
    Get paginated analysis results
    
    Query Parameters:
    - limit: Number of results per page (1-1000, default: 100)
    - offset: Number of results to skip (default: 0)
    
    Returns:
    - results: List of analysis results for the requested page
    - total: Total number of results available
    - limit: Applied limit
    - offset: Applied offset
    - has_more: Whether there are more results available
    """
    with results_lock:
        # Convert deque to list for slicing (thread-safe)
        results_list = list(RESULTS)
        total_count = len(results_list)
        
        # Apply pagination
        start_idx = offset
        end_idx = offset + limit
        paginated_results = results_list[start_idx:end_idx]
        
        return {
            "results": paginated_results,
            "total": total_count,
            "limit": limit,
            "offset": offset,
            "has_more": end_idx < total_count,
            "page": (offset // limit) + 1 if limit > 0 else 1
        }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)