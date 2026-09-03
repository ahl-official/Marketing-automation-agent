import json, requests, os
from dotenv import load_dotenv
load_dotenv('.env')

for model in ['groq/compound', 'openai/gpt-oss-120b', 'qwen/qwen3.6-27b']:
    print(f"Testing {model}...")
    resp = requests.post(
        'https://api.groq.com/openai/v1/chat/completions',
        headers={'Authorization': 'Bearer ' + os.environ.get('GROQ_API_KEY')},
        json={
            'model': model,
            'response_format': {'type': 'json_object'},
            'messages': [{'role': 'user', 'content': 'Output json: {"test": 123}'}]
        }
    )
    print(resp.status_code)
    try:
        print(resp.json())
    except:
        print(resp.text)
    print("-" * 40)
