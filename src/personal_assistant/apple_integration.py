import subprocess

def run_applescript(script):
    try:
        process = subprocess.Popen(['osascript', '-e', script], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = process.communicate(timeout=5)
        if process.returncode != 0:
            print(f"AppleScript error: {err.decode('utf-8')}")
            return None
        return out.decode('utf-8').strip()
    except subprocess.TimeoutExpired:
        process.kill()
        out, err = process.communicate()
        print("AppleScript timed out after 5 seconds.")
        return None
    except Exception as e:
        print(f"Failed to run AppleScript: {e}")
        return None

def get_weekly_plan():
    script = """
    tell application "Notes"
        try
            set myNote to note "weekly plan"
            return body of myNote
        on error
            return "Note 'weekly plan' not found."
        end try
    end tell
    """
    return run_applescript(script)

def update_weekly_plan(new_content):
    # Apple Notes uses HTML for body content
    # We need to properly escape the string for AppleScript
    escaped_content = new_content.replace('"', '\\"').replace('\n', '')
    script = f"""
    tell application "Notes"
        try
            set myNote to note "weekly plan"
            set body of myNote to "{escaped_content}"
            return "Success"
        on error
            return "Error: Note 'weekly plan' not found."
        end try
    end tell
    """
    return run_applescript(script)

def get_upcoming_events(days=7):
    script = f"""
    set d1 to current date
    set d2 to d1 + ({days} * days)
    set output to ""
    tell application "Calendar"
        repeat with c in calendars
            try
                set evts to (every event of c whose start date is greater than or equal to d1 and start date is less than or equal to d2)
                repeat with e in evts
                    set output to output & "Event: " & summary of e & " (" & start date of e & " - " & end date of e & ")\\n"
                end repeat
            on error
                -- Skip calendars that throw errors
            end try
        end repeat
    end tell
    return output
    """
    return run_applescript(script)

def get_unread_emails():
    script = """
    tell application "Mail"
        set output to ""
        try
            set unreadMsgs to (messages of inbox whose read status is false)
            set count limit to 10
            set counter to 0
            repeat with msg in unreadMsgs
                if counter < count limit then
                    set output to output & "Subject: " & subject of msg & "\\n"
                    set output to output & "Sender: " & extract address from sender of msg & "\\n"
                    set output to output & "Content: " & content of msg & "\\n---\\n"
                    set counter to counter + 1
                    
                    -- Mark as read so we don't process it again next time
                    set read status of msg to true
                end if
            end repeat
        on error
            return "Error reading Mail."
        end try
        return output
    end tell
    """
    return run_applescript(script)

def send_notification(title, subtitle, body):
    # Escape quotes
    title = title.replace('"', '\\"')
    subtitle = subtitle.replace('"', '\\"')
    body = body.replace('"', '\\"')
    script = f'display notification "{body}" with title "{title}" subtitle "{subtitle}"'
    return run_applescript(script)

if __name__ == "__main__":
    # Test cases
    print("Upcoming Events:")
    print(get_upcoming_events(3))
