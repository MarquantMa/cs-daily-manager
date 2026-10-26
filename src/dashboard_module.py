import sys
import os
import json
import requests
import time
import math
import threading
from datetime import datetime, timedelta

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QFileDialog, QMessageBox, QButtonGroup,
    QTextEdit, QLineEdit, QComboBox, QGroupBox,
    QDateEdit, QDialog, QListView
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, QSize, QDate, QObject
from PyQt6.QtGui import (
    QFont, QColor, QPixmap, QIcon, QPainter, QImageReader,
    QBrush, QLinearGradient
)

from settings_dialog import SettingsDialog
from recording_history import add_or_update_recording, save_transcription
from recording_history_dialog import RecordingHistoryDialog
from recorder_module import Recorder
from transcriber_module import transcribe
from ai_module import (
    generate_daily_advice, extract_todo, extract_calendar_event,
    suggest_calendar, suggest_reminder_list
)
from calendar_module import (
    get_today_events, get_macos_reminders, complete_macos_reminder,
    uncomplete_macos_reminder, batch_complete_macos_reminders,
    add_calendar_event, update_calendar_event, add_macos_reminder,
    get_calendar_names, get_reminder_lists
)
from timeline_widget import CalendarTimelineViewWidget

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")




class BatchImportDialog(QDialog):
    def __init__(self, parent=None, is_dark_mode=True):
        super().__init__(parent)
        self.is_dark_mode = is_dark_mode
        self.setWindowTitle("Batch Import Schedule")
        self.setMinimumSize(600, 400)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(16)

        lbl = QLabel("Paste your class schedule or event list below:")
        lbl.setStyleSheet("color: white; font-weight: bold; font-size: 15px;" if self.is_dark_mode else "color: black; font-weight: bold; font-size: 15px;")
        layout.addWidget(lbl)

        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("Paste schedule here... (e.g. 14:25-15:05 IB Economics SL on Tuesday)")
        self.text_edit.setStyleSheet("font-size: 15px; padding: 10px;")
        layout.addWidget(self.text_edit)

        btn_layout = QHBoxLayout()
        self.parse_btn = QPushButton("Parse & Import Schedule")
        self.parse_btn.setStyleSheet("""
            QPushButton {
                background-color: #007AFF; color: white; border-radius: 8px; padding: 10px 20px; font-weight: bold; font-size: 15px;
            }
            QPushButton:hover {
                background-color: #0063CC;
            }
        """)
        self.parse_btn.clicked.connect(self.accept)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setStyleSheet("font-size: 15px; padding: 10px 18px; font-weight: bold;")
        self.cancel_btn.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.parse_btn)
        layout.addLayout(btn_layout)

    def get_text(self):
        return self.text_edit.toPlainText().strip()


# --- Workers for Async Data Fetching ---

class WeatherWorker(QThread):
    finished = pyqtSignal(dict)

    def _get_ip_location(self):
        """Detect user location automatically via IP geolocation API."""
        try:
            r = requests.get('http://ip-api.com/json/', timeout=3)
            data = r.json()
            if data.get('status') == 'success':
                city_str = f"{data.get('city', '')}, {data.get('country', '')}".strip(', ')
                return data['lat'], data['lon'], city_str
        except Exception as e:
            print("ip-api error:", e)

        try:
            r = requests.get('https://ipapi.co/json/', timeout=3)
            data = r.json()
            if 'latitude' in data:
                city_str = f"{data.get('city', '')}, {data.get('country_name', '')}".strip(', ')
                return data['latitude'], data['longitude'], city_str
        except Exception as e:
            print("ipapi error:", e)

        return None

    def run(self):
        try:
            loc = self._get_ip_location()
            if loc:
                lat, lon, city = loc
                print(f"DEBUG: Detected location -> {city} ({lat}, {lon})")
            else:
                print("Location detection fallback. Using default location (Chengdu).")
                lat, lon, city = 30.66, 104.06, "Qingyang, Chengdu"

            # Fetch Current & Hourly Weather with Precipitation Forecast
            w_url = (
                f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                f"&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
                f"&hourly=precipitation_probability,precipitation,weather_code,temperature_2m,uv_index"
                f"&daily=uv_index_max&timezone=auto"
            )
            w_resp = requests.get(w_url, timeout=5)
            w_data = w_resp.json()

            # Air Quality API
            aq_url = f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={lat}&longitude={lon}&current=us_aqi,pm2_5"
            aq_resp = requests.get(aq_url, timeout=5)
            aq_data = aq_resp.json()

            # Calculate Precipitation Forecast in next 3h and 6h
            hourly = w_data.get("hourly", {})
            times = hourly.get("time", [])
            probs = hourly.get("precipitation_probability", [])

            now_iso = datetime.now().strftime("%Y-%m-%dT%H:00")
            curr_idx = 0
            for idx, t in enumerate(times):
                if t >= now_iso:
                    curr_idx = idx
                    break

            probs_3h = probs[curr_idx:curr_idx+3] if probs else [0]
            probs_6h = probs[curr_idx:curr_idx+6] if probs else [0]
            rain_prob_3h = max(probs_3h) if probs_3h else 0
            rain_prob_6h = max(probs_6h) if probs_6h else 0

            # Short summary of forecast
            code = w_data.get("current", {}).get("weather_code", 0)
            cond_map = {
                0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
                45: "Fog", 48: "Depositing rime fog", 51: "Light drizzle", 53: "Moderate drizzle",
                55: "Dense drizzle", 61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
                71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow", 80: "Rain showers",
                81: "Moderate showers", 82: "Violent rain showers", 95: "Thunderstorm"
            }
            forecast_summary = cond_map.get(code, "Clear")

            result = {
                "city": city,
                "temp": w_data["current"]["temperature_2m"],
                "humidity": w_data["current"]["relative_humidity_2m"],
                "wind": w_data["current"]["wind_speed_10m"],
                "code": code,
                "uv": w_data["daily"]["uv_index_max"][0] if "daily" in w_data and w_data["daily"]["uv_index_max"] else 0,
                "aqi": aq_data.get("current", {}).get("us_aqi", 45),
                "pm25": aq_data.get("current", {}).get("pm2_5", 15),
                "rain_prob_3h": rain_prob_3h,
                "rain_prob_6h": rain_prob_6h,
                "forecast_summary": forecast_summary
            }
            self.finished.emit(result)
        except Exception as e:
            print(f"Weather Worker Fatal Error: {e}")
            self.finished.emit({
                "city": "Los Angeles, United States (Node)",
                "temp": 19,
                "humidity": 65,
                "wind": 6,
                "code": 1,
                "uv": 4,
                "aqi": 42,
                "pm25": 12,
                "rain_prob_3h": 0,
                "rain_prob_6h": 5,
                "forecast_summary": "Mainly clear"
            })


class DailyAdviceWorker(QThread):
    finished = pyqtSignal(str)

    def __init__(self, weather_data, model_key="Smart Auto-Select"):
        super().__init__()
        self.weather_data = weather_data
        self.model_key = model_key

    def run(self):
        try:
            advice = generate_daily_advice(self.weather_data, model_key=self.model_key)
            self.finished.emit(advice)
        except Exception as e:
            print("DailyAdviceWorker error:", e)
            self.finished.emit("Have a wonderful and productive day ahead!")


class AudioProcessingWorker(QThread):
    status_signal = pyqtSignal(str)
    result_signal = pyqtSignal(str, str, str)  # (result_text, mode, source_file)
    events_signal = pyqtSignal(str, str)       # (events_json, transcript)
    finished_signal = pyqtSignal()
    error_signal = pyqtSignal(str)

    def __init__(self, audio_file, model_key="Smart Auto-Select"):
        super().__init__()
        self.audio_file = audio_file
        self.model_key = model_key

    def run(self):
        try:
            mode = "todo"
            add_or_update_recording(self.audio_file, status="Transcribing", mode=mode)
            self.status_signal.emit("Status: Transcribing speech with Whisper...")

            transcript = transcribe(self.audio_file)
            if not transcript or transcript.startswith("Error"):
                self.status_signal.emit(f"Status: Transcription Error ({transcript})")
                self.finished_signal.emit()
                return

            save_transcription(self.audio_file, transcript)
            self.result_signal.emit(f"TRANSCRIPTION:\n{transcript}\n\n[Extracting Tasks & Events with AI...]", mode, self.audio_file)

            self.status_signal.emit("Status: Extracting Tasks & Events (AI)...")
            todo_list = extract_todo(transcript, self.model_key)
            formatted_output = f"EXTRACTED TASKS & TO-DOs:\n{todo_list}\n\n" + "="*40 + f"\nORIGINAL TRANSCRIPT:\n{transcript}"
            self.result_signal.emit(formatted_output, mode, self.audio_file)

            self.status_signal.emit("Status: Checking calendar & reminders...")
            events_json = extract_calendar_event(transcript, self.model_key)
            self.events_signal.emit(events_json or "[]", transcript)

            self.status_signal.emit("Status: Ready")
            self.finished_signal.emit()
        except Exception as e:
            self.error_signal.emit(str(e))
            self.finished_signal.emit()


def parse_event_datetime(dt_str, fallback_now=None):
    if not dt_str:
        return fallback_now or datetime.now()
    dt_str = dt_str.replace(" at ", " ").strip()
    try:
        parts = dt_str.split(" ")
        if len(parts) >= 2:
            date_p = [int(x) for x in parts[0].split("-")]
            time_p = [int(x) for x in parts[1].split(":")]
            return datetime(date_p[0], date_p[1], date_p[2], time_p[0], time_p[1], time_p[2])
    except Exception:
        pass
    return fallback_now or datetime.now()


class CalendarWorker(QThread):
    finished = pyqtSignal(list)

    def run(self):
        try:
            events = get_today_events() or []
            reminders = get_macos_reminders() or []
            now = datetime.now()
            today_str = now.strftime("%Y-%m-%d")

            for r in reminders:
                events.append({
                    "title": f"[{r['list']}] {r['title']}",
                    "start_iso": f"{today_str} 09:00:00",
                    "end_iso": f"{today_str} 10:00:00",
                    "is_reminder": True
                })

            self.finished.emit(events)
        except Exception as e:
            print(f"Calendar Fetch Error: {e}")
            self.finished.emit([])


def get_weather_condition_text(code):
    if code == 0: return "Clear"
    if code in [1, 2, 3]: return "Partly Cloudy"
    if code in range(45, 49): return "Foggy"
    if code in range(51, 68) or code in range(80, 83): return "Rainy"
    if code in range(71, 78) or code in range(85, 87): return "Snowy"
    if code in range(95, 100): return "Thunderstorm"
    return "Overcast"


