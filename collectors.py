"""
Data collection branches for the research pipeline.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

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
