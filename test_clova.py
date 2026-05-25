import os

from math_eval_v7.utils.api_client import APIClient

client = APIClient(
    base_url="https://clovastudio.stream.ntruss.com/v3/chat-completions/HCX-007",
    api_key=os.environ["CLOVA_STUDIO_API_KEY"],
    api_type="clova"
)

messages = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "What is 2 + 2? Answer briefly."}
]

print("Sending request...")
response = client.chat_completion(messages)
print(f"Response: {response}")
