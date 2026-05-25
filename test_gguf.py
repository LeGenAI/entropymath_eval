from llama_cpp import Llama
import os

model_path = "models/HyperCLOVAX-SEED-Think-14B-Q4_K_M.gguf"
print(f"Loading model from {model_path}...")

try:
    llm = Llama(
        model_path=model_path,
        n_gpu_layers=-1,
        verbose=True
    )
    print("Model loaded successfully!")
except Exception as e:
    print(f"Error loading model: {e}")
