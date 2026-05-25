import subprocess
import time
import requests
import sys
import os

def run_server_and_eval():
    print("Starting Fallback Server (simple_server.py)...")
    # Launch simple_server.py
    # This uses transformers library which works well on Mac with device_map="auto"
    server_cmd = [
        "python3", "simple_server.py",
        "--model", "naver-hyperclovax/HyperCLOVAX-SEED-Think-32B",
        "--port", "8000"
    ]
    
    # We run it in the background
    server_process = subprocess.Popen(server_cmd, stdout=sys.stdout, stderr=sys.stderr)
    
    print("Waiting for Server to become ready...")
    # simple_server.py doesn't have /v1/models by default unless we implemented it, 
    # but we can try connecting or wait for log confirmation if we were parsing stdout.
    # We'll use a simple connection check.
    ready = False
    server_url = "http://localhost:8000/v1/chat/completions" # simple_server implements this
    
    # Wait loop
    for i in range(7200): # Wait up to 2 hours (download continues here)
        try:
            if subprocess.poll() is not None:
                print("Server process died!")
                break
            
            # Simple server usually doesn't have a GET endpoint, so we might get 405 Method Not Allowed,
            # which means it's running!
            try:
                response = requests.get("http://localhost:8000/docs", timeout=5)
                if response.status_code == 200:
                    print("\nServer is Ready!")
                    ready = True
                    break
            except:
                pass
                
        except:
            pass
        if i % 6 == 0:
             print(".", end="", flush=True)
        time.sleep(10)

    if ready:
        print("\nStarting Evaluation...")
        # Run evaluation script with the original config (non-vllm) or the vllm one if compatible.
        # simple_server.py mimics OpenAI API so the vllm config might work if we adjust it to use simple_server expectations.
        # But we previously made 'hyperclovax_seed_think_32b.yaml' for this.
        eval_cmd = [
            "python3", "scripts/run.py",
            "--comp", "problems_will_be_open",
            "--model", "hyperclovax_seed_think_32b_vllm" # We can reuse this config as it points to localhost:8000
        ]
        subprocess.run(eval_cmd, check=False)
        
        print("\nEvaluation complete. Cleaning up...")
        server_process.terminate()
    else:
        print("\nFailed to start server.")
        if server_process.poll() is None:
            server_process.terminate()

if __name__ == "__main__":
    run_server_and_eval()
