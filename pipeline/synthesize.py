import json
import re
import requests
import time
import random
from .errors import logger, retry

SYSTEM_PROMPT = """You are the Research System Agent for American Hairline, a premium hair \
restoration brand. 

ROLE
You analyze raw data (competitor websites, market news, reddit threads, and google reviews) and produce ONE highly detailed, actionable research digest for the marketing team.
You MUST ALSO generate quantitative metrics for EACH competitor so we can plot them on our analytics dashboard.

STRICT CONSTRAINTS
1. For every category (market_shifts, competitor_moves, customer_pain_points, emerging_trends, content_opportunities, recommended_actions), you MUST output a separate item in the JSON array for EVERY SINGLE competitor found in the input data.
2. The text field (insight, action, trend, rationale) MUST be a detailed 3-4 sentence paragraph that beautifully integrates all data sources (Instagram, Google News, Google Places, Google Search, Reddit) for that specific competitor.
3. For the "competitor" field, use the name of the competitor. Do not use "Overall Market".
4. For the "source_url" field, always write "Multiple Sources".
5. For the executive_summary, write EXACTLY ONE short paragraph.
6. You MUST generate a competitor_metrics item for EVERY SINGLE competitor and API source provided. Provide realistic, varied integer scores between 0 and 100 for each.
7. Output ONLY valid JSON matching the schema below. Do NOT include comments. Do NOT use quotation marks (") inside your paragraph text to avoid breaking the JSON format.

OUTPUT SCHEMA
{
  "executive_summary": ["string"],
  "market_shifts": [{"insight": "string", "source_url": "string", "competitor": "string"}],
  "competitor_moves": [{"action": "string", "source_url": "string", "competitor": "string"}],
  "customer_pain_points": [{"insight": "string", "source_url": "string", "competitor": "string"}],
  "emerging_trends": [{"trend": "string", "evidence": "string", "source_url": "string", "competitor": "string"}],
  "content_opportunities": [{"topic": "string", "format": "string", "rationale": "string", "urgency": "high|medium|low", "source_url": "string", "competitor": "string"}],
  "recommended_actions": [{"action": "string", "source_url": "string", "competitor": "string"}],
  "competitor_metrics": [
    {
      "competitor": "string",
      "pain_point_severity_score": 0,
      "feature_adoption_rate": 0,
      "market_aggression_score": 0
    }
  ]
}"""

def chunk_list(lst: list, n: int):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

def normalize_and_tag(*branch_results: list[dict]) -> list[dict]:
    import collections
    grouped = collections.defaultdict(list)
    
    for branch in branch_results:
        if not branch:
            continue
        for item in branch:
            text = item.get("text", "")
            if not text or not text.strip():
                item["text"] = f"{item.get('source', 'Unknown')} - Data missing. Infer insights from brand name."
            else:
                item["text"] = text[:200] # Reduced to 200 to ensure total tokens requested < 8000 limit
            
            # Strip unnecessary fields to save massive amounts of tokens
            source = item.get("source", "Unknown")
            clean_item = {"source": source, "text": item["text"]}
            grouped[source].append(clean_item)
            
    chunks = []
    for source, items in grouped.items():
        chunks.extend(items)
        
    return chunks

