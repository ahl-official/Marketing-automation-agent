"""
Format the validated report to Markdown and publish it to Notion,
Slack, and Airtable - the Python equivalent of the n8n delivery nodes.
"""

from datetime import datetime, timezone

import requests

from .errors import retry


def _bullets(items):
    return "\n".join(f"- {x}" for x in items or [])


def _fmt_market_shift(m):
    return f"Insight: {m['insight']}\nSource: {m['source_url']}\n"


def _fmt_competitor_move(m):
    return f"Competitor: {m['competitor']}\nAction: {m['action']}\nSource: {m['source_url']}\n"


def _fmt_pain_point(m):
    return f"Pain Point Analysis: {m['insight']}\nSource: {m['source_url']}\n"


def _fmt_trend(m):
    return f"Trend: {m['trend']}\nEvidence: {m['evidence']}\nSource: {m['source_url']}\n"


def _fmt_opportunity(m):
    return f"Opportunity: {m['topic']} (Format: {m['format']} | Urgency: {m['urgency']})\nRationale: {m['rationale']}\n"


def _fmt_source(m):
    return m['url']


def _sourced(items, fmt):
    return "\n".join(fmt(x) for x in items or [])


def format_markdown(report: dict, chunks: list[dict]) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sections = [
        f"# Research Digest - {today}",
        "",
        "## Executive summary",
        _bullets(report.get("executive_summary")),
        "",
        "## Market and industry shifts",
        _sourced(report.get("market_shifts"), _fmt_market_shift),
        "",
        "## Competitor moves",
        _sourced(report.get("competitor_moves"), _fmt_competitor_move),
        "",
        "## Customer pain points",
        _sourced(report.get("customer_pain_points"), _fmt_pain_point),
        "",
        "## Emerging trends",
        _sourced(report.get("emerging_trends"), _fmt_trend),
        "",
        "## Content opportunities",
        _sourced(report.get("content_opportunities"), _fmt_opportunity),
        "## Recommended actions this week",
        _sourced(report.get("recommended_actions"), lambda m: f"Competitor: {m.get('competitor', 'Unknown')}\nAction: {m.get('action', m)}\nSource: {m.get('source_url', '')}\n" if isinstance(m, dict) else str(m)),
        "",
        "## Sources",
        _sourced([{"url": c["url"]} for c in chunks if "url" in c], _fmt_source),
        "",
    ]
    return "\n".join(sections)


def format_markdown(report: dict, chunks: list[dict]) -> str:
    sections = []
    
    url_to_title = {c.get('url'): c.get('source', 'Unknown Competitor') for c in chunks if c.get('url')}
    
    if report.get("executive_summary"):
        sections.append("EXECUTIVE SUMMARY\n")
        for s in report["executive_summary"]:
            sections.append(s)
        sections.append("\n==================================================\n")
            
    def _add_section(title: str, items: list, text_key: str):
        if not items:
            return
        sections.append(f"{title}\n")
        import re
        for m in items:
            url = m.get("source_url", "")
            text = m.get(text_key, '')
            # If it's a trend, we might need to combine trend and evidence
            if text_key == "trend" and "evidence" in m:
                text = f"{m.get('trend', '')} - {m.get('evidence', '')}"
            
            # AI sometimes puts Source_url: in the text instead of the JSON field
            if not url:
                url_match = re.search(r'(https?://[^\s]+)', text)
                if url_match:
                    url = url_match.group(1)
                    # Clean the url from the text
                    text = re.sub(r'Source_url:\s*https?://[^\s]+', '', text, flags=re.IGNORECASE).strip()
                    
            comp_name = m.get("competitor", url_to_title.get(url, "Unknown Competitor"))
            if comp_name == "Unknown Competitor" and url_to_title.get(url):
                comp_name = url_to_title.get(url)
                
            sections.append(comp_name.upper())
            sections.append(text)
            sections.append(f"URL: {url}")
            sections.append("\n--------------------------------------------------\n")
        sections.append("==================================================\n")
            
    _add_section("MARKET SHIFTS", report.get("market_shifts", []), "insight")
    _add_section("COMPETITOR MOVES", report.get("competitor_moves", []), "action")
    _add_section("CUSTOMER PAIN POINTS", report.get("customer_pain_points", []), "insight")
    _add_section("EMERGING TRENDS", report.get("emerging_trends", []), "trend")
    
    if report.get("content_opportunities"):
        sections.append("CONTENT OPPORTUNITIES\n")
        import re
        for m in report["content_opportunities"]:
            url = m.get("source_url", "")
            comp_name = m.get("competitor", url_to_title.get(url, "Unknown Competitor"))
            if comp_name == "Unknown Competitor" and url_to_title.get(url):
                comp_name = url_to_title.get(url)
                
            sections.append(comp_name.upper())
            sections.append(f"Topic: {m.get('topic', '')} ({m.get('format', '')}, {m.get('urgency', '')})")
            sections.append(f"Rationale: {m.get('rationale', '')}")
            sections.append(f"URL: {url}")
            sections.append("\n--------------------------------------------------\n")
        sections.append("==================================================\n")
            
    _add_section("RECOMMENDED ACTIONS", report.get("recommended_actions", []), "action")
            
    return "\n".join(sections)

