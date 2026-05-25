import sys
import os
import torch

print(f"Torch version: {torch.__version__}")
print(f"MPS available: {torch.backends.mps.is_available()}")

try:
    from vllm import LLM, SamplingParams
    print("vLLM imported successfully.")
except ImportError as e:
    print(f"Failed to import vLLM: {e}")
    # Try finding vllm path as per guide
    import subprocess
    try:
        vllm_path = subprocess.check_output(["which", "vllm"]).decode().strip()
        print(f"Found vllm at: {vllm_path}")
        # Add parent dir
        sys.path.append(os.path.dirname(os.path.dirname(vllm_path)))
        from vllm import LLM, SamplingParams
        print("vLLM imported successfully after path append.")
    except Exception as e2:
        print(f"Failed to fix import: {e2}")

if 'LLM' in locals():
    print("vLLM module is ready.")
