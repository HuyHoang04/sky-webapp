import fastapi
import uvicorn
import torch
import whisper
import os
import time
import json
import requests
import tempfile
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

app = fastapi.FastAPI()

# ==== DEVICE & DTYPE ====
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print("Using device:", device)

# ==== WHISPER MODEL ====
print("Loading Whisper model...")
whisper_model = whisper.load_model("base", device=device)
print("Whisper model loaded.")

# ==== LLM MODEL CONFIG - 4BIT QUANTIZATION ====
LLM_MODEL_NAME = "microsoft/Phi-3-mini-4k-instruct"

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_use_double_quant=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.float16
)

print("Loading LLM model (this may take a moment)...")
llm_model = AutoModelForCausalLM.from_pretrained(
    LLM_MODEL_NAME,
    quantization_config=bnb_config,
    device_map="auto",
    trust_remote_code=True
)

llm_model.config.use_cache = False
llm_tokenizer = AutoTokenizer.from_pretrained(LLM_MODEL_NAME)
print("LLM model loaded.")

# ==== HELPER GENERATE FUNCTION ====
def generate_text(prompt, max_tokens=512):
    # Di chuyển inputs lên đúng device của model
    inputs = llm_tokenizer(prompt, return_tensors="pt").to(llm_model.device)
    with torch.no_grad():
        output_ids = llm_model.generate(
            **inputs,
            max_new_tokens=max_tokens,
            do_sample=False,
            use_cache=False,
            pad_token_id=llm_tokenizer.eos_token_id
        )
    return llm_tokenizer.decode(output_ids[0], skip_special_tokens=True)

# ==== SYSTEM PROMPT ====
SYSTEM_PROMPT = """<|system|>
Bạn là AI phân tích cứu hộ, chuyên trích xuất ý định (INTENT) và vật dụng (ITEMS) từ lời nói của nạn nhân.
Chỉ trả về JSON.
"""

def build_prompt(text):
    return f"{SYSTEM_PROMPT}\nVăn bản: \"{text}\"\nJSON:\n"

def parse_llm_output(text_output):
    try:
        # Tìm phần JSON trong output của LLM
        json_start = text_output.find("{")
        json_end = text_output.rfind("}") + 1
        
        if json_start == -1 or json_end == 0:
            # Nếu không tìm thấy JSON, trả về lỗi
            return {"error": "No JSON found in LLM output", "raw_output": text_output}
            
        json_str = text_output[json_start:json_end]
        return json.loads(json_str)
    except Exception as e:
        return {"error": str(e), "raw_output": text_output}

RESULTS = []

@app.get("/")
def read_root():
    return {"message": "AI Service is running."}

# ==== ROUTES ====
@app.post("/analyze_from_url/") # ĐÃ SỬA: Thêm dấu / ở cuối
async def analyze_from_url(payload: dict):
    start = time.time()
    audio_url = payload.get("audio_url")

    if not audio_url:
        return {"success": False, "error": "Thiếu audio_url"}

    try:
        # Tải file âm thanh từ URL
        with tempfile.NamedTemporaryFile(delete=False, suffix=".m4a") as tmp:
            r = requests.get(audio_url)
            tmp.write(r.content)
            tmp_path = tmp.name

        # Whisper chuyển giọng nói thành text
        trans = whisper_model.transcribe(tmp_path, language="vi", fp16=(device.type=="cuda"))
        text = trans["text"].strip()

        if not text:
            return {"text_goc": "", "analysis": {"intents": ["KHONG_RO"], "items": {}}}

        # LLM phân tích
        full_prompt = build_prompt(text)
        # Lấy phần text mới do LLM tạo ra
        prompt_len = len(full_prompt)
        llm_output_text = generate_text(full_prompt)[prompt_len:]
        analysis_json = parse_llm_output(llm_output_text)

        result = {
            "audio_url": audio_url,
            "text_goc": text,
            "analysis": analysis_json,
            "time": round(time.time() - start, 2)
        }
        RESULTS.append(result)

        return {"success": True, "result": result}

    except Exception as e:
        # In lỗi ra console server để debug
        print(f"An error occurred: {str(e)}")
        return {"success": False, "error": str(e)}

    finally:
        if 'tmp_path' in locals() and os.path.exists(tmp_path):
            os.remove(tmp_path)

@app.get("/results/")
def get_results():
    return RESULTS

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)