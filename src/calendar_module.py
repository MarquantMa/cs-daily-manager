import subprocess
import threading
from datetime import datetime, timedelta

def add_calendar_event(title, start_time, end_time, notes="", calendar_name="Calendar"):
    """
    Adds an event to the macOS Calendar using AppleScript.
    Constructs dates programmatically to avoid locale/AM-PM issues.
    Falls back gracefully to the first writable calendar if the specified one is read-only.
    """
    MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    def script_date(dt):
        time_in_seconds = dt.hour * 3600 + dt.minute * 60 + dt.second
        month_name = MONTH_NAMES[dt.month - 1]
        return f'''
            set d to current date
            set day of d to 1
            set year of d to {dt.year}
            set month of d to {month_name}
            set day of d to {dt.day}
            set time of d to {time_in_seconds}
        '''
        
    # Escape double quotes in title/notes for AppleScript
    title = str(title).replace('"', '\\"')
    notes = str(notes).replace('"', '\\"')
    calendar_name = str(calendar_name).strip().replace('"', '\\"')
    
    script = f'''
    tell application "Calendar"
        set targetCal to missing value
        try
            set c to calendar "{calendar_name}"
            if writable of c is true then
                set targetCal to c
            end if
        end try
        
        if targetCal is missing value then
            repeat with c in calendars
                try
                    if writable of c is true and (name of c is not "Birthdays") and (name of c is not "Scheduled Reminders") and (name of c is not "Siri Suggestions") then
                        set targetCal to c
                        exit repeat
                    end if
                end try
            end repeat
        end if
        
        if targetCal is missing value then
            set targetCal to first calendar
        end if
        
        -- Create start date object
        {script_date(start_time)}
        set startDate to d
        
        -- Create end date object
        {script_date(end_time)}
        set endDate to d
        
        tell targetCal
            make new event with properties {{summary:"{title}", start date:startDate, end date:endDate, description:"{notes}"}}
        end tell
    end tell
    '''
    
    try:
        subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=True, timeout=10)
        return True, None
    except subprocess.TimeoutExpired:
        return False, "Request timed out after 10 seconds."
    except subprocess.CalledProcessError as e:
        return False, e.stderr

from concurrent.futures import ThreadPoolExecutor, as_completed

def normalize_iso_datetime(dt_str):
    """Normalize unpadded date string (e.g. 2026-9-9 7:5:0) to YYYY-MM-DD HH:MM:SS."""
    if not dt_str:
        return ""
    try:
        parts = dt_str.strip().split(" ")
        if len(parts) >= 2:
            y, m, d = [int(x) for x in parts[0].split("-")]
            hr, mn, sc = [int(x) for x in parts[1].split(":")]
            return f"{y:04d}-{m:02d}-{d:02d} {hr:02d}:{mn:02d}:{sc:02d}"
    except Exception:
        pass
    return dt_str

def get_all_user_calendars():
    """
    Returns exact names of all user calendars from Apple Calendar for event reading.
    Filters out system, holiday, and Siri suggestion calendars without mangling whitespace.
    """
    script = '''
    tell application "Calendar"
        set out to ""
        repeat with c in calendars
            set out to out & (name of c) & "<|||>"
        end repeat
        return out
    end tell
    '''
    try:
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=True, timeout=8)
        raw = result.stdout.strip()
        if not raw:
            return ["Calendar"]
        names = [n for n in raw.split("<|||>") if n]
        skip_keywords = ["holiday", "public holidays", "birthday", "siri suggestions"]
        filtered = [n for n in names if not any(k in n.lower() for k in skip_keywords)]
        return filtered or ["Calendar"]
    except Exception as e:
        print(f"Error fetching user calendars: {e}")
        return ["Calendar"]

