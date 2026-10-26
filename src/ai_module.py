import json
import threading
import requests
from datetime import datetime
import os

_ai_lock = threading.Lock()

# Load credentials from .env if available, or fallback to user provided
from dotenv import load_dotenv
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if not os.path.exists(dotenv_path):
    dotenv_path = os.path.join(os.path.dirname(__file__), 'personal_assistant', '.env')
load_dotenv(dotenv_path)

API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
MLX_MODELS = {
    "Qwen 2.5 7B (Mac Native MLX)": "mlx-community/Qwen2.5-7B-Instruct-4bit",
    "Qwen 2.5 3B (Mac Native MLX)": "mlx-community/Qwen2.5-3B-Instruct-4bit"
}

_mlx_cache = {}

def query_mlx(prompt, model_repo="mlx-community/Qwen2.5-7B-Instruct-4bit"):
    global _mlx_cache
    from mlx_lm import load, generate
    if model_repo not in _mlx_cache:
        print(f"Loading native Apple MLX model '{model_repo}' in Python...")
        _mlx_cache[model_repo] = load(model_repo)

    model, tokenizer = _mlx_cache[model_repo]

    if hasattr(tokenizer, "apply_chat_template"):
        messages = [{"role": "user", "content": prompt}]
        try:
            formatted_prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        except Exception:
            formatted_prompt = prompt
    else:
        formatted_prompt = prompt

    return generate(model, tokenizer, prompt=formatted_prompt, max_tokens=4096, verbose=False)

def query_ai(prompt, model_key="Smart Auto-Select"):
    deepseek_key = os.getenv("DEEPSEEK_API_KEY", "")
    silicon_key = os.getenv("SILICONFLOW_API_KEY", deepseek_key)

    if model_key == "Smart Auto-Select":
        model_key = "Deepseek V4 flash"

    if model_key in MLX_MODELS:
        repo = MLX_MODELS[model_key]
        try:
            with _ai_lock:
                return query_mlx(prompt, repo)
        except Exception as e:
            print(f"Native MLX model '{model_key}' unavailable ({e}), using cloud API...")
            model_key = "Deepseek V4 flash"

    with _ai_lock:
        if "SiliconFlow" in model_key:
            api_base = "https://api.siliconflow.cn/v1"
            api_key = silicon_key
            model_name = "Qwen/Qwen2.5-7B-Instruct"
        elif model_key == "V4 Pro (cloud)":
            api_base = "https://api.deepseek.com/v1"
            api_key = deepseek_key
            model_name = "deepseek-v4-pro"
        elif "Localhost" in model_key or "Ollama" in model_key:
            api_base = "http://localhost:11434/v1"
            api_key = "ollama"
            model_name = "qwen2.5:7b"
        else:
            api_base = "https://api.deepseek.com/v1"
            api_key = deepseek_key
            model_name = "deepseek-chat"

        url = f"{api_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 4096
        }
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=90)
            response.raise_for_status()
            return response.json()['choices'][0]['message']['content'].strip()
        except Exception as e:
            return f"Error querying {model_name}: {e}"

def generate_daily_advice(weather_data, model_key="Smart Auto-Select"):
    """
    Generate dynamic AI daily advice incorporating:
    - Current temperature and weather condition
    - Rain/precipitation probability within the next 1-6 hours
    - Air Quality Index (AQI) and UV index
    - Dynamic, helpful recommendations for outfit, commute, umbrella, and daily planning
    """
    city = weather_data.get("city", "Current Location")
    temp = weather_data.get("temp", 20)
    code = weather_data.get("code", 0)
    aqi = weather_data.get("aqi", 50)
    uv = weather_data.get("uv", 3)
    rain_prob_3h = weather_data.get("rain_prob_3h", 0)
    rain_prob_6h = weather_data.get("rain_prob_6h", 0)
    forecast_summary = weather_data.get("forecast_summary", "")

    # Quick rule-based fallback
    def build_fallback_advice():
        lines = []
        if temp < 10:
            lines.append(f"It's cold at {temp}°C. Wear a thick coat and warm layers.")
        elif temp < 20:
            lines.append(f"Moderate {temp}°C weather. A light jacket or sweater is recommended.")
        else:
            lines.append(f"Warm at {temp}°C! Comfortable t-shirt weather.")

        if rain_prob_3h >= 40:
            lines.append(f"High chance of rain ({rain_prob_3h}%) within the next 3 hours. Bring an umbrella!")
        elif rain_prob_6h >= 30:
            lines.append(f"Light precipitation possible later today (~{rain_prob_6h}% in 6h). Keep an umbrella handy.")
        elif code in range(51, 68) or code in range(80, 83):
            lines.append("Rain is currently reported in the area. Take an umbrella.")

        if uv >= 6:
            lines.append(f"High UV Index ({uv}). Wear sunglasses and apply sunscreen.")
        if aqi >= 100:
            lines.append(f"Sensitive air quality (AQI {aqi}). Consider wearing a mask outdoors.")

        if not lines:
            lines.append("Weather conditions look pleasant! Have a productive and great day ahead.")
        return "\n".join(lines)

    prompt = f"""You are an intelligent, friendly daily personal assistant.
Give concise, dynamic, practical daily advice (2 to 3 sentences maximum) for the user today based on the following real-time weather and forecast data in {city}:
- Temperature: {temp}°C
- Rain/Precipitation Probability (Next 3 Hours): {rain_prob_3h}%
- Rain/Precipitation Probability (Next 6 Hours): {rain_prob_6h}%
- Air Quality Index (AQI): {aqi}
- UV Index: {uv}
- Weather Condition Notes: {forecast_summary or 'Standard daily pattern'}

Guidelines:
1. Specifically mention the rain forecast if precipitation chance is notable (e.g., 'Rain expected within 3 hours (60% chance) — don't forget an umbrella!').
2. Suggest appropriate clothing (layers, coat, or light wear).
3. If UV or AQI is elevated, mention brief protective advice.
4. Keep it friendly, clear, and concise. Do NOT include emojis, markdown code fences or conversational greetings."""

    try:
        response = query_ai(prompt, model_key=model_key)
        if response and not response.startswith("Error querying") and len(response) > 20:
            return response.strip()
    except Exception as e:
        print("AI daily advice generation failed, falling back:", e)

    return build_fallback_advice()


