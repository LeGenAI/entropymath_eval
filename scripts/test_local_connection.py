import os
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:1234/v1",
    api_key="not-needed"
)

model = "exaone-4.0-32b"

print(f"Attempting to connect to {client.base_url} with model {model}...")

try:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "user", "content": "Hello! Are you working?"}
        ],
        temperature=0.7,
        max_tokens=100
    )
    print("Success!")
    print("Response:", response.choices[0].message.content)
except Exception as e:
    print("Error occurred:")
    print(e)
