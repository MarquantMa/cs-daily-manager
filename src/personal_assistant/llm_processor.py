import os
import requests
import json
import sys
from dotenv import load_dotenv
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path)

sys_path_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if sys_path_parent not in sys.path:
    sys.path.append(sys_path_parent)

try:
    from ai_module import query_ai
except ImportError:
    query_ai = None

def call_llm(system_prompt, user_prompt):
    full_prompt = f"{system_prompt}\n\n{user_prompt}"
    if query_ai:
        res = query_ai(full_prompt, model_key="Qwen 3.5 9B (Mac Native MLX)")
        if res and not res.startswith("Error") and not res.startswith("Primary error"):
            return res

    deepseek_key = os.getenv("DEEPSEEK_API_KEY", "")
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {deepseek_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "deepseek-v4-flash",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 4096
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=90)
        response.raise_for_status()
        data = response.json()
        return data['choices'][0]['message']['content'].strip()
    except Exception as e:
        print(f"Error calling LLM: {e}")
        return ""

def summarize_emails(email_content):
    if not email_content or "Error" in email_content:
        return ""

    system_prompt = "You are a concise personal assistant. Summarize the provided emails. For each email, provide a summary in 10 words or less. Format the output clearly."
    user_prompt = f"Here are the unread emails:\n\n{email_content}"

    return call_llm(system_prompt, user_prompt)

def organize_tasks(weekly_plan_text, calendar_events):
    if not weekly_plan_text or "not found" in weekly_plan_text:
        weekly_plan_text = "(Empty or not found)"

    system_prompt = """You are a smart task manager.
You will be given a user's current 'weekly plan' (a list of tasks) and their upcoming 'calendar events'.
Your goal is to:
1. Extract all tasks from the weekly plan.
2. Check if any tasks are already scheduled in the calendar. If they are, mark them as scheduled or integrate them.
3. Smartly divide large tasks into smaller, actionable sub-tasks.
4. Arrange them based on implied deadlines or logical ordering.
5. Return ONLY valid HTML that can be pasted into Apple Notes. Use simple tags like <h1>, <ul>, <li>, <b>. Do not include ```html or <html> or <body> tags, just the inner HTML snippet."""

    user_prompt = f"Weekly Plan Tasks:\n{weekly_plan_text}\n\nCalendar Events:\n{calendar_events}\n\nPlease output the reorganized tasks as HTML."

    html_output = call_llm(system_prompt, user_prompt)

    # Strip markdown code blocks if the LLM includes them
    if html_output.startswith("```html"):
        html_output = html_output[7:]
    if html_output.startswith("```"):
        html_output = html_output[3:]
    if html_output.endswith("```"):
        html_output = html_output[:-3]

    return html_output.strip()

if __name__ == "__main__":
    # Quick test
    print("Testing LLM processing...")
    # res = summarize_emails("Subject: Project Meeting\nSender: boss@company.com\nContent: Let's meet at 5pm to discuss the launch.")
    # print(res)
