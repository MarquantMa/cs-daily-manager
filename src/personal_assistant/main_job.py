import argparse
import datetime
import json
import os
import sys

# Import our modules
from apple_integration import get_weekly_plan, update_weekly_plan, get_upcoming_events, get_unread_emails, send_notification
from llm_processor import summarize_emails, organize_tasks


SETTINGS_FILE = os.path.join(os.path.dirname(__file__), 'settings.json')

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'r') as f:
            return json.load(f)
    return {}

def is_time_in_range(time_range_str, current_time):
    if not time_range_str or "-" not in time_range_str:
        return False
    
    try:
        start_str, end_str = time_range_str.split("-")
        start_time = datetime.datetime.strptime(start_str.strip(), "%H:%M").time()
        end_time = datetime.datetime.strptime(end_str.strip(), "%H:%M").time()
        
        if start_time <= end_time:
            return start_time <= current_time <= end_time
        else:
            # Crosses midnight (e.g., 23:00 - 07:00)
            return current_time >= start_time or current_time <= end_time
    except Exception as e:
        print(f"Error parsing time range {time_range_str}: {e}")
        return False

def should_notify():
    settings = load_settings()
    now = datetime.datetime.now()
    day_name = now.strftime("%A")
    current_time = now.time()
    
    day_settings = settings.get(day_name, {})
    sleep_range = day_settings.get("sleep", "")
    class_range = day_settings.get("class", "")
    
    if is_time_in_range(sleep_range, current_time):
        print(f"Currently sleeping ({sleep_range}). Skipping notifications.")
        return False
        
    if is_time_in_range(class_range, current_time):
        print(f"Currently in class ({class_range}). Skipping notifications.")
        return False
        
    return True

def run_assistant():
    print(f"[{datetime.datetime.now()}] Running assistant...")
    
    if not should_notify():
        print("Not an appropriate time to notify. Aborting run so we don't miss unread emails.")
        return

    # 1. Process Emails
    print("Checking emails...")
    unread = get_unread_emails()
    if unread and not unread.startswith("Error") and unread.strip():
        summary = summarize_emails(unread)
        if summary:
            print("Sending email summary notification...")
            send_notification("Mail Summary", "New unread emails", summary)
    
    # 2. Process Tasks
    print("Checking tasks and calendar...")
    upcoming_events = get_upcoming_events(7)
    weekly_plan = get_weekly_plan()
    
    if weekly_plan and "not found" not in weekly_plan:
        reorganized_html = organize_tasks(weekly_plan, upcoming_events)
        if reorganized_html:
            print("Updating Apple Notes...")
            update_weekly_plan(reorganized_html)
            
            # Send notification for tasks
            send_notification("Tasks Organized", "Weekly Plan updated", "Your tasks have been smartly divided and scheduled.")
    
    print("Assistant run complete.")



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Personal Assistant Orchestrator")
    parser.add_argument("--assist", action="store_true", help="Run email and task assistant")
    args = parser.parse_args()
    
    if args.assist:
        run_assistant()
    else:
        print("Please specify --assist")