def _fetch_single_calendar_events(cal_name):
    """Fetch events for a single calendar for today."""
    clean_cal = str(cal_name).replace('"', '\\"')
    script = f'''
    set now to (current date)
    set todayStart to now - (time of now)
    set todayEnd to todayStart + 86400
    tell application "Calendar"
        try
            set c to calendar "{clean_cal}"
            set evs to (every event of c whose (start date ≥ todayStart and start date < todayEnd))
            set out to ""
            repeat with e in evs
                set sDate to start date of e
                set eDate to end date of e
                set s_iso to (year of sDate as string) & "-" & (month of sDate as integer as string) & "-" & (day of sDate as string) & " " & (hours of sDate as string) & ":" & (minutes of sDate as string) & ":" & (seconds of sDate as string)
                set e_iso to (year of eDate as string) & "-" & (month of eDate as integer as string) & "-" & (day of eDate as string) & " " & (hours of eDate as string) & ":" & (minutes of eDate as string) & ":" & (seconds of eDate as string)
                set out to out & (summary of e) & "|||" & s_iso & "|||" & e_iso & "\\n"
            end repeat
            return out
        on error
            return ""
        end try
    end tell
    '''
    try:
        res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=20)
        return res.stdout.strip()
    except Exception:
        return ""

def get_today_events():
    """
    Fetches today's events from macOS Calendar across all active user calendars.
    Uses ThreadPoolExecutor with controlled worker pool to prevent AppleEvents congestion.
    Returns a list of dictionaries with title, start_iso, end_iso, calendar, and is_reminder.
    """
    cals = get_all_user_calendars()
    events = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(_fetch_single_calendar_events, cal): cal for cal in cals}
        for future in as_completed(futures):
            cal = futures[future]
            try:
                raw = future.result()
                if raw:
                    cleaned = raw.replace('\\\\n', '\n').replace('\\n', '\n')
                    for line in cleaned.split('\n'):
                        line = line.strip()
                        if "|||" in line:
                            parts = line.split("|||")
                            if len(parts) >= 3:
                                events.append({
                                    "title": parts[0],
                                    "start_iso": normalize_iso_datetime(parts[1]),
                                    "end_iso": normalize_iso_datetime(parts[2]),
                                    "calendar": cal.strip(),
                                    "is_reminder": False
                                })
            except Exception:
                pass
    events.sort(key=lambda x: x.get("start_iso", ""))
    return events

def get_calendar_names():
    """
    Returns a list of writable calendar names from Apple Calendar.
    Filters out read-only subscribed calendars, system, holiday, and Siri suggestion calendars.
    """
    script = 'tell application "Calendar" to get name of every calendar'
    try:
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=True, timeout=5)
        raw = result.stdout.strip()
        if not raw: return ["Personal", "Calendar"]
        names = [n.strip() for n in raw.split(",") if n.strip()]
        read_only_keywords = ["holiday", "public holidays", "canvas", "blue schedule", "birthday", "siri", "scheduled"]
        filtered = [n for n in names if not any(k in n.lower() for k in read_only_keywords)]
        return filtered or ["Personal", "Calendar"]
    except Exception as e:
        print(f"Error fetching calendar names: {e}")
        return ["Personal", "Calendar"]

def get_reminder_lists():
    """
    Returns a list of reminder list names from macOS Reminders.
    """
    script = 'tell application "Reminders" to get name of every list'
    try:
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=True, timeout=12)
        raw = result.stdout.strip()
        if not raw: return []
        return [n.strip() for n in raw.split(",") if n.strip()]
    except Exception as e:
        print(f"Error fetching reminder lists: {e}")
        return []

def _fetch_single_reminder_list(list_name):
    """Fetch uncompleted reminders from a single list using fast bulk name retrieval."""
    script = f'''
    tell application "Reminders"
        try
            set l to list "{list_name}"
            set remNames to name of (every reminder of l whose completed is false)
            set out to ""
            repeat with n in remNames
                set out to out & (n as string) & "|||" & "{list_name}" & "\\n"
            end repeat
            return out
        on error
            return ""
        end try
    end tell
    '''
    try:
        res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=6)
        return res.stdout.strip()
    except Exception:
        return ""

