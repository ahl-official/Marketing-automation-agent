import sys
import json
import time
from datetime import datetime, timezone

from pipeline.collectors import (
    fetch_competitor_content,
    fetch_config,
    fetch_market_news,
    fetch_social_listening,
    fetch_google_reviews,
    fetch_emerging_trends,
    fetch_youtube_content,
)
from pipeline.config import load_settings
from pipeline.errors import format_exception_alert, logger, post_slack_alert
from pipeline.publish import (
    publish_google_doc,
    update_job_status
)
from pipeline.synthesize import call_groq, normalize_and_tag


def run_job() -> None:
    settings = load_settings()
    
    try:
        competitors, dashboard_settings = fetch_config(settings.apps_script_url, settings.apps_script_token)
    except Exception as e:
        return
        
    schedule = dashboard_settings.get("schedule", "Manual")
    is_scheduled_run = False
    
    if schedule != "Manual":
        last_run = dashboard_settings.get("last_run_timestamp")
        if last_run:
            try:
                last_time = int(last_run) / 1000.0
                hours_passed = (time.time() - last_time) / 3600.0
                if schedule == "Daily" and hours_passed >= 24:
                    is_scheduled_run = True
                elif schedule == "Weekly" and hours_passed >= (24 * 7):
                    is_scheduled_run = True
                elif schedule == "Monthly" and hours_passed >= (24 * 30):
                    is_scheduled_run = True
            except:
                pass
        else:
            is_scheduled_run = True
            
    if dashboard_settings.get("job_status") != "PENDING" and not is_scheduled_run:
        return
        
    if is_scheduled_run and dashboard_settings.get("job_status") != "PENDING":
        try:
            update_job_status(settings.apps_script_url, settings.apps_script_token, "PENDING")
        except:
            pass
        
    logger.info("=== Research Agent job starting ===")
    
    try:
        if not competitors:
            raise RuntimeError("Could not load config - aborting run.")
        logger.info("Config loaded: %s competitors", len(competitors))

        logger.info("Scraping competitor sites...")
        update_job_status(settings.apps_script_url, settings.apps_script_token, "PENDING", progress=10, progress_text="Scraping competitor sites...")
        competitor_content = fetch_competitor_content(competitors)
        logger.info("Collected %s raw competitor items", len(competitor_content))
        
        logger.info("Executing autonomous API collectors...")
        update_job_status(settings.apps_script_url, settings.apps_script_token, "PENDING", progress=50, progress_text="Executing autonomous API collectors...")
        # User requested to ONLY use Instagram scraping to run instantly in one batch
        # if settings.serper_api_key:
        #     competitor_content.extend(fetch_market_news(settings.serper_api_key, settings.geo, competitors))
        #     competitor_content.extend(fetch_social_listening(settings.serper_api_key, settings.geo, competitors))
        #     competitor_content.extend(fetch_emerging_trends(settings.serper_api_key, settings.geo, competitors))
        #     competitor_content.extend(fetch_youtube_content(settings.serper_api_key, settings.geo, competitors))
            
        # if settings.google_places_api_key:
        #     competitor_content.extend(fetch_google_reviews(settings.google_places_api_key, settings.geo, competitors))
            
        logger.info("Total data chunks collected: %s", len(competitor_content))

        chunks = normalize_and_tag(competitor_content)
        logger.info("Calling Groq to synthesize the digest...")
        update_job_status(settings.apps_script_url, settings.apps_script_token, "PENDING", progress=75, progress_text="Calling LLM to synthesize the digest...")
        
        raw_report = call_groq(
            chunks, 
            [], 
            settings.groq_api_key, 
            settings.groq_model
        )

        logger.info("Validation passed. Formatting and publishing...")
        update_job_status(settings.apps_script_url, settings.apps_script_token, "PENDING", progress=90, progress_text="Formatting and publishing Google Doc...")

        # Save a local backup of the report in case Google Docs publishing fails
        with open("report_backup.json", "w", encoding="utf-8") as f:
            json.dump(raw_report, f, indent=2)
        logger.info("Saved local backup to report_backup.json")

        run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        doc_url = publish_google_doc(
            run_date,
            raw_report,
            chunks,
            settings.apps_script_url,
            settings.apps_script_token,
        )
        logger.info("Published Google Doc: %s", doc_url)

        logger.info("=== Research Agent run completed successfully ===")
        
    except Exception as exc:
        logger.critical("Run failed with an unhandled error: %s", exc, exc_info=True)
        update_job_status(settings.apps_script_url, settings.apps_script_token, "IDLE", str(exc))
        if settings.slack_bot_token:
            msg = format_exception_alert("American Hairline Research Agent", exc)
            post_slack_alert(settings.slack_bot_token, settings.slack_alerts_channel, msg)


def run():
    print("Starting background worker. Polling Apps Script for PENDING jobs every 10 seconds...")
    while True:
        try:
            run_job()
        except Exception as e:
            logging.getLogger("research_agent").error(f"Polling error: {e}")
        time.sleep(10)

if __name__ == "__main__":
    run()
