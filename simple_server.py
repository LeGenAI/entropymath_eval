import argparse
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch
import time
import uuid

app = FastAPI()

model = None
tokenizer = None

def load_model(model_name):
    global model, tokenizer
    print(f"Loading model {model_name}...")
    try:
        tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
        # Use device_map="auto" to handle large models via CPU offload if needed
        model = AutoModelForCausalLM.from_pretrained(
            model_name, 
            trust_remote_code=True, 
            device_map="auto", 
            torch_dtype="auto",
            low_cpu_mem_usage=True
        )
        print("Model loaded successfully.")
    except Exception as e:
        print(f"Error loading model: {e}")
        raise e

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    data = await request.json()
    messages = data.get("messages", [])
    model_name = data.get("model", "model")
    max_tokens = data.get("max_tokens", 2048)
    temperature = data.get("temperature", 0.5)
    stop = data.get("stop", [])
    
    if isinstance(stop, str):
        stop = [stop]

    # Ensure chat template exists or use default
    if tokenizer.chat_template:
        prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    else:
        # Fallback for models without template
        prompt = ""
        for m in messages:
            prompt += f"{m['role']}: {m['content']}\n"
        prompt += "assistant: "

    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    
    # Generate
    outputs = model.generate(
        **inputs,
        max_new_tokens=max_tokens,
        temperature=temperature,
        do_sample=True if temperature > 0 else False,
        stop_strings=stop if stop else None,
        tokenizer=tokenizer,
        pad_token_id=tokenizer.eos_token_id
    )
    
    generated_text = tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
    
    return JSONResponse({
        "id": f"chatcmpl-{uuid.uuid4()}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_name,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": generated_text
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": inputs.input_ids.shape[1],
            "completion_tokens": outputs.shape[1] - inputs.input_ids.shape[1],
            "total_tokens": outputs.shape[1]
        }
    })

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, required=True)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    
    load_model(args.model)
    uvicorn.run(app, host="0.0.0.0", port=args.port)