def get_macos_reminders():
    """
    Fetches all uncompleted reminders from macOS Reminders in parallel.
    Deduplicates identical tasks from duplicate list mirrors.
    Returns a list of dictionaries with title, list, and is_reminder.
    """
    raw_lists = get_reminder_lists()
    seen_lists = set()
    lists = []
    for l in raw_lists:
        if l not in seen_lists:
            seen_lists.add(l)
            lists.append(l)

    reminders = []
    seen_rems = set()
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(_fetch_single_reminder_list, l_name): l_name for l_name in lists}
        for future in as_completed(futures):
            l_name = futures[future]
            try:
                raw = future.result()
                if raw:
                    cleaned = raw.replace('\\\\n', '\n').replace('\\n', '\n')
                    for line in cleaned.split('\n'):
                        line = line.strip()
                        if "|||" in line:
                            parts = line.split("|||")
                            if len(parts) >= 2:
                                rem_key = (parts[0].strip(), parts[1].strip())
                                if rem_key not in seen_rems:
                                    seen_rems.add(rem_key)
                                    reminders.append({
                                        "title": parts[0],
                                        "list": parts[1],
                                        "is_reminder": True
                                    })
            except Exception as e:
                print(f"Error fetching reminders for {l_name}: {e}")
    return reminders

def update_calendar_event(old_title=None, old_start=None, new_title=None, new_start=None, new_end=None, new_notes="", calendar_name="Calendar", **kwargs):
    """
    Updates an existing calendar event using AppleScript.
    Accepts flexible keyword arguments for compatibility.
    """
    target_title = old_title or kwargs.get("target_title") or ""
    target_start = old_start or kwargs.get("target_start_date") or kwargs.get("target_start") or datetime.now()
    updated_title = new_title or kwargs.get("new_title") or target_title
    updated_start = new_start or kwargs.get("new_start_time") or kwargs.get("new_start") or target_start
    updated_end = new_end or kwargs.get("new_end_time") or kwargs.get("new_end") or (updated_start + timedelta(hours=1))
    updated_notes = new_notes if new_notes is not None else kwargs.get("notes", "")

    def script_date(dt):
        time_in_seconds = dt.hour * 3600 + dt.minute * 60 + dt.second
        return f'''
            set d to current date
            set day of d to 1
            set year of d to {dt.year}
            set month of d to {dt.month}
            set day of d to {dt.day}
            set time of d to {time_in_seconds}
        '''

    clean_old_title = str(target_title).replace('"', '\\"')
    clean_new_title = str(updated_title).replace('"', '\\"')
    clean_notes = str(updated_notes).replace('"', '\\"')
    calendar_name = str(calendar_name).strip().replace('"', '\\"')
    
    script = f'''
    tell application "Calendar"
        try
            set theCalendar to calendar "{calendar_name}"
        on error
            set theCalendar to first calendar
        end try
        
        {script_date(updated_start)}
        set newStart to d
        {script_date(updated_end)}
        set newEnd to d
        
        set evs to (every event of theCalendar whose summary is "{clean_old_title}")
        if (count of evs) > 0 then
            set theEvent to first item of evs
            set summary of theEvent to "{clean_new_title}"
            set start date of theEvent to newStart
            set end date of theEvent to newEnd
            set description of theEvent to "{clean_notes}"
            return "success"
        else
            return "Event not found"
        end if
    end tell
    '''
    try:
        res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=True, timeout=10)
        out = res.stdout.strip()
        if "success" in out:
            return True, None
        return False, out
    except subprocess.TimeoutExpired:
        return False, "Request timed out after 10 seconds."
    except subprocess.CalledProcessError as e:
        return False, e.stderr

