from math_eval_v7.utils.api_client import APIClient

client = APIClient(
    base_url="http://localhost:1234/v1",
    api_key="not-needed",
    model="deepseek-r1-distill-qwen-32b",
    api_type="openai"
)

messages = [
    {"role": "system", "content": "Always answer in rhymes. Today is Thursday"},
    {"role": "user", "content": "What day is it today?"}
]

print("Sending request...")
response = client.chat_completion(messages, temperature=0.7, max_tokens=-1)
print(f"Response: {response}")
