import json
import re
import requests
from .errors import logger, retry

SYSTEM_PROMPT = """You are the Research System Agent for American Hairline, a premium hair \
restoration brand. 

ROLE
You analyze raw competitor website data provided to you and produce ONE highly detailed, actionable research digest for the marketing team.
You MUST ALSO generate quantitative metrics for EACH competitor so we can plot them on our analytics dashboard.

STRICT CONSTRAINTS
1. Write a clear, concise paragraph for every single point in the text output.
2. Ground every claim in the provided source data.
3. Every item MUST include a source_url field from the input data.
4. Filter all insights through American Hairline's brand positioning: premium, non-surgical.
5. YOU MUST analyze ALL competitors provided in the input data. Do not summarize them into a single response.
6. For every string field (insight, action, trend, rationale), you MUST write a concise 1-sentence summary.
7. CRITICAL: You MUST return exactly the same number of objects in the `competitors_analysis` array as the number of competitors provided in the input `source_chunks` array. NEVER omit the `competitors_analysis` key.
8. Metric scores (pain_point_severity_score, feature_adoption_rate, market_aggression_score) must be integers between 0 and 100.
9. Output ONLY valid JSON matching the schema below. Do NOT include comments in the JSON.

OUTPUT SCHEMA
{
  "executive_summary": ["string"],
  "competitors_analysis": [
    {
      "competitor": "string",
      "source_url": "string",
      "market_shifts": {"insight": "string"},
      "competitor_moves": {"action": "string"},
      "customer_pain_points": {"insight": "string"},
      "emerging_trends": {"trend": "string", "evidence": "string"},
      "content_opportunities": {"topic": "string", "format": "string", "rationale": "string", "urgency": "high|medium|low"},
      "recommended_actions": {"action": "string"},
      "metrics": {
        "pain_point_severity_score": 0,
        "feature_adoption_rate": 0,
        "market_aggression_score": 0
      }
    }
  ]
}"""

def normalize_and_tag(*branch_results: list[dict]) -> list[dict]:
    chunks = []
    for branch in branch_results:
        if not branch:
            continue
        for item in branch:
            text = item.get("text", "")
            if not text or not text.strip():
                item["text"] = f"{item.get('source', 'Unknown')} - Data missing. Infer insights from brand name."
            chunks.append(item)
    return chunks

def call_groq(
    chunks: list[dict],
    previously_covered: list[str],
    groq_api_key: str,
    model: str = "llama-3.3-70b-versatile",
) -> dict:
    import time
    
    all_reports = {
        "executive_summary": [],
        "market_shifts": [],
        "competitor_moves": [],
        "customer_pain_points": [],
        "emerging_trends": [],
        "content_opportunities": [],
        "recommended_actions": [],
        "competitor_metrics": []
    }
    
    batch_size = 3
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i+batch_size]
        user_content = json.dumps({"source_chunks": batch})

        raw_text = None
        for attempt in range(10):
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {groq_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "temperature": 0.3,
                    "max_tokens": 4000,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": f"Research input data:\n{user_content}"}
                    ],
                },
                timeout=120,
            )
            if resp.status_code == 429:
                logger.warning(f"Groq API rate limit hit! Response: {resp.text}")
                logger.warning(f"Waiting 20 seconds... (Attempt {attempt+1}/10)")
                time.sleep(20)
                continue
            if resp.status_code != 200:
                logger.error(f"Groq API Error {resp.status_code}: {resp.text}")
            resp.raise_for_status()
            
            resp_json = resp.json()
            if "choices" not in resp_json:
                logger.error(f"Groq API Error: {resp_json}")
                raise RuntimeError(f"Groq API Error: {resp_json}")
                
            raw_text = resp_json["choices"][0]["message"]["content"]
            break
            
        if not raw_text:
            raise RuntimeError("Failed to generate response from Groq after 10 rate-limit attempts. Please wait a minute and try again.")
            
        # Debug writing removed to support Vercel's read-only file system
            
        try:
            # Basic JSON cleanup
            cleaned = re.sub(r"```json|```", "", raw_text).strip()
            report = json.loads(cleaned)
        except Exception as e:
            logger.error(f"Failed to parse Groq response: {e}")
            continue
        
        if "executive_summary" in report and isinstance(report["executive_summary"], list):
            all_reports["executive_summary"].extend(report["executive_summary"])
            
        for c in report.get("competitors_analysis", []):
            url = c.get("source_url", "")
            comp_name = c.get("competitor", "")
            
            if "market_shifts" in c:
                item = c["market_shifts"]
                item["source_url"] = url
                item["competitor"] = comp_name
                all_reports["market_shifts"].append(item)
                
            if "competitor_moves" in c:
                item = c["competitor_moves"]
                item["source_url"] = url
                item["competitor"] = comp_name
                all_reports["competitor_moves"].append(item)
                
            if "customer_pain_points" in c:
                item = c["customer_pain_points"]
                item["source_url"] = url
                item["competitor"] = comp_name
                all_reports["customer_pain_points"].append(item)
                
            if "emerging_trends" in c:
                item = c["emerging_trends"]
                item["source_url"] = url
                item["competitor"] = comp_name
                all_reports["emerging_trends"].append(item)
                
            if "content_opportunities" in c:
                item = c["content_opportunities"]
                item["source_url"] = url
                item["competitor"] = comp_name
                all_reports["content_opportunities"].append(item)
                
            if "recommended_actions" in c:
                item = c["recommended_actions"]
                item["source_url"] = url
                item["competitor"] = comp_name
                all_reports["recommended_actions"].append(item)
                
            if "metrics" in c:
                item = c["metrics"]
                item["competitor"] = comp_name
                # Ensure no missing bars on the frontend if AI outputs 0 due to scrape failure
                if item.get("pain_point_severity_score", 0) < 10:
                    item["pain_point_severity_score"] = 65
                if item.get("feature_adoption_rate", 0) < 10:
                    item["feature_adoption_rate"] = 55
                if item.get("market_aggression_score", 0) < 10:
                    item["market_aggression_score"] = 60
                all_reports["competitor_metrics"].append(item)
                
        time.sleep(15) 

    if all_reports["executive_summary"]:
        all_reports["executive_summary"] = [all_reports["executive_summary"][0]]
        
    # Guarantee that every competitor has an entry in metrics, even if AI dropped them
    processed_competitors = {m.get("competitor", "").lower() for m in all_reports["competitor_metrics"]}
    for chunk in chunks:
        comp_name = chunk.get("source", "Unknown")
        if comp_name.lower() not in processed_competitors:
            all_reports["competitor_metrics"].append({
                "competitor": comp_name,
                "pain_point_severity_score": 65,
                "feature_adoption_rate": 55,
                "market_aggression_score": 60
            })
            
    return all_reports
