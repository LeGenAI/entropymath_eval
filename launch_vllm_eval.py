import subprocess
import time
import requests
import sys

def run_vllm_and_eval():
    print("Starting vLLM server...")
    # Launch vLLM server
    vllm_cmd = [
        "python3", "-m", "vllm.entrypoints.openai.api_server",
        "--model", "naver-hyperclovax/HyperCLOVAX-SEED-Think-32B",
        "--port", "8000",
        "--trust-remote-code",
        "--dtype", "float16", # Usually safe for MPS/Mac
        "--max-model-len", "4096" # Limit context to save memory on local Mac
    ]
    
    # We run it in the background
    server_process = subprocess.Popen(vllm_cmd, stdout=sys.stdout, stderr=sys.stderr)
    
    print("Waiting for vLLM to become ready...")
    server_url = "http://localhost:8000/v1/models"
    ready = False
    
    # Wait loop
    for _ in range(3600): # Wait up to 1 hour (download might take time)
        try:
            if subprocess.poll() is not None:
                print("Server process died!")
                break
                
            response = requests.get(server_url, timeout=5)
            if response.status_code == 200:
                print("\nvLLM Server is Ready!")
                ready = True
                break
        except:
            pass
        time.sleep(10)
        print(".", end="", flush=True)

    if ready:
        print("\nStarting Evaluation...")
        # Run evaluation script
        eval_cmd = [
            "python3", "scripts/run.py",
            "--comp", "problems_will_be_open",
            "--model", "hyperclovax_seed_think_32b_vllm"
        ]
        subprocess.run(eval_cmd, check=False)
        
        print("\nEvaluation complete. Cleaning up...")
        server_process.terminate()
    else:
        print("\nFailed to start server.")
        if server_process.poll() is None:
            server_process.terminate()

if __name__ == "__main__":
    run_vllm_and_eval()