@retry(max_tries=2, wait_seconds=5, exceptions=(requests.RequestException,))
def publish_google_doc(
    run_date: str, report: dict, chunks: list[dict], apps_script_url: str, apps_script_token: str
) -> str:
    """Send the structured report to Google Apps Script for doc generation."""
    
    formatted_md = format_markdown(report, chunks)

    resp = requests.post(
        apps_script_url,
        params={"token": apps_script_token, "action": "publish_doc"},
        json={"runDate": run_date, "report": report, "formatted_md": formatted_md},
        timeout=30,
    )
    resp.raise_for_status()
    try:
        data = resp.json()
    except Exception:
        raise RuntimeError(f"Google Apps Script did not return JSON. Raw response: {resp.text[:500]}")
    if data.get("error"):
        raise RuntimeError(f"Apps Script doc publish failed: {data['error']}")
    return data["docUrl"]


@retry(max_tries=2, wait_seconds=5, exceptions=(requests.RequestException,))
def publish_slack_digest(report: dict, doc_url: str, slack_bot_token: str, channel: str) -> None:
    summary_lines = "\n".join(f"- {s}" for s in report.get("executive_summary", []))
    text = f"*New research digest is up*\n{summary_lines}\n\nFull report: {doc_url}"
    resp = requests.post(
        "https://slack.com/api/chat.postMessage",
        headers={"Authorization": f"Bearer {slack_bot_token}"},
        json={"channel": channel, "text": text},
        timeout=10,
    )
    resp.raise_for_status()


def update_job_status(apps_script_url: str, token: str, status: str, error: str = "") -> None:
    try:
        requests.post(
            apps_script_url,
            params={"action": "update_status", "token": token},
            json={"status": status, "error": error},
            timeout=15,
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Could not update job status: {e}")


@retry(max_tries=2, wait_seconds=2, exceptions=(requests.RequestException,))
def archive_report_google_sheets(
    report: dict, markdown: str, apps_script_url: str, apps_script_token: str
) -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    resp = requests.post(
        apps_script_url,
        params={"token": apps_script_token, "action": "archive"},
        json={
            "runDate": today,
            "insightSummary": " | ".join(report.get("executive_summary", [])),
            "fullMarkdown": markdown,
        },
        timeout=15,
    )
    resp.raise_for_status()


@retry(max_tries=2, wait_seconds=5, exceptions=(requests.RequestException,))
def read_past_reports_google_sheets(apps_script_url: str, apps_script_token: str) -> list[str]:
    """Read the last 4 weeks of insight summaries for the dedup check."""
    resp = requests.get(
        apps_script_url,
        params={"token": apps_script_token, "action": "read_past"},
        timeout=15,
    )
    resp.raise_for_status()
    records = resp.json().get("records", [])
    return [r.get("insightSummary", "") for r in records if isinstance(r, dict) and "insightSummary" in r]