def get_system_context():
    now = datetime.now()
    day_name = now.strftime("%A")
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%I:%M %p (%H:%M)")

    location_str = "Philadelphia, United States"
    try:
        project_dir = os.path.dirname(os.path.abspath(__file__))
        cache_file = os.path.join(project_dir, "exports", "dashboard_cache.json")
        if os.path.exists(cache_file):
            with open(cache_file, "r") as f:
                cdata = json.load(f)
                wdata = cdata.get("weather", {})
                if wdata.get("city"):
                    location_str = f"{wdata['city']}"
    except Exception:
        pass

    return f"""CURRENT REAL-TIME CONTEXT:
- Date: {date_str} ({day_name})
- Time: {time_str}
- Location: {location_str}
Use this exact date, day of week, time, and location context when resolving relative time references (such as 'today', 'tomorrow', 'next Monday', 'tonight', '3 PM', 'in 2 hours')."""

def extract_todo(text, model_key="Qwen 3.5 9B (Mac Native MLX)"):
    context = get_system_context()
    prompt = f"""{context}

Extract a structured todo list from the following text.
Only include tasks with their time details and notes.
Format the output as a clean list, without extra prompts or details.
I want you to extract the todo list in a clean format as follows:

Time:
Event:
Notes:

Arrange the todo list in the order of time.

Text: "{text}"

Todo List:"""
    return query_ai(prompt, model_key)

def extract_calendar_event(text, model_key="Smart Auto-Select"):
    """
    Tries to extract multiple items (both calendar events and reminders/tasks).
    Returns JSON string with a LIST of item objects.
    """
    context = get_system_context()
    prompt = f"""{context}

Extract ALL event and task/reminder details from this text for system calendar or reminder entries (either adding new items or updating existing ones).
Output ONLY a JSON LIST of objects with these keys:
- "item_type": "calendar" for scheduled events/meetings/appointments with specific time bounds, OR "reminder" for to-dos, tasks, or reminders without fixed event duration.
- "action": "add" or "update" (use "update" if text explicitly asks to change, move, update, reschedule, or modify an existing item)
- "title": (the title of the event or reminder)
- "start_time": (for calendar events, the start time e.g. "3:00 PM"; for reminders, the due time if specified)
- "end_time": (for calendar events, the end time e.g. "4:00 PM")
- "notes": (the description/notes)
- "date": (YYYY-MM-DD or 'today')
- "old_title": (ONLY if action is "update", exact existing title)
- "old_start_time": (ONLY if action is "update", exact existing start time)

CRITICAL RULES:
1. Categorize item_type correctly as "calendar" or "reminder".
2. Preserve AM/PM if spoken.
3. If no end time for calendar event, assume 1 hour after start.

Text: "{text}"

JSON List:"""
    return query_ai(prompt, model_key)

def construct_diary(text, model_key="Smart Auto-Select"):
    context = get_system_context()
    prompt = f"""{context}

Turn the following spoken transcript into a beautiful, coherent diary entry.
Keep it personal and reflective, but fix the grammar and structure.
Don't add anything the user didn't say, just polish it.

Transcript: "{text}"

Diary Entry:"""
    return query_ai(prompt, model_key)

def suggest_calendar(title, notes, calendar_list):
    """
    Given an event title, notes, and a list of Apple Calendar names,
    uses the AI model to suggest which calendar to place it in.
    """
    if not calendar_list:
        return "Calendar"

    calendars_str = ", ".join(calendar_list)
    prompt = f"""You are a smart calendar organizer.
Given the following event details:
Title: "{title}"
Description/Notes: "{notes}"

And a list of available Apple Calendar names in the system: [{calendars_str}]

Which calendar from the list is the best fit for this event? Select exactly one calendar name from the list.
Return ONLY the selected calendar name from the list, with no extra formatting, quotes, or explanation."""

    suggestion = query_ai(prompt, model_key="Deepseek V4 flash")
    suggested = suggestion.strip().strip('"').strip("'").strip()

    if suggested in calendar_list:
        return suggested

    for cal in calendar_list:
        if cal.lower() == suggested.lower():
            return cal

    for cal in calendar_list:
        if cal.lower() in suggested.lower() or suggested.lower() in cal.lower():
            return cal

    return calendar_list[0]

def suggest_reminder_list(title, notes, list_names):
    """
    Given a reminder title, notes, and a list of Apple Reminder list names,
    suggests which list to place it in.
    """
    if not list_names:
        return "Homework and study"
    lists_str = ", ".join(list_names)
    prompt = f"""You are a task organizer.
Reminder title: "{title}"
Description: "{notes}"
Available Apple Reminder list names: [{lists_str}]

Which list name is the best fit? Return ONLY one list name from the available list names with no extra text or quotes."""
    try:
        suggestion = query_ai(prompt, model_key="Deepseek V4 flash")
        suggested = suggestion.strip().strip('"').strip("'").strip()
        for l_name in list_names:
            if l_name.lower() == suggested.lower() or l_name.lower() in suggested.lower():
                return l_name
    except Exception:
        pass
    return list_names[0]