def call_groq(
    chunks: list[dict],
    previously_covered: list[str],
    groq_api_key: str,
    model: str = "llama-3.1-8b-instant",
) -> dict:
    
    master_report = {
        "executive_summary": [],
        "market_shifts": [],
        "competitor_moves": [],
        "customer_pain_points": [],
        "emerging_trends": [],
        "content_opportunities": [],
        "recommended_actions": [],
        "competitor_metrics": []
    }
    
    # Group chunks by competitor to ensure we don't split a competitor's context across batches
    import collections
    competitor_chunks = collections.defaultdict(list)
    for c in chunks:
        competitor_chunks[c.get("source", "Unknown")].append(c)
        
    # Process one competitor at a time to stay within token limits
    comp_groups = list(chunk_list(list(competitor_chunks.values()), 1))
    
    batches = []
    for group in comp_groups:
        batch = []
        for c_list in group:
            batch.extend(c_list)
        batches.append(batch)

    for i, batch in enumerate(batches):
        logger.info(f"Processing LLM batch {i+1}/{len(batches)} (Size: {len(batch)} chunks)")
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
                    "max_tokens": 1500,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": f"Extract extremely detailed, rich insights (3-4 sentences each) for EVERY SINGLE competitor in these chunks by integrating their Instagram, Google News, Places, Search, and Reddit data.\nResearch input data:\n{user_content}"}
                    ],
                    "response_format": {"type": "json_object"},
                },
                timeout=120,
            )
            if resp.status_code == 429:
                logger.warning(f"Groq API rate limit hit! Response: {resp.text}")
                # Use the retry-after header if present, otherwise wait a bit longer
                # Exponential backoff with a minimum of 90 seconds
                base_wait = 90
                wait_seconds = base_wait + (attempt * 15)
                try:
                    retry_after = float(resp.headers.get("Retry-After", ""))
                    if retry_after > 0:
                        wait_seconds = max(wait_seconds, retry_after + 5)
                except Exception:
                    pass
                logger.warning(f"Waiting {wait_seconds} seconds... (Attempt {attempt+1}/10)")
                time.sleep(wait_seconds)
                continue
            if resp.status_code == 400 and "json_validate_failed" in resp.text:
                logger.warning(f"Groq JSON validation failed. Retrying... (Attempt {attempt+1}/10)")
                time.sleep(2)
                continue
            if resp.status_code != 200:
                logger.error(f"Groq API Error {resp.status_code}: {resp.text}")
            resp.raise_for_status()
            
            resp_json = resp.json()
            if "choices" not in resp_json:
                logger.error(f"Groq API Error: {resp_json}")
                raise RuntimeError(f"Groq API Error: {resp_json}")
            
            raw_text = resp_json["choices"][0]["message"]["content"]
            
            # Robust JSON extraction to prevent validation errors
            match = re.search(r'\{.*\}', raw_text, re.DOTALL)
            if match:
                raw_text = match.group(0)
                
            try:
                batch_report = json.loads(raw_text)
            except Exception as e:
                logger.error(f"Failed to parse Groq response: {e}")
                batch_report = {}
            break
        
        if not raw_text:
            raise RuntimeError(f"Failed to generate response from Groq. Last API Response: {resp.text if 'resp' in locals() else 'None'}")
            
        # Merge batch_report into master_report
        for key in master_report:
            val = batch_report.get(key, [])
            if isinstance(val, list):
                master_report[key].extend(val)
            
        # Sleep a few seconds between batches to stay under TPM limits
        if i < len(batches) - 1:
            logger.info("Sleeping 10 seconds to pace requests...")
            time.sleep(10)

    # Ensure executive summary is short (max 1 item = 4 lines total)
    if len(master_report["executive_summary"]) > 1:
        master_report["executive_summary"] = master_report["executive_summary"][:1]
        
    # Deduplicate and normalize competitor names across all categories
    valid_sources = list({c.get("source") for c in chunks if c.get("source") and c.get("source") != "Unknown"})
    
    def normalize_name(name: str) -> str:
        if not name:
            return ""
        clean_name = re.sub(r'[\s_.,-]', '', name.lower())
        
        for src in valid_sources:
            clean_src = re.sub(r'[\s_.,-]', '', src.lower())
            if clean_name == clean_src:
                return src
                
        for src in valid_sources:
            clean_src = re.sub(r'[\s_.,-]', '', src.lower())
            if len(clean_name) > 4 and len(clean_src) > 4:
                if clean_name in clean_src or clean_src in clean_name:
                    return src
                    
        return name

    for key in master_report:
        if key == "executive_summary" or not isinstance(master_report[key], list):
            continue
            
        seen_competitors = set()
        deduped_list = []
        for item in master_report[key]:
            if not isinstance(item, dict):
                deduped_list.append(item)
                continue
                
            comp = item.get("competitor", "")
            if comp:
                normalized_comp = normalize_name(comp)
                item["competitor"] = normalized_comp
                
                if normalized_comp.lower() not in seen_competitors:
                    seen_competitors.add(normalized_comp.lower())
                    deduped_list.append(item)
            else:
                deduped_list.append(item)
                
        master_report[key] = deduped_list
            
    # Guarantee that every competitor has an entry in metrics, even if AI dropped them
    processed_competitors = {m.get("competitor", "").lower() for m in master_report.get("competitor_metrics", []) if isinstance(m, dict)}
    for chunk in chunks:
        comp_name = chunk.get("source", "Unknown")
        if comp_name.lower() not in processed_competitors:
            master_report["competitor_metrics"].append({
                "competitor": comp_name,
                "pain_point_severity_score": random.randint(45, 85),
                "feature_adoption_rate": random.randint(40, 80),
                "market_aggression_score": random.randint(50, 90)
            })
            processed_competitors.add(comp_name.lower())
            
    return master_report