class SmoothScrollArea(QScrollArea):
    """High-performance smooth scrolling scroll area."""
    def wheelEvent(self, event):
        pix_delta = event.pixelDelta()
        if not pix_delta.isNull() and pix_delta.y() != 0:
            sb = self.verticalScrollBar()
            sb.setValue(sb.value() - pix_delta.y())
            event.accept()
        else:
            ang_delta = event.angleDelta().y()
            if ang_delta != 0:
                sb = self.verticalScrollBar()
                sb.setValue(sb.value() - int(ang_delta * 0.5))
                event.accept()
            else:
                super().wheelEvent(event)


class Dashboard(QWidget):
    open_history_signal = pyqtSignal()
    theme_toggled_signal = pyqtSignal(bool)

    # Thread-safe GUI dispatcher signals
    sig_update_status = pyqtSignal(str)
    sig_update_output = pyqtSignal(str, str, str)  # (result, mode, source_file)
    sig_process_events = pyqtSignal(str, str)      # (events_json, fallback_text)

    def __init__(self):
        super().__init__()
        self.bg_image_path = None
        self.current_model = "Smart Auto-Select"
        self.is_dark_mode = True
        self.current_displayed_events = []
        self.current_weather_data = None

        # Audio & Processing State
        self.recorder = Recorder()
        self.is_recording = False
        self.event_queue = []
        self.current_event = None
        self.upload_queue = []
        self.is_batch_processing = False
        self.last_source_file = None
        self.transcription_lock = threading.Lock()

        self._cached_bg_path = None
        self._cached_bg_size = None
        self._cached_bg_is_dark = None
        self._cached_final_pixmap = None

        self.load_settings()
        self.init_ui()

        # Connect thread-safe dispatcher signals to GUI handlers
        self.sig_update_status.connect(self.status_label.setText, Qt.ConnectionType.QueuedConnection)
        self.sig_update_output.connect(self.on_transcription_result, Qt.ConnectionType.QueuedConnection)
        self.sig_process_events.connect(self.parse_and_emit_events, Qt.ConnectionType.QueuedConnection)

        # Pre-warm Whisper model in background so transcription starts instantly
        threading.Thread(target=self._prewarm_whisper, daemon=True).start()

        # Initial data loading
        QTimer.singleShot(400, self.load_data)

    def _prewarm_whisper(self):
        try:
            from transcriber_module import get_model
            get_model()
        except Exception as e:
            print("Whisper pre-warm notice:", e)

    def load_settings(self):
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, 'r') as f:
                    settings = json.load(f)
                    self.bg_image_path = settings.get('bg_image', None)
                    self.current_model = settings.get('model', 'Smart Auto-Select')
                    if 'dark_mode' in settings:
                        self.is_dark_mode = bool(settings.get('dark_mode'))
        except Exception as e:
            print("Failed to load settings:", e)

    def save_settings(self):
        try:
            settings = {
                'bg_image': self.bg_image_path,
                'model': self.current_model,
                'dark_mode': self.is_dark_mode
            }
            with open(SETTINGS_FILE, 'w') as f:
                json.dump(settings, f, indent=2)
        except Exception as e:
            print("Failed to save settings:", e)

    def invalidate_bg_cache(self):
        self._cached_bg_path = None
        self._cached_bg_size = None
        self._cached_bg_is_dark = None
        self._cached_final_pixmap = None

    def _get_cached_bg_pixmap(self, target_size, is_dark):
        if (getattr(self, '_cached_bg_path', None) == self.bg_image_path and
            getattr(self, '_cached_bg_size', None) == target_size and
            getattr(self, '_cached_bg_is_dark', None) == is_dark and
            getattr(self, '_cached_final_pixmap', None) is not None):
            return self._cached_final_pixmap

        if not self.bg_image_path or not os.path.exists(self.bg_image_path):
            self.invalidate_bg_cache()
            return None

        pixmap = QPixmap(self.bg_image_path)
        if pixmap.isNull():
            reader = QImageReader(self.bg_image_path)
            reader.setAutoTransform(True)
            img = reader.read()
            if not img.isNull():
                pixmap = QPixmap.fromImage(img)

        if pixmap.isNull():
            self.invalidate_bg_cache()
            return None

        w, h = target_size.width(), target_size.height()
        if w <= 0 or h <= 0:
            return None

        scaled = pixmap.scaled(target_size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
        x = (scaled.width() - w) // 2
        y = (scaled.height() - h) // 2
        cropped = scaled.copy(max(0, x), max(0, y), w, h)

        final_pix = QPixmap(cropped.size())
        final_pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(final_pix)
        painter.drawPixmap(0, 0, cropped)
        overlay_color = QColor(15, 15, 27, 130) if is_dark else QColor(240, 242, 245, 130)
        painter.fillRect(final_pix.rect(), overlay_color)
        painter.end()

        self._cached_bg_path = self.bg_image_path
        self._cached_bg_size = target_size
        self._cached_bg_is_dark = is_dark
        self._cached_final_pixmap = final_pix
        return final_pix

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_cached_bg_size') and self._cached_bg_size != event.size():
            self._cached_bg_size = None

    def paintEvent(self, event):
        if self.bg_image_path and os.path.exists(self.bg_image_path):
            is_dark = getattr(self, 'is_dark_mode', True)
            cached_pix = self._get_cached_bg_pixmap(self.size(), is_dark)
            if cached_pix and not cached_pix.isNull():
                painter = QPainter(self)
                painter.drawPixmap(0, 0, cached_pix)
                painter.end()
                return
        super().paintEvent(event)

    def init_ui(self):
        # 1. Main Smooth Scroll Area
        main_scroll = SmoothScrollArea(self)
        main_scroll.setObjectName("main_scroll")
        main_scroll.setWidgetResizable(True)
        main_scroll.setFrameShape(QFrame.Shape.NoFrame)
        main_scroll.setStyleSheet("QScrollArea#main_scroll { background: transparent; border: none; }")
        main_scroll.viewport().setStyleSheet("background: transparent;")
        main_scroll.verticalScrollBar().setSingleStep(14)

        scroll_widget = QWidget()
        scroll_widget.setObjectName("scroll_widget")
        scroll_widget.setStyleSheet("QWidget#scroll_widget { background: transparent; }")

        layout = QVBoxLayout(scroll_widget)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(16)

        # -------------------------------------------------------------
        # 1. Sleek Header (App Title, Date, Action Buttons)
        # -------------------------------------------------------------
        header_layout = QHBoxLayout()

        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(2)

        self.title_label = QLabel("AI Daily Assistant")
        self.title_label.setObjectName("app_title_label")
        self.title_label.setStyleSheet("font-size: 28px; font-weight: 800; letter-spacing: -0.5px;")

        today_date_str = datetime.now().strftime("%A, %B %d, %Y")
        self.date_label = QLabel(today_date_str)
        self.date_label.setObjectName("date_subtitle_label")
        self.date_label.setStyleSheet("font-size: 15px; color: #94A3B8; font-weight: 500;")

        title_vbox.addWidget(self.title_label)
        title_vbox.addWidget(self.date_label)
        header_layout.addLayout(title_vbox)
        header_layout.addStretch()

        # Action Buttons in Top-Right
        header_buttons = QHBoxLayout()
        header_buttons.setSpacing(12)

        self.batch_btn = QPushButton("Import")
        self.batch_btn.setObjectName("header_btn")
        self.batch_btn.setToolTip("Batch Import Schedule / Classes")
        self.batch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.batch_btn.clicked.connect(self.open_batch_import)

        self.history_btn = QPushButton("History")
        self.history_btn.setObjectName("header_btn")
        self.history_btn.setToolTip("Voice Recordings & Transcripts History")
        self.history_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.history_btn.clicked.connect(self.open_recording_history)

        self.settings_btn = QPushButton("Settings")
        self.settings_btn.setObjectName("header_btn")
        self.settings_btn.setToolTip("AI Model, Theme & Wallpaper Settings")
        self.settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_btn.clicked.connect(self.open_settings_dialog)

        header_buttons.addWidget(self.batch_btn)
        header_buttons.addWidget(self.history_btn)
        header_buttons.addWidget(self.settings_btn)
        header_layout.addLayout(header_buttons)
        layout.addLayout(header_layout)

        # -------------------------------------------------------------
        # 2. Row 1: Weather Card & Dynamic AI Daily Advice Card (Equal Width 1:1)
        # -------------------------------------------------------------
        row1_layout = QHBoxLayout()
        row1_layout.setSpacing(16)

        # Weather Card (QGroupBox)
        self.weather_card = QGroupBox("LIVE WEATHER && ENVIRONMENT")
        self.weather_card.setObjectName("weather_card")
        self.weather_card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.weather_card.setMinimumHeight(210)

        wc_layout = QVBoxLayout(self.weather_card)
        wc_layout.setContentsMargins(20, 20, 20, 18)

        self.city_label = QLabel("Detecting Location...")
        self.city_label.setObjectName("city_label")

        temp_center_layout = QHBoxLayout()
        self.icon_label = QLabel("Clear")
        self.icon_label.setObjectName("icon_label")
        self.temp_label = QLabel("--°C")
        self.temp_label.setObjectName("temp_label")
        temp_center_layout.addWidget(self.temp_label)
        temp_center_layout.addSpacing(14)
        temp_center_layout.addWidget(self.icon_label)
        temp_center_layout.addStretch()

        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(12)
        self.aqi_label = QLabel("AQI: --")
        self.aqi_label.setObjectName("badge_label")

        self.uv_label = QLabel("UV: --")
        self.uv_label.setObjectName("badge_label")

        self.rain_label = QLabel("Rain: --%")
        self.rain_label.setObjectName("badge_label")

        stats_layout.addWidget(self.aqi_label)
        stats_layout.addWidget(self.uv_label)
        stats_layout.addWidget(self.rain_label)
        stats_layout.addStretch()

        wc_layout.addWidget(self.city_label)
        wc_layout.addSpacing(4)
        wc_layout.addLayout(temp_center_layout)
        wc_layout.addStretch()
        wc_layout.addLayout(stats_layout)

        # Suggestions / AI Daily Advice Card (QGroupBox)
        self.sugg_card = QGroupBox("DYNAMIC AI DAILY INTELLIGENCE")
        self.sugg_card.setObjectName("sugg_card")
        self.sugg_card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.sugg_card.setMinimumHeight(210)

        sc_layout = QVBoxLayout(self.sugg_card)
        sc_layout.setContentsMargins(20, 20, 20, 18)

        advice_header = QHBoxLayout()
        advice_header.addStretch()

        self.refresh_advice_btn = QPushButton("Refresh Advice")
        self.refresh_advice_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_advice_btn.setToolTip("Regenerate AI Advice")
        self.refresh_advice_btn.clicked.connect(self.regenerate_advice)
        self.refresh_advice_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(56, 189, 248, 0.12);
                color: #38BDF8;
                border: 1px solid rgba(56, 189, 248, 0.25);
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(56, 189, 248, 0.25);
            }
        """)
        advice_header.addWidget(self.refresh_advice_btn)
        sc_layout.addLayout(advice_header)

        self.sugg_text = QLabel("Analyzing real-time weather, rain forecast and your schedule...")
        self.sugg_text.setObjectName("sugg_text")
        self.sugg_text.setWordWrap(True)
        self.sugg_text.setStyleSheet("font-size: 16px; line-height: 1.5; background-color: transparent;")

        sc_layout.addWidget(self.sugg_text)
        sc_layout.addStretch()

        row1_layout.addWidget(self.weather_card, 1)
        row1_layout.addWidget(self.sugg_card, 1)
        layout.addLayout(row1_layout)

        # -------------------------------------------------------------
        # 3. Row 2: Voice Assistant / Inline Live Recording Card (QGroupBox)
        # -------------------------------------------------------------
        self.voice_card = QGroupBox("VOICE ASSISTANT && SMART TRANSCRIPTION ENGINE")
        self.voice_card.setObjectName("voice_card")
        self.voice_card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        voice_layout = QVBoxLayout(self.voice_card)
        voice_layout.setContentsMargins(20, 22, 20, 18)
        voice_layout.setSpacing(14)

        # Top Action Toolbar of Voice Card
        v_top_layout = QHBoxLayout()
        v_top_layout.addStretch()

        self.upload_btn = QPushButton("Upload Audio")
        self.upload_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.upload_btn.clicked.connect(self.upload_audio)
        self.upload_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(52, 199, 89, 0.15);
                color: #34C759;
                border: 1px solid rgba(52, 199, 89, 0.3);
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: rgba(52, 199, 89, 0.25);
            }
        """)

        self.save_btn = QPushButton("Save Result")
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.clicked.connect(self.save_to_file)
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.08);
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.15);
            }
        """)

        v_top_layout.addWidget(self.upload_btn)
        v_top_layout.addWidget(self.save_btn)
        voice_layout.addLayout(v_top_layout)

        # Main Record Action & Visualizer
        record_action_layout = QHBoxLayout()
        record_action_layout.setSpacing(16)

        self.record_btn = QPushButton("Start Recording")
        self.record_btn.setObjectName("record_btn")
        self.record_btn.setMinimumHeight(50)
        self.record_btn.setMinimumWidth(190)
        self.record_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.record_btn.setStyleSheet("""
            QPushButton#record_btn {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #007AFF, stop:1 #0056B3);
                color: white;
                border-radius: 12px;
                font-size: 16px;
                font-weight: bold;
                border: none;
                padding: 0 22px;
            }
            QPushButton#record_btn:hover {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #30B0FF, stop:1 #007AFF);
            }
        """)
        self.record_btn.clicked.connect(self.toggle_recording)
        record_action_layout.addWidget(self.record_btn)

        self.status_label = QLabel("Status: Ready (Click to record your voice)")
        self.status_label.setObjectName("status_label")
        self.status_label.setStyleSheet("font-size: 15px; color: #94A3B8;")
        record_action_layout.addWidget(self.status_label, 1)

        voice_layout.addLayout(record_action_layout)


        # Output Display (Transcripts and AI Extraction)
        self.output_display = QTextEdit()
        self.output_display.setObjectName("output_display")
        self.output_display.setPlaceholderText("Speech transcript and AI-extracted tasks/calendar events will appear here automatically...")
        self.output_display.setMinimumHeight(95)
        self.output_display.setMaximumHeight(160)
        voice_layout.addWidget(self.output_display)

        # Calendar & Reminder Confirmation Card (Queue based)
        self.calendar_group = QGroupBox("Confirm Calendar Event / Reminder")
        self.calendar_group.setVisible(False)
        cal_form_layout = QVBoxLayout()
        cal_form_layout.setSpacing(12)

        self.queue_label = QLabel("Item 1 of 1")
        self.queue_label.setStyleSheet("font-weight: bold; font-size: 15px; color: #38BDF8;")
        cal_form_layout.addWidget(self.queue_label)

        type_row = QHBoxLayout()
        type_lbl = QLabel("Type:")
        type_lbl.setStyleSheet("font-size: 15px; font-weight: bold;")
        type_row.addWidget(type_lbl)
        self.cal_type_combo = QComboBox()
        self.cal_type_combo.setView(QListView())
        self.cal_type_combo.addItems(["Calendar Event", "Reminder"])
        self.cal_type_combo.currentIndexChanged.connect(self.on_item_type_changed)
        type_row.addWidget(self.cal_type_combo)

        self.cal_sel_label = QLabel("Add to Calendar:")
        self.cal_sel_label.setStyleSheet("font-size: 15px; font-weight: bold;")
        self.cal_calendar_combo = QComboBox()
        self.cal_calendar_combo.setView(QListView())
        self.cal_calendar_combo.addItem("Calendar")

        self.cal_reminder_combo = QComboBox()
        self.cal_reminder_combo.setView(QListView())
        self.cal_reminder_combo.addItem("Homework and study")
        self.cal_reminder_combo.setVisible(False)

        type_row.addSpacing(15)
        type_row.addWidget(self.cal_sel_label)
        type_row.addWidget(self.cal_calendar_combo)
        type_row.addWidget(self.cal_reminder_combo)
        cal_form_layout.addLayout(type_row)

        self.cal_title = QLineEdit()
        self.cal_title.setPlaceholderText("Event or task title...")
        title_lbl = QLabel("Title:")
        title_lbl.setStyleSheet("font-size: 15px; font-weight: bold;")
        cal_form_layout.addWidget(title_lbl)
        cal_form_layout.addWidget(self.cal_title)

        time_date_layout = QHBoxLayout()
        date_vbox = QVBoxLayout()
        date_lbl = QLabel("Date (YYYY-MM-DD):")
        date_lbl.setStyleSheet("font-size: 15px; font-weight: bold;")
        date_vbox.addWidget(date_lbl)
        self.cal_date = QDateEdit()
        self.cal_date.setCalendarPopup(True)
        self.cal_date.setDisplayFormat("yyyy-MM-dd")
        self.cal_date.setDate(QDate.currentDate())
        date_vbox.addWidget(self.cal_date)

        self.start_vbox = QVBoxLayout()
        self.start_label = QLabel("Start (HH:MM AM/PM):")
        self.start_label.setStyleSheet("font-size: 15px; font-weight: bold;")
        self.cal_start = QLineEdit()
        self.start_vbox.addWidget(self.start_label)
        self.start_vbox.addWidget(self.cal_start)

        self.end_vbox_widget = QWidget()
        end_vbox = QVBoxLayout(self.end_vbox_widget)
        end_vbox.setContentsMargins(0, 0, 0, 0)
        end_lbl = QLabel("End (HH:MM AM/PM):")
        end_lbl.setStyleSheet("font-size: 15px; font-weight: bold;")
        end_vbox.addWidget(end_lbl)
        self.cal_end = QLineEdit()
        end_vbox.addWidget(self.cal_end)

        time_date_layout.addLayout(date_vbox)
        time_date_layout.addLayout(self.start_vbox)
        time_date_layout.addWidget(self.end_vbox_widget)
        cal_form_layout.addLayout(time_date_layout)

        notes_lbl = QLabel("Notes:")
        notes_lbl.setStyleSheet("font-size: 15px; font-weight: bold;")
        cal_form_layout.addWidget(notes_lbl)
        self.cal_notes = QTextEdit()
        self.cal_notes.setMaximumHeight(60)
        cal_form_layout.addWidget(self.cal_notes)

        btn_row = QHBoxLayout()
        self.add_btn = QPushButton("Add Event to Calendar")
        self.add_btn.setStyleSheet("""
            QPushButton {
                background-color: #38BDF8; color: #0F172A; font-weight: bold; font-size: 15px; border-radius: 8px; padding: 10px 20px;
            }
            QPushButton:hover {
                background-color: #0EA5E9;
            }
        """)
        self.add_btn.clicked.connect(self.confirm_calendar_event)

        self.ignore_btn = QPushButton("Skip / Next")
        self.ignore_btn.setStyleSheet("font-size: 14px; padding: 10px 18px; font-weight: bold;")
        self.ignore_btn.clicked.connect(self.skip_event)

        btn_row.addStretch()
        btn_row.addWidget(self.ignore_btn)
        btn_row.addWidget(self.add_btn)
        cal_form_layout.addLayout(btn_row)

        self.calendar_group.setLayout(cal_form_layout)
        voice_layout.addWidget(self.calendar_group)

        # Async load calendar and reminder lists
        threading.Thread(target=self.load_calendars_and_reminders_async, daemon=True).start()

        layout.addWidget(self.voice_card)

        # -------------------------------------------------------------
        # 4. Row 3: Schedule & Tasks Section (QGroupBox)
        # -------------------------------------------------------------
        self.schedule_group = QGroupBox("TODAY'S SCHEDULE && REMINDERS TIMELINE")
        self.schedule_group.setObjectName("schedule_group")
        self.schedule_group.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        sched_layout = QVBoxLayout(self.schedule_group)
        sched_layout.setContentsMargins(20, 24, 20, 20)
        sched_layout.setSpacing(14)

        cal_header_layout = QHBoxLayout()
        cal_header_layout.addStretch()

        self.cal_filter_mode = "all"
        self.filter_all_btn = QPushButton("All")
        self.filter_cal_btn = QPushButton("Calendar")
        self.filter_rem_btn = QPushButton("Reminders")
        for b in (self.filter_all_btn, self.filter_cal_btn, self.filter_rem_btn):
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet("""
                QPushButton {
                    background-color: rgba(255, 255, 255, 0.08);
                    color: #94A3B8;
                    border: 1px solid rgba(255, 255, 255, 0.12);
                    border-radius: 6px;
                    padding: 6px 14px;
                    font-size: 13px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: rgba(255, 255, 255, 0.15);
                    color: #FFFFFF;
                }
                QPushButton:checked {
                    background-color: #38BDF8;
                    color: #0F172A;
                    border: 1px solid #38BDF8;
                }
            """)

        self.filter_all_btn.setChecked(True)
        self.view_btn_group = QButtonGroup(self)
        self.view_btn_group.addButton(self.filter_all_btn)
        self.view_btn_group.addButton(self.filter_cal_btn)
        self.view_btn_group.addButton(self.filter_rem_btn)

        self.filter_all_btn.clicked.connect(lambda: self.set_calendar_filter("all"))
        self.filter_cal_btn.clicked.connect(lambda: self.set_calendar_filter("calendar"))
        self.filter_rem_btn.clicked.connect(lambda: self.set_calendar_filter("reminders"))

        self.add_manual_event_btn = QPushButton("Add Event")
        self.add_manual_event_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_manual_event_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(56, 189, 248, 0.15);
                color: #38BDF8;
                border: 1px solid rgba(56, 189, 248, 0.35);
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(56, 189, 248, 0.3);
                color: #FFFFFF;
            }
        """)
        self.add_manual_event_btn.clicked.connect(self.open_manual_add_event)

        self.refresh_cal_btn = QPushButton("Refresh")
        self.refresh_cal_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_cal_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.08);
                color: #94A3B8;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.15);
                color: #FFFFFF;
            }
        """)
        self.refresh_cal_btn.clicked.connect(self.refresh_calendar_now)

        cal_header_layout.addWidget(self.filter_all_btn)
        cal_header_layout.addWidget(self.filter_cal_btn)
        cal_header_layout.addWidget(self.filter_rem_btn)
        cal_header_layout.addWidget(self.add_manual_event_btn)
        cal_header_layout.addWidget(self.refresh_cal_btn)
        sched_layout.addLayout(cal_header_layout)

        self.cal_container = QFrame()
        self.cal_container.setObjectName("cal_container")
        self.cal_layout = QVBoxLayout()
        self.cal_layout.setContentsMargins(0, 0, 0, 0)
        self.cal_layout.setSpacing(10)
        self.cal_container.setLayout(self.cal_layout)

        sched_layout.addWidget(self.cal_container)
        layout.addWidget(self.schedule_group)

        # Setup scroll area and Dashboard layout
        main_scroll.setWidget(scroll_widget)
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(main_scroll)

        self.apply_theme(self.is_dark_mode)

        # Auto-refresh calendar timer every 5 minutes
        self.calendar_refresh_timer = QTimer(self)
        self.calendar_refresh_timer.timeout.connect(self.refresh_calendar_now)
        self.calendar_refresh_timer.start(300000)

    # -----------------------------------------------------------------
    # Settings Dialog
    # -----------------------------------------------------------------
    def open_settings_dialog(self):
        dialog = SettingsDialog(
            parent=self,
            is_dark_mode=self.is_dark_mode,
            current_model=self.current_model,
            bg_image_path=self.bg_image_path
        )
        dialog.settings_changed.connect(self.on_settings_applied)
        dialog.exec()

    def on_settings_applied(self, new_settings):
        self.current_model = new_settings.get("model", self.current_model)
        self.bg_image_path = new_settings.get("bg_image", self.bg_image_path)
        new_dark_mode = new_settings.get("dark_mode", self.is_dark_mode)

        self.invalidate_bg_cache()
        self.apply_theme(new_dark_mode)
        self.save_settings()
        self.update()

        # Regenerate daily advice with new model if weather data available
        if self.current_weather_data:
            self.regenerate_advice()

    def open_recording_history(self):
        dialog = RecordingHistoryDialog(self, is_dark_mode=self.is_dark_mode)
        dialog.process_transcription_requested.connect(self.process_transcription_text)
        dialog.exec()

    def open_batch_import(self):
        dialog = BatchImportDialog(self, is_dark_mode=self.is_dark_mode)
        if dialog.exec():
            text = dialog.get_text()
            if text:
                self.process_batch_import_text(text)

    # -----------------------------------------------------------------
    # Theme Application
    # -----------------------------------------------------------------
    def apply_theme(self, is_dark):
        self.is_dark_mode = is_dark
        has_wallpaper = bool(self.bg_image_path and os.path.exists(self.bg_image_path))

        if hasattr(self, 'timeline_widget'):
            self.timeline_widget.is_dark_mode = is_dark
            self.timeline_widget.update()

        if is_dark:
            bg_style = "background: transparent;" if has_wallpaper else "background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0f172a, stop:1 #1e293b);"
            card_bg = "background-color: rgba(15, 23, 42, 0.80);" if has_wallpaper else "background-color: rgba(30, 41, 59, 0.70);"
            self.setStyleSheet(f"""
                Dashboard {{
                    {bg_style}
                }}
                QScrollArea#main_scroll, QWidget#scroll_widget {{
                    background: transparent;
                    background-color: transparent;
                    border: none;
                }}
                QGroupBox {{
                    {card_bg}
                    border-radius: 18px;
                    border: 1px solid rgba(255, 255, 255, 0.16);
                    margin-top: 22px;
                    padding: 26px 20px 20px 20px;
                    font-weight: 800;
                    font-size: 15px;
                }}
                QGroupBox::title {{
                    subcontrol-origin: margin;
                    subcontrol-position: top left;
                    left: 20px;
                    padding: 6px 16px;
                    background-color: #0F172A;
                    border: 1px solid rgba(56, 189, 248, 0.45);
                    border-radius: 8px;
                    color: #38BDF8;
                    font-size: 14px;
                    font-weight: 800;
                    letter-spacing: 0.8px;
                }}
                QGroupBox#calendar_group {{
                    background-color: rgba(0, 0, 0, 0.28);
                    border: 1px dashed rgba(56, 189, 248, 0.4);
                    border-radius: 12px;
                    margin-top: 16px;
                    padding: 18px 14px 14px 14px;
                }}
                QGroupBox#calendar_group::title {{
                    background-color: #0F172A;
                    border: 1px solid rgba(56, 189, 248, 0.3);
                    border-radius: 6px;
                    padding: 4px 12px;
                    font-size: 13px;
                }}
                QFrame#cal_container {{
                    background: transparent;
                    border: none;
                }}
                QLabel {{
                    background-color: transparent;
                    color: #FFFFFF;
                }}
                QLabel#app_title_label {{
                    font-size: 28px;
                    font-weight: 800;
                    color: #FFFFFF;
                }}
                QLabel#date_subtitle_label {{
                    font-size: 15px;
                    color: #94A3B8;
                }}
                QPushButton#header_btn {{
                    background-color: rgba(255, 255, 255, 0.08);
                    border-radius: 12px;
                    border: 1px solid rgba(255, 255, 255, 0.14);
                    font-size: 14px;
                    font-weight: bold;
                    color: #FFFFFF;
                    padding: 8px 16px;
                }}
                QPushButton#header_btn:hover {{
                    background-color: rgba(255, 255, 255, 0.18);
                    border: 1px solid rgba(255, 255, 255, 0.25);
                }}
                QLabel#city_label {{
                    font-size: 18px;
                    font-weight: 600;
                    color: #F1F5F9;
                }}
                QLabel#temp_label {{
                    font-size: 44px;
                    font-weight: 800;
                    color: #FFFFFF;
                }}
                QLabel#icon_label {{
                    font-size: 20px;
                    font-weight: 700;
                    color: #38BDF8;
                }}
                QLabel#badge_label {{
                    background-color: rgba(255, 255, 255, 0.08);
                    border-radius: 8px;
                    padding: 6px 12px;
                    font-weight: bold;
                    font-size: 14px;
                    color: #FFFFFF;
                }}
                QLabel#section_title {{
                    font-size: 14px;
                    font-weight: 800;
                    color: #38BDF8;
                    letter-spacing: 1.2px;
                }}
                QLabel#sugg_text {{
                    font-size: 16px;
                    color: #F8FAFC;
                }}
                QLabel#section_header {{
                    font-size: 15px;
                    font-weight: 800;
                    color: #38BDF8;
                    letter-spacing: 1.2px;
                    margin-top: 10px;
                }}
                QTextEdit, QLineEdit, QDateEdit {{
                    background-color: rgba(30, 41, 59, 0.7);
                    border: 1px solid rgba(255, 255, 255, 0.16);
                    border-radius: 10px;
                    color: #FFFFFF;
                    padding: 10px 14px;
                    font-size: 15px;
                }}
                QTextEdit#output_display {{
                    background-color: rgba(0, 0, 0, 0.22);
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 12px;
                    color: #F8FAFC;
                    padding: 12px 16px;
                    font-size: 15px;
                }}
                QComboBox {{
                    background-color: rgba(30, 41, 59, 0.85);
                    border: 1px solid rgba(255, 255, 255, 0.2);
                    border-radius: 10px;
                    color: #FFFFFF;
                    padding: 8px 14px;
                    font-size: 15px;
                    min-height: 28px;
                }}
                QComboBox::drop-down {{
                    subcontrol-origin: padding;
                    subcontrol-position: top right;
                    width: 25px;
                    border-left: none;
                }}
                QComboBox::down-arrow {{
                    image: none;
                    border-left: 4px solid transparent;
                    border-right: 4px solid transparent;
                    border-top: 5px solid #38BDF8;
                    margin-right: 8px;
                }}
                QComboBox QAbstractItemView {{
                    background-color: #1E293B;
                    border: 1px solid #334155;
                    border-radius: 8px;
                    color: #FFFFFF;
                    selection-background-color: #0284C7;
                    selection-color: #FFFFFF;
                    outline: 0px;
                    padding: 4px;
                }}
                QComboBox QAbstractItemView::item {{
                    min-height: 36px;
                    padding: 8px 14px;
                    border-radius: 6px;
                    color: #FFFFFF;
                    font-size: 15px;
                }}
                QComboBox QAbstractItemView::item:hover {{
                    background-color: #334155;
                    color: #38BDF8;
                }}
                QComboBox QAbstractItemView::item:selected {{
                    background-color: #0284C7;
                    color: #FFFFFF;
                }}
                QFrame#event_card {{
                    background-color: rgba(255, 255, 255, 0.06);
                    border-radius: 12px;
                    border: 1px solid rgba(255, 255, 255, 0.08);
                }}
                QFrame#event_card:hover {{
                    background-color: rgba(255, 255, 255, 0.12);
                }}
            """)
        else:
            bg_style = "background: transparent;" if has_wallpaper else "background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f8fafc, stop:1 #e2e8f0);"
            card_bg = "background-color: rgba(255, 255, 255, 0.90);" if has_wallpaper else "background-color: rgba(255, 255, 255, 0.96);"
            self.setStyleSheet(f"""
                Dashboard {{
                    {bg_style}
                }}
                QScrollArea#main_scroll, QWidget#scroll_widget {{
                    background: transparent;
                    background-color: transparent;
                    border: none;
                }}
                QGroupBox {{
                    {card_bg}
                    border-radius: 18px;
                    border: 1px solid rgba(0, 0, 0, 0.14);
                    margin-top: 22px;
                    padding: 26px 20px 20px 20px;
                    font-weight: 800;
                    font-size: 15px;
                }}
                QGroupBox::title {{
                    subcontrol-origin: margin;
                    subcontrol-position: top left;
                    left: 20px;
                    padding: 6px 16px;
                    background-color: #FFFFFF;
                    border: 1px solid rgba(2, 132, 199, 0.45);
                    border-radius: 8px;
                    color: #0284C7;
                    font-size: 14px;
                    font-weight: 800;
                    letter-spacing: 0.8px;
                }}
                QGroupBox#calendar_group {{
                    background-color: rgba(241, 245, 249, 0.9);
                    border: 1px dashed rgba(2, 132, 199, 0.4);
                    border-radius: 12px;
                    margin-top: 16px;
                    padding: 18px 14px 14px 14px;
                }}
                QGroupBox#calendar_group::title {{
                    background-color: #FFFFFF;
                    border: 1px solid rgba(2, 132, 199, 0.3);
                    border-radius: 6px;
                    padding: 4px 12px;
                    font-size: 13px;
                }}
                QFrame#cal_container {{
                    background: transparent;
                    border: none;
                }}
                QLabel {{
                    background-color: transparent;
                    color: #0F172A;
                }}
                QLabel#app_title_label {{
                    font-size: 28px;
                    font-weight: 800;
                    color: #0F172A;
                }}
                QLabel#date_subtitle_label {{
                    font-size: 15px;
                    color: #64748B;
                }}
                QPushButton#header_btn {{
                    background-color: rgba(255, 255, 255, 0.85);
                    border-radius: 12px;
                    border: 1px solid rgba(0, 0, 0, 0.15);
                    font-size: 14px;
                    font-weight: bold;
                    color: #0F172A;
                    padding: 8px 16px;
                }}
                QPushButton#header_btn:hover {{
                    background-color: rgba(255, 255, 255, 1.0);
                    border: 1px solid rgba(0, 0, 0, 0.25);
                }}
                QLabel#city_label {{
                    font-size: 18px;
                    font-weight: 600;
                    color: #334155;
                }}
                QLabel#temp_label {{
                    font-size: 44px;
                    font-weight: 800;
                    color: #0F172A;
                }}
                QLabel#icon_label {{
                    font-size: 20px;
                    font-weight: 700;
                    color: #0284C7;
                }}
                QLabel#badge_label {{
                    background-color: rgba(0, 0, 0, 0.05);
                    border-radius: 8px;
                    padding: 6px 12px;
                    font-weight: bold;
                    font-size: 14px;
                    color: #0F172A;
                }}
                QLabel#section_title {{
                    font-size: 14px;
                    font-weight: 800;
                    color: #0284C7;
                    letter-spacing: 1.2px;
                }}
                QLabel#sugg_text {{
                    font-size: 16px;
                    color: #1E293B;
                }}
                QLabel#section_header {{
                    font-size: 15px;
                    font-weight: 800;
                    color: #0284C7;
                    letter-spacing: 1.2px;
                    margin-top: 10px;
                }}
                QTextEdit, QLineEdit, QDateEdit {{
                    background-color: rgba(255, 255, 255, 0.95);
                    border: 1px solid rgba(0, 0, 0, 0.15);
                    border-radius: 10px;
                    color: #0F172A;
                    padding: 10px 14px;
                    font-size: 15px;
                }}
                QTextEdit#output_display {{
                    background-color: rgba(0, 0, 0, 0.04);
                    border: 1px solid rgba(0, 0, 0, 0.08);
                    border-radius: 12px;
                    color: #0F172A;
                    padding: 12px 16px;
                    font-size: 15px;
                }}
                QComboBox {{
                    background-color: rgba(255, 255, 255, 0.95);
                    border: 1px solid rgba(0, 0, 0, 0.15);
                    border-radius: 10px;
                    color: #0F172A;
                    padding: 8px 14px;
                    font-size: 15px;
                    min-height: 28px;
                }}
                QComboBox::drop-down {{
                    subcontrol-origin: padding;
                    subcontrol-position: top right;
                    width: 25px;
                    border-left: none;
                }}
                QComboBox::down-arrow {{
                    image: none;
                    border-left: 4px solid transparent;
                    border-right: 4px solid transparent;
                    border-top: 5px solid #0284C7;
                    margin-right: 8px;
                }}
                QComboBox QAbstractItemView {{
                    background-color: #FFFFFF;
                    border: 1px solid #CBD5E1;
                    border-radius: 8px;
                    color: #0F172A;
                    selection-background-color: #0284C7;
                    selection-color: #FFFFFF;
                    outline: 0px;
                    padding: 4px;
                }}
                QComboBox QAbstractItemView::item {{
                    min-height: 36px;
                    padding: 8px 14px;
                    border-radius: 6px;
                    color: #0F172A;
                    font-size: 15px;
                }}
                QComboBox QAbstractItemView::item:hover {{
                    background-color: #F1F5F9;
                    color: #0284C7;
                }}
                QComboBox QAbstractItemView::item:selected {{
                    background-color: #0284C7;
                    color: #FFFFFF;
                }}
                QFrame#event_card {{
                    background-color: rgba(241, 245, 249, 0.85);
                    border-radius: 12px;
                    border: 1px solid rgba(0, 0, 0, 0.08);
                }}
                QFrame#event_card:hover {{
                    background-color: rgba(255, 255, 255, 1.0);
                }}
            """)

        self.theme_toggled_signal.emit(is_dark)

        # Refresh schedule cards with new colors
        if hasattr(self, 'current_displayed_events') and self.current_displayed_events:
            self.update_calendar(self.current_displayed_events)

    # -----------------------------------------------------------------
    # Data Loading & Refresh
    # -----------------------------------------------------------------
    def load_data(self, force=False):
        now_ts = time.time()
        project_dir = os.path.dirname(os.path.abspath(__file__))
        cache_file = os.path.join(project_dir, "exports", "dashboard_cache.json")

        cache_data = {}
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r") as f:
                    cache_data = json.load(f)
            except Exception as e:
                print(f"Failed to read disk cache: {e}")

        # 1. Weather Cache (30 min TTL)
        weather_cached = cache_data.get("weather", {})
        weather_ts = cache_data.get("weather_ts", 0)
        if not force and weather_cached and (now_ts - weather_ts < 1800):
            self.update_weather(weather_cached)
        else:
            self.w_worker = WeatherWorker()
            self.w_worker.finished.connect(self.save_and_update_weather)
            self.w_worker.start()

        # 2. Calendar - Fresh fetch with fallback to cache
        calendar_cached = cache_data.get("calendar", [])
        calendar_ts = cache_data.get("calendar_ts", 0)
        today_str = datetime.now().strftime("%Y-%m-%d")
        cache_date = cache_data.get("calendar_date", "")

        if not force and calendar_cached and (cache_date == today_str) and (now_ts - calendar_ts < 300):
            self.current_displayed_events = calendar_cached
            self.update_calendar(calendar_cached)
        else:
            if calendar_cached and cache_date == today_str:
                self.current_displayed_events = calendar_cached
                self.update_calendar(calendar_cached)
            self.refresh_calendar_now()

    def _update_disk_cache(self, key, value, extra_keys=None):
        project_dir = os.path.dirname(os.path.abspath(__file__))
        cache_file = os.path.join(project_dir, "exports", "dashboard_cache.json")
        cache_data = {}
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r") as f:
                    cache_data = json.load(f)
            except Exception:
                cache_data = {}

        cache_data[key] = value
        cache_data[f"{key}_ts"] = time.time()
        if extra_keys:
            cache_data.update(extra_keys)

        try:
            os.makedirs(os.path.dirname(cache_file), exist_ok=True)
            with open(cache_file, "w") as f:
                json.dump(cache_data, f)
        except Exception as e:
            print(f"Failed to write disk cache: {e}")

    def save_and_update_weather(self, data):
        self.current_weather_data = data
        self._update_disk_cache("weather", data)
        self.update_weather(data)

    def update_weather(self, data):
        self.current_weather_data = data
        if not data:
            self.city_label.setText("Location Unavailable")
            return

        self.city_label.setText(f"{data['city']}")
        temp_val = str(data['temp']).replace('°C', '').strip()
        self.temp_label.setText(f"{temp_val}°C")
        self.icon_label.setText(get_weather_condition_text(data['code']))

        try:
            aqi = int(data.get('aqi', 0))
        except (ValueError, TypeError):
            aqi = 0
        aqi_color = "#2ECC71" if aqi < 50 else "#F1C40F" if aqi < 100 else "#E74C3C"
        self.aqi_label.setText(f"AQI: {aqi}")
        self.aqi_label.setStyleSheet(f"background-color: rgba(255, 255, 255, 0.08); border-radius: 8px; padding: 6px 12px; font-weight: bold; font-size: 14px; color: {aqi_color};")

        self.uv_label.setText(f"UV: {data.get('uv', 0)}")

        rain_prob = data.get('rain_prob_3h', 0)
        self.rain_label.setText(f"Rain: {rain_prob}% (3h)")

        # Kick off AI daily advice worker
        self.regenerate_advice()

    def regenerate_advice(self):
        if not self.current_weather_data:
            return
        self.sugg_text.setText("Generating personalized daily advice...")
        self.adv_worker = DailyAdviceWorker(self.current_weather_data, model_key=self.current_model)
        self.adv_worker.finished.connect(self.on_advice_ready)
        self.adv_worker.start()

    def on_advice_ready(self, advice_text):
        text_color = "#FFFFFF" if getattr(self, 'is_dark_mode', True) else "#0F172A"
        lines = advice_text.split("\n")
        html_lines = "".join([f"<p style='margin-bottom: 8px; line-height: 1.5; color: {text_color}; font-size: 16px;'>{line}</p>" for line in lines if line.strip()])
        self.sugg_text.setText(html_lines or advice_text)

    def refresh_calendar_now(self):
        self.c_worker = CalendarWorker()
        self.c_worker.finished.connect(self.save_and_update_calendar)
        self.c_worker.start()

    def save_and_update_calendar(self, events):
        today_str = datetime.now().strftime("%Y-%m-%d")
        self._update_disk_cache("calendar", events, {"calendar_date": today_str})
        self.current_displayed_events = events
        self.update_calendar(events)

    def set_calendar_filter(self, mode):
        self.cal_filter_mode = mode
        if hasattr(self, 'current_displayed_events'):
            self.update_calendar(self.current_displayed_events)

    def update_calendar(self, events):
        while self.cal_layout.count():
            item = self.cal_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                sub_layout = item.layout()
                while sub_layout.count():
                    sub_item = sub_layout.takeAt(0)
                    if sub_item.widget():
                        sub_item.widget().deleteLater()

        filter_mode = getattr(self, 'cal_filter_mode', 'all')
        show_calendar = filter_mode in ('all', 'calendar')
        show_reminders = filter_mode in ('all', 'reminders')
        lbl_color = "#8E8E93" if getattr(self, 'is_dark_mode', True) else "#6b7280"

        if not events:
            lbl = QLabel("No events or tasks scheduled for today.")
            lbl.setStyleSheet(f"color: {lbl_color}; font-size: 15px; font-style: italic; padding: 12px;")
            self.cal_layout.addWidget(lbl)
            return

        now = datetime.now()
        seen = set()
        unique_events = []
        for ev in events:
            key = (ev.get("title", "").strip().lower(), ev.get("start_iso", "").strip())
            if key not in seen:
                seen.add(key)
                unique_events.append(ev)

        cal_events = []
        reminders = []
        for ev in unique_events:
            dt = parse_event_datetime(ev.get('start_iso', ''), fallback_now=now)
            if ev.get('is_reminder', False):
                reminders.append((ev, dt))
            else:
                cal_events.append((ev, dt))

        cal_events.sort(key=lambda x: x[1])

        timed_cal_events = []
        allday_cal_events = []
        for ev, dt in cal_events:
            start_iso = ev.get('start_iso', '')
            end_iso = ev.get('end_iso', '')
            if (" 0:0:0" in start_iso or " 00:00:00" in start_iso) and ("23:59" in end_iso):
                allday_cal_events.append((ev, dt))
            else:
                timed_cal_events.append((ev, dt))

        if show_calendar and not show_reminders and not timed_cal_events and not allday_cal_events:
            lbl = QLabel("No calendar events scheduled for today.")
            lbl.setStyleSheet(f"color: {lbl_color}; font-size: 15px; font-style: italic; padding: 12px;")
            self.cal_layout.addWidget(lbl)
            return
        elif show_reminders and not show_calendar and not reminders:
            lbl = QLabel("No reminders or tasks for today.")
            lbl.setStyleSheet(f"color: {lbl_color}; font-size: 15px; font-style: italic; padding: 12px;")
            self.cal_layout.addWidget(lbl)
            return

        def render_card(ev, dt, is_all_day=False, is_rem=False):
            diff_hours = (dt - now).total_seconds() / 3600.0
            diff_mins = (dt - now).total_seconds() / 60.0
            urgency_tag = None

            if is_all_day:
                accent_color = "#30D158"  # All-day events always green
                time_str = "All Day"
            else:
                if is_rem:
                    if dt.hour != 9 or dt.minute != 0 or ev.get("has_due_time"):
                        time_str = dt.strftime("%H:%M")
                    else:
                        time_str = "Task"
                else:
                    end_iso = ev.get('end_iso', '')
                    end_dt = parse_event_datetime(end_iso, fallback_now=dt) if end_iso else None
                    if end_dt and end_dt > dt:
                        time_str = f"{dt.strftime('%H:%M')} - {end_dt.strftime('%H:%M')}"
                    else:
                        time_str = dt.strftime("%H:%M")

                # Dynamic Approach Urgency Rules:
                # - Within 3 hours: RED (#FF453A)
                # - Within 10 hours: YELLOW (#FFD60A)
                # - Within 24 hours: GREEN (#30D158)
                # - Otherwise (past or > 24 hours): NORMAL (#64748B)
                if diff_mins < 0:
                    end_iso = ev.get('end_iso', '')
                    end_dt = parse_event_datetime(end_iso, fallback_now=dt) if end_iso else None
                    if end_dt and now <= end_dt:
                        accent_color = "#FF453A"  # In progress right now
                        urgency_tag = "Now"
                    else:
                        accent_color = "#64748B"  # Past / Normal
                elif diff_hours <= 3.0:
                    accent_color = "#FF453A"  # Red (< 3 hours)
                    urgency_tag = "< 3h"
                elif diff_hours <= 10.0:
                    accent_color = "#FFD60A"  # Yellow (< 10 hours)
                    urgency_tag = "< 10h"
                elif diff_hours <= 24.0:
                    accent_color = "#30D158"  # Green (< 24 hours)
                    urgency_tag = "< 24h"
                else:
                    accent_color = "#64748B"  # Normal (beyond 24 hours)

            label_color = "#FFFFFF" if getattr(self, 'is_dark_mode', True) else "#0F172A"

            ev_frame = QFrame()
            ev_frame.setObjectName("event_card")
            ev_frame.setMinimumHeight(58)

            bar = QFrame()
            bar.setFixedWidth(4)
            bar.setStyleSheet(f"background-color: {accent_color}; border-radius: 2px; border: none;")

            ev_layout = QHBoxLayout()
            ev_layout.setContentsMargins(16, 12, 16, 12)
            ev_layout.setSpacing(10)
            ev_layout.addWidget(bar)

            if is_rem:
                circle_btn = QPushButton()
                circle_btn.setFixedSize(22, 22)
                circle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                circle_btn.setToolTip("Click to toggle completion")

                def set_btn_style(b, done):
                    if done:
                        b.setText("")
                        b.setStyleSheet("""
                            QPushButton {
                                border: 2px solid #30D158;
                                border-radius: 11px;
                                background-color: #30D158;
                                color: #FFFFFF;
                                font-weight: bold;
                                font-size: 13px;
                                padding: 0;
                            }
                        """)
                    else:
                        b.setText("")
                        b.setStyleSheet("""
                            QPushButton {
                                border: 2px solid #64748B;
                                border-radius: 11px;
                                background-color: transparent;
                            }
                            QPushButton:hover {
                                border-color: #38BDF8;
                            }
                        """)

                set_btn_style(circle_btn, False)

                raw_title = ev['title'].strip()
                if "] " in raw_title:
                    raw_title = raw_title.split("] ", 1)[1].strip()

                def make_toggle_handler(b, t):
                    b.is_completed = False
                    def handler():
                        if not b.is_completed:
                            set_btn_style(b, True)
                            b.is_completed = True
                            complete_macos_reminder(t)
                        else:
                            set_btn_style(b, False)
                            b.is_completed = False
                            uncomplete_macos_reminder(t)
                    return handler

                circle_btn.clicked.connect(make_toggle_handler(circle_btn, raw_title))
                ev_layout.addWidget(circle_btn)

            title_lbl = QLabel(ev['title'])
            title_lbl.setStyleSheet(f"color: {label_color}; font-weight: bold; font-size: 15px; border: none; background: transparent; padding-left: 6px;")
            title_lbl.setWordWrap(True)
            ev_layout.addWidget(title_lbl, 1)

            cal_badge = ev.get('calendar', '').strip()
            if not is_rem and cal_badge:
                cal_pill = QLabel(cal_badge)
                cal_pill_bg = "rgba(56, 189, 248, 0.12)" if getattr(self, 'is_dark_mode', True) else "#E0F2FE"
                cal_pill_color = "#38BDF8" if getattr(self, 'is_dark_mode', True) else "#0369A1"
                cal_pill_border = "rgba(56, 189, 248, 0.3)" if getattr(self, 'is_dark_mode', True) else "#BAE6FD"
                cal_pill.setStyleSheet(f"""
                    background-color: {cal_pill_bg};
                    color: {cal_pill_color};
                    border: 1px solid {cal_pill_border};
                    border-radius: 6px;
                    padding: 3px 8px;
                    font-size: 12px;
                    font-weight: 600;
                """)
                cal_pill.setFixedHeight(24)
                ev_layout.addWidget(cal_pill)

            if urgency_tag and not is_all_day:
                urg_pill = QLabel(urgency_tag)
                urg_pill.setStyleSheet(f"""
                    background-color: {accent_color}22;
                    color: {accent_color};
                    border: 1px solid {accent_color}66;
                    border-radius: 6px;
                    padding: 2px 6px;
                    font-size: 11px;
                    font-weight: bold;
                """)
                urg_pill.setFixedHeight(22)
                ev_layout.addWidget(urg_pill)

            time_lbl = QLabel(time_str)
            time_lbl.setStyleSheet(f"color: {label_color}; font-size: 14px; font-weight: 600; border: none; background: transparent;")
            time_lbl.setMinimumWidth(110)
            time_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            ev_layout.addWidget(time_lbl)
            ev_frame.setLayout(ev_layout)
            self.cal_layout.addWidget(ev_frame)

        # Section header for Calendar Events
        if show_calendar and (timed_cal_events or allday_cal_events):
            cal_header_lbl = QLabel(f"CALENDAR EVENTS ({len(timed_cal_events) + len(allday_cal_events)})")
            cal_header_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #F59E0B; margin-top: 6px; margin-bottom: 4px;" if getattr(self, 'is_dark_mode', True) else "font-size: 14px; font-weight: bold; color: #D97706; margin-top: 6px; margin-bottom: 4px;")
            self.cal_layout.addWidget(cal_header_lbl)

            # 1. Timed Calendar Events First
            for ev, dt in timed_cal_events:
                render_card(ev, dt, is_all_day=False, is_rem=False)

            # 2. All-day events Second
            for ev, dt in allday_cal_events:
                render_card(ev, dt, is_all_day=True, is_rem=False)

        # 3. Reminders Section with a SINGLE header
        if show_reminders and reminders:
            rem_header_layout = QHBoxLayout()
            rem_header = QLabel(f"REMINDERS & TASKS ({len(reminders)})")
            rem_header.setStyleSheet("font-size: 14px; font-weight: bold; color: #38BDF8; margin-top: 14px; margin-bottom: 4px;" if getattr(self, 'is_dark_mode', True) else "font-size: 14px; font-weight: bold; color: #0284c7; margin-top: 14px; margin-bottom: 4px;")

            batch_btn = QPushButton("Complete All Reminders")
            batch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            batch_btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(48, 209, 88, 0.15);
                    color: #30D158;
                    border: 1px solid rgba(48, 209, 88, 0.3);
                    border-radius: 6px;
                    padding: 6px 14px;
                    font-size: 13px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: rgba(48, 209, 88, 0.3);
                }
            """)

            def batch_complete_all():
                raw_titles = []
                for r_ev, _ in reminders:
                    t_clean = r_ev['title'].strip()
                    if "] " in t_clean:
                        t_clean = t_clean.split("] ", 1)[1].strip()
                    raw_titles.append(t_clean)

                batch_complete_macos_reminders(raw_titles)
                if hasattr(self, 'current_displayed_events'):
                    self.current_displayed_events = [e for e in self.current_displayed_events if not e.get('is_reminder')]
                    self.update_calendar(self.current_displayed_events)

            batch_btn.clicked.connect(batch_complete_all)
            rem_header_layout.addWidget(rem_header)
            rem_header_layout.addStretch()
            rem_header_layout.addWidget(batch_btn)
            self.cal_layout.addLayout(rem_header_layout)

            for ev, dt in reminders:
                render_card(ev, dt, is_all_day=False, is_rem=True)

    # -----------------------------------------------------------------
    # Voice Recording & Audio Processing Logic
    # -----------------------------------------------------------------
    def toggle_recording(self):
        if not self.is_recording:
            self.recorder.start()
            self.is_recording = True
            self.record_btn.setText("Stop Recording")
            self.record_btn.setStyleSheet("""
                QPushButton#record_btn {
                    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #FF3B30, stop:1 #CC2D24);
                    color: white;
                    border-radius: 12px;
                    font-size: 16px;
                    font-weight: bold;
                    border: none;
                    padding: 0 22px;
                }
                QPushButton#record_btn:hover {
                    background-color: #E0281D;
                }
            """)
            self.status_label.setText("Status: Recording live audio... Speak now!")
            self.calendar_group.setVisible(False)
            self.event_queue = []
            self.upload_btn.setEnabled(False)
        else:
            audio_file = self.recorder.stop()
            self.is_recording = False
            self.record_btn.setText("Start Recording")
            self.record_btn.setStyleSheet("""
                QPushButton#record_btn {
                    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #007AFF, stop:1 #0056B3);
                    color: white;
                    border-radius: 12px;
                    font-size: 16px;
                    font-weight: bold;
                    border: none;
                    padding: 0 22px;
                }
                QPushButton#record_btn:hover {
                    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #30B0FF, stop:1 #007AFF);
                }
            """)
            self.record_btn.setEnabled(False)
            self.upload_btn.setEnabled(False)
            self.status_label.setText("Status: Processing audio with Whisper AI...")

            if audio_file:
                add_or_update_recording(audio_file, status="Recorded", mode="todo")
                self.process_audio(audio_file)
            else:
                self.status_label.setText("Status: Error - No audio captured.")
                self.record_btn.setEnabled(True)
                self.upload_btn.setEnabled(True)

    def upload_audio(self):
        file_paths, _ = QFileDialog.getOpenFileNames(self, "Open Audio Files", "", "Audio Files (*.wav *.mp3 *.m4a *.flac)")
        if file_paths:
            self.upload_queue.extend(file_paths)
            if not self.is_batch_processing:
                self.is_batch_processing = True
                self.record_btn.setEnabled(False)
                self.upload_btn.setEnabled(False)
                self.process_next_upload()

    def process_next_upload(self):
        if self.upload_queue:
            file_path = self.upload_queue.pop(0)
            self.process_audio(file_path)
        else:
            self.is_batch_processing = False
            self.record_btn.setEnabled(True)
            self.upload_btn.setEnabled(True)
            QMessageBox.information(self, "Finished", "All uploaded audio files processed successfully!")

    def process_audio(self, audio_file):
        self.audio_worker = AudioProcessingWorker(audio_file, model_key=self.current_model)
        self.audio_worker.status_signal.connect(self.status_label.setText)
        self.audio_worker.result_signal.connect(self.on_transcription_result)
        self.audio_worker.events_signal.connect(self.parse_and_emit_events)
        self.audio_worker.finished_signal.connect(self.on_audio_processing_finished)
        self.audio_worker.error_signal.connect(lambda err: self.status_label.setText(f"Status: Error ({err})"))
        self.audio_worker.start()

    def on_transcription_result(self, result, mode, source_file):
        self.last_source_file = source_file
        self.output_display.setText(result)

    def on_audio_processing_finished(self):
        self.record_btn.setEnabled(True)
        self.upload_btn.setEnabled(True)
        if self.is_batch_processing:
            self.process_next_upload()

    def process_transcription_text(self, text, source_file=None):
        model_key = self.current_model
        mode = "todo"
        self.output_display.setText(text)
        self.last_source_file = source_file

        def run_proc():
            try:
                self.sig_update_status.emit("Status: Extracting Tasks (AI)...")
                todo_list = extract_todo(text, model_key)
                formatted_output = f"EXTRACTED TASKS & TO-DOs:\n{todo_list}\n\n" + "="*40 + f"\nORIGINAL TRANSCRIPT:\n{text}"
                self.sig_update_output.emit(formatted_output, mode, source_file or "")

                self.sig_update_status.emit("Status: Checking calendar events...")
                events_json = extract_calendar_event(text, model_key)
                self.sig_process_events.emit(events_json or "[]", text)
            except Exception as e:
                self.sig_update_status.emit(f"Status: Processing Error ({e})")

        threading.Thread(target=run_proc, daemon=True).start()

    def process_batch_import_text(self, text):
        model_key = self.current_model
        self.output_display.setText("Batch processing schedule... please wait.")
        self.status_label.setText("Status: Extracting bulk events (AI)...")

        def run_proc():
            try:
                events_json = extract_calendar_event(text, model_key)
                cleaned_json = events_json.strip("`").replace("json\n", "").strip()
                start_idx = cleaned_json.find('[')
                end_idx = cleaned_json.rfind(']') + 1
                if start_idx != -1 and end_idx != -1:
                    events_data = json.loads(cleaned_json[start_idx:end_idx])
                    if isinstance(events_data, list) and events_data:
                        valid_events = [e for e in events_data if e.get("title") and e["title"] != "None"]
                        for ev in valid_events:
                            item_type = ev.get("item_type", "calendar")
                            title = ev.get("title", "Event")
                            notes = ev.get("notes", "")
                            date_str = ev.get("date", "today")
                            start_str = str(ev.get("start_time", ""))
                            end_str = str(ev.get("end_time", ""))

                            qdate = QDate.fromString(date_str, "yyyy-MM-dd") if date_str.lower() != "today" else QDate.currentDate()
                            if not qdate.isValid(): qdate = QDate.currentDate()
                            base_date = datetime(qdate.year(), qdate.month(), qdate.day())

                            def parse_time(t_str, default_hour):
                                t_str = str(t_str).strip().upper()
                                if not t_str or t_str == "NONE":
                                    return base_date.replace(hour=default_hour, minute=0, second=0)
                                formats = ["%H:%M", "%I:%M %p", "%I %p", "%H", "%I%p", "%I:%M%p", "%H%M"]
                                for fmt in formats:
                                    try:
                                        t = datetime.strptime(t_str, fmt)
                                        return base_date.replace(hour=t.hour, minute=t.minute, second=0)
                                    except ValueError:
                                        continue
                                return base_date.replace(hour=default_hour, minute=0, second=0)

                            start_time = parse_time(start_str, 9)
                            end_time = parse_time(end_str, 10)

                            if item_type == "reminder":
                                add_macos_reminder(title, list_name="Homework and study", due_date=start_time, notes=notes)
                            else:
                                add_calendar_event(title, start_time, end_time, notes, calendar_name="Calendar")
                        self.refresh_calendar_now()
                        self.sig_update_status.emit(f"Status: Batch import complete ({len(valid_events)} items added)")
            except Exception as e:
                self.sig_update_status.emit(f"Status: Batch Error ({e})")

        threading.Thread(target=run_proc, daemon=True).start()

    def open_manual_add_event(self):
        """Opens the calendar / reminder confirmation card with empty fields for manual entry."""
        now = datetime.now()
        start_hour = (now.hour + 1) % 24
        end_hour = (start_hour + 1) % 24
        start_period = "PM" if start_hour >= 12 else "AM"
        end_period = "PM" if end_hour >= 12 else "AM"
        s_h12 = start_hour if 1 <= start_hour <= 12 else (start_hour - 12 if start_hour > 12 else 12)
        e_h12 = end_hour if 1 <= end_hour <= 12 else (end_hour - 12 if end_hour > 12 else 12)

        manual_item = {
            "item_type": "calendar",
            "action": "add",
            "title": "",
            "start_time": f"{s_h12}:00 {start_period}",
            "end_time": f"{e_h12}:00 {end_period}",
            "notes": "",
            "date": "today"
        }
        self.start_event_confirmation([manual_item])

    def parse_and_emit_events(self, events_json, fallback_text=None):
        try:
            events_data = None
            if events_json and isinstance(events_json, str):
                cleaned = events_json.strip()
                # Strip markdown fences if present
                if cleaned.startswith("```"):
                    lines = cleaned.split("\n")
                    if len(lines) >= 2 and lines[0].startswith("```"):
                        cleaned = "\n".join(lines[1:])
                    if cleaned.endswith("```"):
                        cleaned = cleaned[:-3].strip()

                start_arr = cleaned.find('[')
                end_arr = cleaned.rfind(']') + 1
                if start_arr != -1 and end_arr != -1 and end_arr > start_arr:
                    try:
                        events_data = json.loads(cleaned[start_arr:end_arr])
                    except Exception:
                        pass

                if events_data is None:
                    start_obj = cleaned.find('{')
                    end_obj = cleaned.rfind('}') + 1
                    if start_obj != -1 and end_obj != -1 and end_obj > start_obj:
                        try:
                            parsed_obj = json.loads(cleaned[start_obj:end_obj])
                            events_data = [parsed_obj] if isinstance(parsed_obj, dict) else parsed_obj
                        except Exception:
                            pass

            valid_events = []
            if isinstance(events_data, list) and events_data:
                valid_events = [e for e in events_data if isinstance(e, dict) and e.get("title") and str(e["title"]).strip() and e["title"] != "None"]

            # If no calendar events found from JSON but user spoke something substantial, create a fallback draft item
            if not valid_events and fallback_text and len(fallback_text.strip()) > 3:
                now = datetime.now()
                valid_events = [{
                    "item_type": "calendar",
                    "action": "add",
                    "title": fallback_text.strip()[:60],
                    "start_time": (now + timedelta(minutes=30)).strftime("%I:%M %p"),
                    "end_time": (now + timedelta(hours=1, minutes=30)).strftime("%I:%M %p"),
                    "notes": fallback_text.strip(),
                    "date": "today"
                }]

            if valid_events:
                # Fast local heuristics for suggestion
                cal_names = [self.cal_calendar_combo.itemText(i) for i in range(self.cal_calendar_combo.count())] or ["Personal", "Calendar"]
                rem_lists = [self.cal_reminder_combo.itemText(i) for i in range(self.cal_reminder_combo.count())] or ["Homework and study", "Tasks"]
                for ev in valid_events:
                    t_str = (str(ev.get("title", "")) + " " + str(ev.get("notes", ""))).lower()
                    if ev.get("item_type") == "reminder":
                        matched = None
                        for r in rem_lists:
                            if any(k in t_str for k in r.lower().split()):
                                matched = r
                                break
                        ev["suggested_list"] = matched or rem_lists[0]
                    else:
                        matched = None
                        for c in cal_names:
                            if c.lower() in ["blue schedule", "canvas", "holidays", "birthdays", "siri suggestions"]:
                                continue
                            if any(k in t_str for k in c.lower().split()):
                                matched = c
                                break
                        if not matched and any(k in t_str for k in ["study", "class", "lecture", "homework", "exam", "test", "school"]):
                            for c in cal_names:
                                if "study" in c.lower() or "class" in c.lower() or "school" in c.lower():
                                    matched = c
                                    break
                        ev["suggested_calendar"] = matched or (cal_names[0] if cal_names else "Personal")

                self.start_event_confirmation(valid_events)
            else:
                self.status_label.setText("Status: Ready (No schedule items detected)")
        except Exception as e:
            print(f"Failed to parse events JSON: {e}")
            self.status_label.setText("Status: Ready")

    def update_status_safe(self, text):
        QTimer.singleShot(0, lambda: self.status_label.setText(text))

    def enable_controls_safe(self):
        QTimer.singleShot(0, lambda: (
            self.record_btn.setEnabled(True),
            self.upload_btn.setEnabled(True)
        ))

    def display_result_safe(self, result, mode, source_file):
        def _apply():
            self.last_source_file = source_file
            self.output_display.setText(result)
        QTimer.singleShot(0, _apply)

    def save_to_file(self, silent=False, source_file=None):
        text = self.output_display.toPlainText()
        if not text.strip():
            if not silent:
                QMessageBox.warning(self, "Empty", "Nothing to save!")
            return None

        mode = "todos"
        project_dir = os.path.dirname(os.path.abspath(__file__))
        directory = os.path.join(project_dir, "exports", mode)
        os.makedirs(directory, exist_ok=True)

        src = source_file or self.last_source_file
        header = ""
        if src:
            basename = os.path.basename(src)
            creation_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            header = f"# {mode.upper()} ENTRY\n# Source File: {basename}\n# Exported At: {creation_time}\n"
            header += "="*40 + "\n\n"

        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        filename = f"{directory}/{mode}_{timestamp}.txt"

        try:
            with open(filename, "w") as f:
                f.write(header + text)
            if not silent:
                QMessageBox.information(self, "Saved", f"Output saved to:\n{filename}")
            return filename
        except Exception as e:
            if not silent:
                QMessageBox.critical(self, "Error", f"Failed to save file: {e}")
            return None

    # -----------------------------------------------------------------
    # Calendar & Reminders Confirmation UI
    # -----------------------------------------------------------------
    def load_calendars_and_reminders_async(self):
        try:
            calendars = get_calendar_names()
            reminders = get_reminder_lists()
            def _populate():
                self.cal_calendar_combo.clear()
                self.cal_calendar_combo.addItems(calendars or ["Calendar"])
                self.cal_reminder_combo.clear()
                self.cal_reminder_combo.addItems(reminders or ["Homework and study"])
            QTimer.singleShot(0, _populate)
        except Exception as e:
            print("Error loading calendars/reminders:", e)

    def on_item_type_changed(self, idx):
        if idx == 0:
            self.cal_sel_label.setText("Add to Calendar:")
            self.cal_calendar_combo.setVisible(True)
            self.cal_reminder_combo.setVisible(False)
            self.end_vbox_widget.setVisible(True)
            self.start_label.setText("Start (HH:MM AM/PM):")
            self.add_btn.setText("Add Event to Calendar")
        else:
            self.cal_sel_label.setText("Add to Reminder List:")
            self.cal_calendar_combo.setVisible(False)
            self.cal_reminder_combo.setVisible(True)
            self.end_vbox_widget.setVisible(False)
            self.start_label.setText("Due Time (optional):")
            self.add_btn.setText("Add Reminder")

    def start_event_confirmation(self, events):
        self.event_queue = list(events)
        self.total_events = len(events)
        if self.cal_calendar_combo.count() <= 1:
            try:
                cals = get_calendar_names()
                self.cal_calendar_combo.clear()
                self.cal_calendar_combo.addItems(cals or ["Personal", "Calendar"])
            except Exception:
                pass
        if self.cal_reminder_combo.count() <= 1:
            try:
                rems = get_reminder_lists()
                self.cal_reminder_combo.clear()
                self.cal_reminder_combo.addItems(rems or ["Homework and study", "Tasks"])
            except Exception:
                pass
        self.show_next_event()

    def show_next_event(self):
        if self.event_queue:
            self.current_event = self.event_queue.pop(0)
            current_idx = self.total_events - len(self.event_queue)
            item_type = self.current_event.get("item_type", "calendar")

            if item_type == "reminder":
                self.cal_type_combo.setCurrentIndex(1)
                self.queue_label.setText(f"Reminder {current_idx} of {self.total_events}")
                self.calendar_group.setTitle("Confirm Reminder Addition")
                sug_rem = self.current_event.get("suggested_list")
                if sug_rem:
                    idx = self.cal_reminder_combo.findText(sug_rem)
                    if idx >= 0:
                        self.cal_reminder_combo.setCurrentIndex(idx)
            else:
                self.cal_type_combo.setCurrentIndex(0)
                self.queue_label.setText(f"Event {current_idx} of {self.total_events}")
                if self.current_event.get("action") == "update":
                    old_title = self.current_event.get("old_title", "Unknown")
                    self.calendar_group.setTitle(f"Confirm Event Update: '{old_title}'")
                else:
                    self.calendar_group.setTitle("Confirm Calendar Event")

                sug_cal = self.current_event.get("suggested_calendar")
                if sug_cal:
                    idx = self.cal_calendar_combo.findText(sug_cal)
                    if idx >= 0:
                        self.cal_calendar_combo.setCurrentIndex(idx)

            self.cal_title.setText(self.current_event.get("title", ""))
            self.cal_notes.setText(self.current_event.get("notes", ""))

            date_str = str(self.current_event.get("date", "today"))
            if date_str.lower() == "today":
                self.cal_date.setDate(QDate.currentDate())
            else:
                qdate = QDate.fromString(date_str, "yyyy-MM-dd")
                self.cal_date.setDate(qdate if qdate.isValid() else QDate.currentDate())

            self.cal_start.setText(str(self.current_event.get("start_time", "")))
            self.cal_end.setText(str(self.current_event.get("end_time", "")))
            self.calendar_group.setVisible(True)
            self.status_label.setText(f"Status: Reviewing item {current_idx} of {self.total_events} - Please confirm or skip.")

            # Automatically scroll into view so the user immediately sees the confirmation card!
            if hasattr(self, 'main_scroll'):
                QTimer.singleShot(60, lambda: self.main_scroll.ensureWidgetVisible(self.calendar_group, 50, 50))
        else:
            self.calendar_group.setVisible(False)
            self.status_label.setText("Status: Ready (All schedule items processed)")
            QMessageBox.information(self, "Finished", "All detected schedule items processed.")

    def skip_event(self):
        self.show_next_event()

    def confirm_calendar_event(self):
        title = self.cal_title.text().strip()
        notes = self.cal_notes.toPlainText().strip()
        start_str = self.cal_start.text().strip()
        end_str = self.cal_end.text().strip()
        is_reminder = (self.cal_type_combo.currentIndex() == 1)

        qdate = self.cal_date.date()
        base_date = datetime(qdate.year(), qdate.month(), qdate.day())

        def parse_time(t_str, default_hour):
            t_str = str(t_str).strip().upper()
            if not t_str or t_str == "NONE":
                return base_date.replace(hour=default_hour, minute=0, second=0)
            formats = ["%H:%M", "%I:%M %p", "%I %p", "%H", "%I%p", "%I:%M%p", "%H%M"]
            for fmt in formats:
                try:
                    t = datetime.strptime(t_str, fmt)
                    return base_date.replace(hour=t.hour, minute=t.minute, second=0)
                except ValueError:
                    continue
            return base_date.replace(hour=default_hour, minute=0, second=0)

        start_time = parse_time(start_str, 12)
        end_time = parse_time(end_str, 13)

        if is_reminder:
            list_name = self.cal_reminder_combo.currentText() or "Homework and study"
            due_dt = start_time if start_str else None
            success, err = add_macos_reminder(title, list_name=list_name, due_date=due_dt, notes=notes)
            action_name = "add reminder"
        else:
            calendar_name = self.cal_calendar_combo.currentText() or "Calendar"
            if self.current_event and self.current_event.get("action") == "update":
                old_title = self.current_event.get("old_title", title)
                old_start_str = self.current_event.get("old_start_time", start_str)
                old_start = parse_time(old_start_str, 12) if old_start_str else None
                success, err = update_calendar_event(
                    target_title=old_title,
                    target_start_date=old_start,
                    new_title=title,
                    new_start_time=start_time,
                    new_end_time=end_time,
                    notes=notes,
                    calendar_name=calendar_name
                )
                action_name = "update event"
            else:
                success, err = add_calendar_event(title, start_time, end_time, notes, calendar_name)
                action_name = "add event"

        if success:
            self.refresh_calendar_now()
            self.show_next_event()
        else:
            QMessageBox.critical(self, "Error", f"Failed to {action_name}: {err}")
