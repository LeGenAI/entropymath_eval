
from math_eval_v7.utils.api_client import APIClient
import yaml

def test_llama():
    config = {
        "model": "llama-varco-8b-instruct",
        "base_url": "http://localhost:1234/v1",
        "api_key": "not-needed",
        "temperature": 0.3,
        "max_tokens": 100,
        "stop": ["Observation:", "<|call|>", "[/PYTHON]", "[PYTHON]"]
    }
    
    client = APIClient(
        base_url=config["base_url"],
        api_key=config["api_key"],
        model=config["model"]
    )
    
    print("Sending test request to Llama Varco...")
    messages = [{"role": "user", "content": "What is 1+1?"}]
    
    # Remove model, base_url, api_key from config before passing as kwargs
    run_config = config.copy()
    run_config.pop("model", None)
    run_config.pop("base_url", None)
    run_config.pop("api_key", None)
    
    try:
        response = client.chat_completion(messages=messages, **run_config)
        print(f"Response: {response}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_llama()
