import json
from pipeline.synthesize import call_groq
from pipeline.config import load_settings

def test_prompt():
    settings = load_settings()
    
    chunks = [
        {
            "source": "Competitor A",
            "type": "website",
            "url": "https://competitor-a.com",
            "text": "Competitor A provides surgical hair transplants. We offer FUE and FUT at an affordable price."
        },
        {
            "source": "Competitor B",
            "type": "website",
            "url": "https://competitor-b.com",
            "text": "Competitor B provides premium non-surgical hair systems for men."
        },
        {
            "source": "Google News",
            "type": "market_news",
            "url": "https://news.com/hair",
            "text": "The market is shifting towards non-surgical options."
        }
    ]
    
    report = call_groq(chunks, [], settings.groq_api_key, settings.groq_model)
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    test_prompt()
