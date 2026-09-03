"""
Data collection branches for the research pipeline.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import json
import requests
from bs4 import BeautifulSoup

from .errors import logger, retry, safe_branch


@safe_branch(default=([], {}))
@retry(max_tries=3, wait_seconds=4, exceptions=(requests.RequestException,))
def fetch_config(apps_script_url: str, token: str) -> tuple[list[dict], dict]:
    """Fetch active competitors and dashboard settings from Google Apps Script."""
    resp = requests.get(
        apps_script_url,
        params={"action": "config", "token": token},
        timeout=30
    )
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"Config API returned an error: {data['error']}")
    
    rows = data.get("rows", [])
    settings = data.get("settings", {})
    
    competitors = []
    for r in rows:
        if r.get("name") and r.get("url"):
            competitors.append({
                "name": str(r["name"]).strip(), 
                "url": str(r["url"]).strip(),
                "modules": r.get("modules", {})
            })
            
    return competitors, settings


@safe_branch(default=[])
def fetch_competitor_content(competitors: list[dict]) -> list[dict]:
    """Branch: scrape each competitor site and extract clean text."""

    @retry(max_tries=2, wait_seconds=5, exceptions=(requests.RequestException,))
    def scrape_one(comp: dict) -> dict | None:
        url = comp["url"]
        name = comp["name"]
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0 ResearchAgent/1.0"})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        body_text = soup.get_text(separator=" ", strip=True)
        return {
            "source": name,
            "type": "competitor",
            "url": url,
            "date": datetime.now(timezone.utc).isoformat(),
            "text": body_text[:500],
        }

    results = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(scrape_one, comp): comp for comp in competitors}
        for fut in futures:
            try:
                res = fut.result()
                if res:
                    results.append(res)
                else:
                    raise Exception("Scraper returned None")
            except Exception as e:
                comp = futures[fut]
                logger.warning(f"Failed to scrape competitor {comp['url']}: {e}")
                results.append({
                    "source": comp["name"],
                    "type": "competitor",
                    "url": comp["url"],
                    "date": datetime.now(timezone.utc).isoformat(),
                    "text": f"{comp['name']} ({comp['url']}) - Data could not be scraped (likely blocked). Please infer marketing insights based on their brand name and their platform.",
                })
    return results


def _safe_scrape(fn, comp):
    try:
        return fn(comp)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to scrape %s: %s", comp.get("url"), exc)
        return None

@safe_branch(default=[])
def fetch_market_news(api_key: str, geo: str, competitors: list[dict]) -> list[dict]:
    """Search Google News for specific competitor market shifts."""
    if not api_key: return []
    url = "https://google.serper.dev/news"
    results = []
    
    def fetch_one(comp):
        payload = json.dumps({"q": f"{comp['name']} hair restoration", "gl": geo.split(',')[0].lower()})
        headers = {'X-API-KEY': api_key, 'Content-Type': 'application/json'}
        resp = requests.post(url, headers=headers, data=payload, timeout=15)
        resp.raise_for_status()
        return resp.json(), comp['name']
        
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(fetch_one, comp) for comp in competitors]
        for fut in futures:
            try:
                data, name = fut.result()
                for item in data.get("news", [])[:1]:
                    results.append({
                        "source": name,
                        "type": "market_news",
                        "url": item.get("link", ""),
                        "date": datetime.now(timezone.utc).isoformat(),
                        "text": f"Google News for {name}: {item.get('title')}. {item.get('snippet')}",
                    })
            except Exception:
                pass
    return results

@safe_branch(default=[])
def fetch_social_listening(api_key: str, geo: str, competitors: list[dict]) -> list[dict]:
    """Search Reddit/Quora for specific competitor customer pain points."""
    if not api_key: return []
    url = "https://google.serper.dev/search"
    results = []
    
    def fetch_one(comp):
        payload = json.dumps({"q": f"(site:reddit.com OR site:quora.com) {comp['name']} hair", "gl": geo.split(',')[0].lower()})
        headers = {'X-API-KEY': api_key, 'Content-Type': 'application/json'}
        resp = requests.post(url, headers=headers, data=payload, timeout=15)
        resp.raise_for_status()
        return resp.json(), comp['name']
        
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(fetch_one, comp) for comp in competitors]
        for fut in futures:
            try:
                data, name = fut.result()
                for item in data.get("organic", [])[:1]:
                    results.append({
                        "source": name,
                        "type": "social_listening",
                        "url": item.get("link", ""),
                        "date": datetime.now(timezone.utc).isoformat(),
                        "text": f"Reddit discussion for {name}: {item.get('title')}. {item.get('snippet')}",
                    })
            except Exception:
                pass
    return results

@safe_branch(default=[])
def fetch_emerging_trends(api_key: str, geo: str, competitors: list[dict]) -> list[dict]:
    """Search Google for competitor-specific trends and search results."""
    if not api_key: return []
    url = "https://google.serper.dev/search"
    results = []
    
    def fetch_one(comp):
        payload = json.dumps({"q": f"{comp['name']} hair transplant reviews", "gl": geo.split(',')[0].lower()})
        headers = {'X-API-KEY': api_key, 'Content-Type': 'application/json'}
        resp = requests.post(url, headers=headers, data=payload, timeout=15)
        resp.raise_for_status()
        return resp.json(), comp['name']
        
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(fetch_one, comp) for comp in competitors]
        for fut in futures:
            try:
                data, name = fut.result()
                for item in data.get("organic", [])[:1]:
                    results.append({
                        "source": name,
                        "type": "emerging_trends",
                        "url": item.get("link", ""),
                        "date": datetime.now(timezone.utc).isoformat(),
                        "text": f"Google Search Result for {name}: {item.get('title')}. {item.get('snippet')}",
                    })
            except Exception:
                pass
    return results

@safe_branch(default=[])
def fetch_google_reviews(api_key: str, geo: str, competitors: list[dict]) -> list[dict]:
    """Search Google Places for specific competitor local reviews."""
    if not api_key: return []
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.displayName,places.rating,places.userRatingCount",
        "Content-Type": "application/json"
    }
    results = []
    
    def fetch_one(comp):
        payload = {"textQuery": f"{comp['name']} hair restoration clinic"}
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        return resp.json(), comp['name']
        
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(fetch_one, comp) for comp in competitors]
        for fut in futures:
            try:
                data, name = fut.result()
                for place in data.get("places", [])[:1]:
                    display_name = place.get("displayName", {}).get("text")
                    rating = place.get("rating")
                    total_ratings = place.get("userRatingCount")
                    if display_name and rating:
                        results.append({
                            "source": name,
                            "type": "local_reviews",
                            "url": f"https://maps.google.com/?q={display_name}",
                            "date": datetime.now(timezone.utc).isoformat(),
                            "text": f"Google Places Review for {name}: Rating {rating}/5 based on {total_ratings} reviews.",
                        })
            except Exception:
                pass
    return results

@safe_branch(default=[])
def fetch_youtube_content(api_key: str, geo: str, competitors: list[dict]) -> list[dict]:
    """Search YouTube via Serper API for competitor video content."""
    if not api_key: return []
    url = "https://google.serper.dev/videos"
    results = []
    
    def fetch_one(comp):
        payload = json.dumps({"q": f"{comp['name']} hair", "gl": geo.split(',')[0].lower()})
        headers = {'X-API-KEY': api_key, 'Content-Type': 'application/json'}
        resp = requests.post(url, headers=headers, data=payload, timeout=15)
        resp.raise_for_status()
        return resp.json(), comp['name']
        
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(fetch_one, comp) for comp in competitors]
        for fut in futures:
            try:
                data, name = fut.result()
                for item in data.get("videos", [])[:1]:
                    results.append({
                        "source": name,
                        "type": "youtube_content",
                        "url": item.get("link", ""),
                        "date": datetime.now(timezone.utc).isoformat(),
                        "text": f"YouTube video for {name}: {item.get('title')}. {item.get('snippet')}",
                    })
            except Exception:
                pass
    return results
