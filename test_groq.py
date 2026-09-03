import json
import sys
from pipeline.config import load_settings
from pipeline.synthesize import SYSTEM_PROMPT
import requests

s = load_settings()
payload = {
    'model': s.groq_model,
    'messages': [
        {'role': 'system', 'content': SYSTEM_PROMPT},
        {'role': 'user', 'content': 'Research input data:\n{"source_chunks": [{"source": "A", "text": "Hair salon offering non-surgical hair replacement in New York. We provide premium service."}]}'}
    ]
}

resp = requests.post(
    'https://api.groq.com/openai/v1/chat/completions',
    headers={'Authorization': 'Bearer ' + s.groq_api_key},
    json=payload
)

with open('test_resp.txt', 'w', encoding='utf-8') as f:
    f.write(resp.text)
print(resp.status_code)
