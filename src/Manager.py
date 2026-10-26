import sys
import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

import threading
import shutil
from datetime import datetime
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QMessageBox
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon, QFont

from dashboard_module import Dashboard

# Import the personal assistant background automation jobs
sys.path.append(os.path.join(os.path.dirname(__file__), "personal_assistant"))
try:
    from main_job import run_assistant
except ImportError:
    run_assistant = None


import subprocess

def send_desktop_notification(title, subtitle, body):
    """
    Sends a native macOS notification with sound using AppleScript in a daemon thread.
    Operates while the application is active/open.
    """
    def _notify():
        try:
            clean_title = str(title).replace('"', '\\"')
            clean_sub = str(subtitle).replace('"', '\\"')
            clean_body = str(body).replace('"', '\\"')
            script = f'display notification "{clean_body}" with title "{clean_title}" subtitle "{clean_sub}" sound name "default"'
            subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
        except Exception as e:
            print(f"Notification error: {e}")

    threading.Thread(target=_notify, daemon=True).start()


class ManagerApp(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        self.check_dependencies()
        self.setWindowTitle("AI Daily Assistant")

        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "app_icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.setMinimumSize(1020, 700)
        self.resize(1200, 820)

        # Main Single-Window Dashboard Layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.dashboard = Dashboard()
        main_layout.addWidget(self.dashboard)

        # Automation Timer (Runs in background at scheduled hours)
        self.automation_timer = QTimer(self)
        self.automation_timer.timeout.connect(self.check_automation_schedule)
        self.automation_timer.start(60000)
        self.last_assistant_run = None
        self.last_booking_run = None

        # Live Notifications Manager (Active while application is open)
        self.notified_items = set()
        self.notified_weather_alerts = set()
        self.last_tomorrow_briefing_date = None
        self.known_event_signatures = set()

        self.notification_timer = QTimer(self)
        self.notification_timer.timeout.connect(self.check_live_notifications)
        self.notification_timer.start(60000)  # Check every 60s
        QTimer.singleShot(4000, self.check_live_notifications)  # Initial check 4s after startup

    def check_live_notifications(self):
        """
        Monitors events, reminders, weather, and tomorrow's classes while the app is open.
        Sends native macOS notifications for imminent items, critical weather, or new tasks.
        """
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")

        # 1. Critical Weather Monitoring
        weather = getattr(self.dashboard, 'current_weather_data', None)
        if weather:
            rain_prob = weather.get("rain_prob_3h") or weather.get("rain_prob_6h") or 0
            try:
                rain_val = int(rain_prob)
            except Exception:
                rain_val = 0

            code = weather.get("code", 0)
            aqi = weather.get("aqi", 0)
            try:
                aqi_val = int(aqi)
            except Exception:
                aqi_val = 0

            city = weather.get('city', 'your area')

            if rain_val >= 50:
                alert_key = f"rain_{today_str}_{rain_val // 25}"
                if alert_key not in self.notified_weather_alerts:
                    self.notified_weather_alerts.add(alert_key)
                    send_desktop_notification(
                        "Critical Weather Alert",
                        f"High Rain Risk ({rain_val}%)",
                        f"Rain forecasted today in {city}. Don't forget an umbrella!"
                    )

            if code in range(95, 100):
                alert_key = f"storm_{today_str}"
                if alert_key not in self.notified_weather_alerts:
                    self.notified_weather_alerts.add(alert_key)
                    send_desktop_notification(
                        "Severe Weather Alert",
                        "Thunderstorm Warning",
                        f"Thunderstorms reported in {city}. Stay indoors if possible."
                    )

            if aqi_val >= 100:
                alert_key = f"aqi_{today_str}"
                if alert_key not in self.notified_weather_alerts:
                    self.notified_weather_alerts.add(alert_key)
                    send_desktop_notification(
                        "Air Quality Alert",
                        f"Elevated AQI ({aqi_val})",
                        "Air quality is poor today. Consider limiting outdoor exercise."
                    )

        # 2. Upcoming Schedule & Reminders Imminent Approach
        events = getattr(self.dashboard, 'current_displayed_events', []) or []
        for ev in events:
            start_iso = ev.get('start_iso', '')
            try:
                parts = start_iso.strip().split(" ")
                if len(parts) >= 2:
                    dp = [int(x) for x in parts[0].split("-")]
                    tp = [int(x) for x in parts[1].split(":")]
                    dt = datetime(dp[0], dp[1], dp[2], tp[0], tp[1], tp[2])
                else:
                    dt = now
            except Exception:
                dt = now

            diff_mins = (dt - now).total_seconds() / 60.0
            item_id = f"{ev.get('title', '')}_{start_iso}"

            # Within 1 hour notification
            if 0 <= diff_mins <= 60 and f"{item_id}_1h" not in self.notified_items:
                self.notified_items.add(f"{item_id}_1h")
                kind = "Reminder" if ev.get('is_reminder') else f"Event ({ev.get('calendar', 'Calendar')})"
                send_desktop_notification(
                    "Upcoming Schedule Alert",
                    f"{kind}: {ev.get('title')}",
                    f"Starts in {int(diff_mins)} minutes at {dt.strftime('%H:%M')}."
                )
            # Within 3 hours notification
            elif 60 < diff_mins <= 180 and f"{item_id}_3h" not in self.notified_items:
                self.notified_items.add(f"{item_id}_3h")
                kind = "Reminder" if ev.get('is_reminder') else f"Event ({ev.get('calendar', 'Calendar')})"
                send_desktop_notification(
                    "Upcoming Schedule (< 3h)",
                    f"{kind}: {ev.get('title')}",
                    f"Scheduled for {dt.strftime('%H:%M')} today."
                )

        # 3. New Event / Reminder Detection Notification
        current_signatures = {f"{ev.get('title', '')}_{ev.get('start_iso', '')}" for ev in events if ev.get('title')}
        if self.known_event_signatures:
            new_items = current_signatures - self.known_event_signatures
            for sig in new_items:
                for ev in events:
                    if f"{ev.get('title', '')}_{ev.get('start_iso', '')}" == sig:
                        kind = "Reminder" if ev.get('is_reminder') else "Calendar Event"
                        cal_name = ev.get('calendar', 'Calendar')
                        send_desktop_notification(
                            f"New {kind} Added",
                            ev.get('title', 'New Item'),
                            f"Scheduled at {ev.get('start_iso', '')[11:16]} ({cal_name})"
                        )
                        break
        self.known_event_signatures = current_signatures

        # 4. Tomorrow's Schedule / Classes Evening Briefing (between 19:30 and 22:30)
        if 19 <= now.hour <= 22 and self.last_tomorrow_briefing_date != now.date():
            self.last_tomorrow_briefing_date = now.date()
            threading.Thread(target=self._check_tomorrow_classes_async, daemon=True).start()

    def _check_tomorrow_classes_async(self):
        """Queries tomorrow's classes and sends an evening briefing notification."""
        script = '''
        set now to (current date)
        set tomorrowStart to (now - (time of now)) + 86400
        set tomorrowEnd to tomorrowStart + 86400
        tell application "Calendar"
            set out to ""
            repeat with c in calendars
                set cName to name of c
                if cName contains "Class Schedule" or cName is "Study" then
                    try
                        set evs to (every event of c whose start date ≥ tomorrowStart and start date < tomorrowEnd)
                        repeat with e in evs
                            set sDate to start date of e
                            set h to hours of sDate as string
                            set m to minutes of sDate as string
                            if (count of m) is 1 then set m to "0" & m
                            set out to out & (summary of e) & " (" & h & ":" & m & ")|"
                        end repeat
                    end try
                end if
            end repeat
            return out
        end tell
        '''
        try:
            res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=12)
            raw = res.stdout.strip()
            if raw:
                items = [x.strip() for x in raw.split("|") if x.strip()]
                class_items = [x for x in items if "roll call" not in x.lower() and "dorm" not in x.lower()]
                target_items = class_items or items
                if target_items:
                    summary_text = f"You have {len(target_items)} classes scheduled tomorrow. First: {target_items[0]}."
                    send_desktop_notification(
                        "Tomorrow's Classes Briefing",
                        f"{len(target_items)} Sessions Scheduled",
                        summary_text
                    )
        except Exception as e:
            print(f"Error checking tomorrow classes: {e}")

    def check_automation_schedule(self):
        now = datetime.now()
        if now.minute == 0:
            if self.last_assistant_run != now.hour:
                self.last_assistant_run = now.hour
                if run_assistant:
                    print("Triggering scheduled Assistant run...")
                    threading.Thread(target=run_assistant, daemon=True).start()



    def check_dependencies(self):
        if not shutil.which("ffmpeg"):
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Critical)
            msg.setWindowTitle("Missing Dependency")
            msg.setText("FFmpeg is missing!")
            msg.setInformativeText(
                "This app requires FFmpeg to process audio.\n\n"
                "Please install it using Homebrew:\n'brew install ffmpeg'\n\n"
                "Or download it from ffmpeg.org."
            )
            msg.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg.exec()

    def closeEvent(self, event):
        if hasattr(self, 'dashboard') and getattr(self.dashboard, 'is_recording', False):
            print("Closing window mid-recording. Gracefully finalizing stream...")
            self.dashboard.recorder.stop()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Global modern readable font
    default_font = QFont("SF Pro Text", 14)
    default_font.setStyleHint(QFont.StyleHint.SansSerif)
    app.setFont(default_font)

    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "app_icon.png")
    if os.path.exists(icon_path):
        app_icon = QIcon(icon_path)
        app.setWindowIcon(app_icon)
        if sys.platform == "darwin":
            try:
                from AppKit import NSApplication, NSImage
                ns_img = NSImage.alloc().initWithContentsOfFile_(os.path.abspath(icon_path))
                NSApplication.sharedApplication().setApplicationIconImage_(ns_img)
            except Exception as e:
                print("Could not set macOS Dock icon:", e)

    if sys.platform == "darwin":
        app.setDesktopSettingsAware(True)

    # Security Authentication Dialog (Touch ID & Master Password)
    from login_dialog import LoginDialog
    login_dialog = LoginDialog(is_dark_mode=True)
    if login_dialog.exec() != LoginDialog.DialogCode.Accepted:
        print("Security authentication canceled. Exiting application.")
        sys.exit(0)

    window = ManagerApp()
    window.show()
    sys.exit(app.exec())