def add_macos_reminder(title, list_name="Homework and study", due_date=None, notes=""):
    """
    Creates a new reminder in Apple Reminders app using AppleScript.
    """
    def script_date(dt):
        time_in_seconds = dt.hour * 3600 + dt.minute * 60 + dt.second
        return f'''
            set d to current date
            set year of d to {dt.year}
            set month of d to {dt.month}
            set day of d to {dt.day}
            set time of d to {time_in_seconds}
        '''

    clean_title = title.replace('"', '\\"')
    clean_notes = notes.replace('"', '\\"')
    clean_list = list_name.replace('"', '\\"')

    if due_date:
        script = f'''
        tell application "Reminders"
            try
                set theList to list "{clean_list}"
            on error
                set theList to default list
            end try
            {script_date(due_date)}
            make new reminder at theList with properties {{name:"{clean_title}", body:"{clean_notes}", due date:d}}
            return "success"
        end tell
        '''
    else:
        script = f'''
        tell application "Reminders"
            try
                set theList to list "{clean_list}"
            on error
                set theList to default list
            end try
            make new reminder at theList with properties {{name:"{clean_title}", body:"{clean_notes}"}}
            return "success"
        end tell
        '''

    try:
        res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=True, timeout=10)
        return True, None
    except subprocess.TimeoutExpired:
        return False, "Request timed out after 10 seconds."
    except subprocess.CalledProcessError as e:
        return False, e.stderr
    except Exception as e:
        return False, str(e)

def complete_macos_reminder(title, list_name=None):
    """Mark a reminder as completed in Apple Reminders via background AppleScript."""
    def run_bg():
        clean_title = title.replace('"', '\\"')
        if list_name:
            clean_list = list_name.replace('"', '\\"')
            script = f'''
            tell application "Reminders"
                try
                    set theList to list "{clean_list}"
                    set rems to (every reminder of theList whose completed is false and name is "{clean_title}")
                    repeat with r in rems
                        set completed of r to true
                    end repeat
                end try
            end tell
            '''
        else:
            script = f'''
            tell application "Reminders"
                try
                    repeat with l in lists
                        set remNames to name of (every reminder of l whose completed is false)
                        repeat with i from 1 to count of remNames
                            if (item i of remNames) is "{clean_title}" then
                                set completed of (item i of (every reminder of l whose completed is false)) to true
                                exit repeat
                            end if
                        end repeat
                    end repeat
                end try
            end tell
            '''
        try:
            subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
        except Exception as e:
            print(f"Background reminder completion warning: {e}")

    threading.Thread(target=run_bg, daemon=True).start()
    return True, None

def uncomplete_macos_reminder(title, list_name=None):
    """Mark a reminder as incomplete in Apple Reminders via background AppleScript."""
    def run_bg():
        clean_title = title.replace('"', '\\"')
        if list_name:
            clean_list = list_name.replace('"', '\\"')
            script = f'''
            tell application "Reminders"
                try
                    set theList to list "{clean_list}"
                    set rems to (every reminder of theList whose completed is true and name is "{clean_title}")
                    repeat with r in rems
                        set completed of r to false
                    end repeat
                end try
            end tell
            '''
        else:
            script = f'''
            tell application "Reminders"
                try
                    repeat with l in lists
                        set remNames to name of (every reminder of l whose completed is true)
                        repeat with i from 1 to count of remNames
                            if (item i of remNames) is "{clean_title}" then
                                set completed of (item i of (every reminder of l whose completed is true)) to false
                                exit repeat
                            end if
                        end repeat
                    end repeat
                end try
            end tell
            '''
        try:
            subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
        except Exception as e:
            print(f"Background reminder uncompletion warning: {e}")

    threading.Thread(target=run_bg, daemon=True).start()
    return True, None

def batch_complete_macos_reminders(titles):
    """Batch mark multiple reminders as completed."""
    for t in titles:
        complete_macos_reminder(t)
    return True, None

def batch_uncomplete_macos_reminders(titles):
    """Batch mark multiple reminders as incomplete."""
    for t in titles:
        uncomplete_macos_reminder(t)
    return True, None

