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

app = fastapi.FastAPI()

WEB_URL = "https://your-external-monitoring-endpoint.dev/voice" 

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

@app.get("/")
def read_root():
    return {"message": "AI Service is running."}

# ==== ROUTES ====
@app.post("/analyze_from_url/")
async def analyze_from_url(payload: dict):
    start = time.time()
    audio_url = payload.get("audio_url")

    if not audio_url:
        return {"success": False, "error": "Thiếu audio_url"}

    tmp_path = None
    try:
        # Tải file âm thanh từ URL
        print(f"[DOWNLOAD] Downloading audio from {audio_url}...")
        r = requests.get(audio_url)
        # Sử dụng 'wb' để đảm bảo ghi nội dung nhị phân (binary content)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".m4a", mode='wb') as tmp: 
            tmp.write(r.content)
            tmp_path = tmp.name
        print("[DOWNLOAD] Download complete.")

        # Whisper chuyển giọng nói thành text
        print("[WHISPER] Starting Whisper transcription...")
        trans = whisper_model.transcribe(tmp_path, language="vi", fp16=(device.type=="cuda"))
        text = trans["text"].strip()
        print(f"[WHISPER] Transcribed Text: '{text}'")

        if not text:
            # Trả về kết quả nếu không có văn bản nào được trích xuất
            return {"text_goc": "", "analysis": {"intent": "Uncertain", "items": []}}

        # LLM phân tích
        print("[PHI3] Starting LLM analysis...")
        full_prompt = build_prompt(text)
        
        llm_output_text = generate_text(full_prompt) 
        analysis_json = parse_llm_output(llm_output_text)
        print("[PHI3] analysis complete.")

        result = {
            "audio_url": audio_url,
            "text_goc": text,
            "analysis": analysis_json,
            "time": round(time.time() - start, 2)
        }
        
        RESULTS.append(result)

        try:
            print("==== RESULT TO SEND ====")
            requests.post(f"{WEB_URL}", json=result) 
            print(f"[API] Result sent to external endpoint. {WEB_URL}")
        except Exception as send_e:
            print(f"[API] Failed to send result to external endpoint: {send_e}")

        return {"success": True, "result": result}

    except Exception as e:
        print(f"[API] An error occurred: {str(e)}")
        return {"success": False, "error": str(e)}

    finally:
        # Dọn dẹp file tạm
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)