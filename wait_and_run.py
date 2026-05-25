import time
import requests
import subprocess
import sys
import argparse

def wait_for_server(url, timeout=3600):
    print(f"Waiting for server at {url}...")
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            # vLLM provides /health endpoint usually, but /models or /v1/models is standard
            response = requests.get(f"{url}/v1/models", timeout=5)
            if response.status_code == 200:
                print("Server is ready!")
                return True
        except requests.exceptions.ConnectionError:
            pass
        except Exception as e:
            # print(f"waiting... ({e})")
            pass
        
        time.sleep(10)
        print(".", end="", flush=True)
    return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    server_url = f"http://localhost:{args.port}"
    if wait_for_server(server_url):
        print("\nServer Ready. Starting evaluation...")
        cmd = [
            "python3", "scripts/run.py",
            "--comp", "problems_will_be_open",
            "--model", "hyperclovax_seed_think_32b_vllm"
        ]
        # We need to make sure the config exists for vllm too
        subprocess.run(cmd, check=True)
    else:
        print("\nServer timed out.")
        sys.exit(1)
