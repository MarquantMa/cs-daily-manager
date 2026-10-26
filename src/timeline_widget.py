from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont
from datetime import datetime

class CalendarTimelineViewWidget(QWidget):
    def __init__(self, is_dark_mode=True, parent=None):
        super().__init__(parent)
        self.is_dark_mode = is_dark_mode
        self.events = []
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Type", "Title", "Time Slot", "Status", "Duration"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        
        layout.addWidget(self.table)
        
        self.time_timer = QTimer(self)
        self.time_timer.timeout.connect(self.update_layout)
        self.time_timer.start(60000)

        self.apply_theme()

    def set_dark_mode(self, is_dark):
        self.is_dark_mode = is_dark
        self.apply_theme()
        self.update_layout()

    def apply_theme(self):
        if self.is_dark_mode:
            bg_color = "#0f0f1b"
            text_color = "#ffffff"
            header_bg = "#1a1a2e"
            grid_color = "#33334d"
        else:
            bg_color = "#ffffff"
            text_color = "#0f172a"
            header_bg = "#f1f5f9"
            grid_color = "#e2e8f0"

        self.table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {bg_color};
                color: {text_color};
                border: none;
                gridline-color: {grid_color};
                font-size: 15px;
                outline: 0;
            }}
            QHeaderView::section {{
                background-color: {header_bg};
                color: {text_color};
                font-weight: bold;
                font-size: 15px;
                border: none;
                border-bottom: 2px solid {grid_color};
                padding: 10px;
            }}
            QTableWidget::item {{
                border-bottom: 1px solid {grid_color};
                padding: 10px 8px;
                font-size: 15px;
            }}
        """)

    def set_events(self, events):
        self.events = events or []
        self.update_layout()

    def update_layout(self):
        self.table.setRowCount(0)
        now = datetime.now()
        
        for ev in self.events:
            title = ev.get('title', 'Event')
            start_iso = ev.get('start_iso', '')
            end_iso = ev.get('end_iso', '')
            is_rem = ev.get('is_reminder', False)
            cal_name = ev.get('calendar', 'Calendar')

            def parse_dt(d_str, fallback):
                if not d_str:
                    return fallback
                try:
                    cleaned = d_str.replace(" at ", " ").strip()
                    parts = cleaned.split(" ")
                    if len(parts) >= 2:
                        dp = [int(x) for x in parts[0].split("-")]
                        tp = [int(x) for x in parts[1].split(":")]
                        return datetime(dp[0], dp[1], dp[2], tp[0], tp[1], tp[2])
                except Exception:
                    pass
                try:
                    return datetime.strptime(d_str, "%Y-%m-%d %H:%M:%S")
                except Exception:
                    return fallback

            s_dt = parse_dt(start_iso, now)
            e_dt = parse_dt(end_iso, s_dt)

            # Determine Status
            status = "Upcoming"
            if is_rem:
                status = "Pending"
            elif s_dt <= now <= e_dt:
                status = "In Progress"
            elif e_dt < now:
                status = "Finished"

            # Determine Time Slot
            if (" 0:0:0" in start_iso or " 00:00:00" in start_iso) and ("23:59" in end_iso):
                time_slot = "All Day"
                duration = "24h"
            else:
                time_slot = f"{s_dt.strftime('%H:%M')} - {e_dt.strftime('%H:%M')}"
                dur_mins = (e_dt - s_dt).total_seconds() / 60
                duration = f"{int(dur_mins)}m" if dur_mins < 60 else f"{dur_mins/60:.1f}h"

            # Type
            ev_type = "Reminder" if is_rem else f"Calendar ({cal_name})"

            row = self.table.rowCount()
            self.table.insertRow(row)

            # Insert items
            type_item = QTableWidgetItem(ev_type)
            title_item = QTableWidgetItem(title)
            time_item = QTableWidgetItem(time_slot)
            status_item = QTableWidgetItem(status)
            dur_item = QTableWidgetItem(duration)

            # Colors
            if status == "In Progress":
                status_item.setForeground(QColor("#30D158"))
            elif status == "Upcoming":
                status_item.setForeground(QColor("#FFD60A"))
            elif status == "Finished":
                status_item.setForeground(QColor("#8E8E93"))
            
            if is_rem:
                type_item.setForeground(QColor("#38BDF8"))
            else:
                type_item.setForeground(QColor("#F59E0B"))

            # Alignments
            for item in [type_item, time_item, status_item, dur_item]:
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.table.setItem(row, 0, type_item)
            self.table.setItem(row, 1, title_item)
            self.table.setItem(row, 2, time_item)
            self.table.setItem(row, 3, status_item)
            self.table.setItem(row, 4, dur_item)
            
            # Alternate row colors
            if row % 2 == 1:
                bg_c = QColor(255, 255, 255, 10) if self.is_dark_mode else QColor(0, 0, 0, 10)
                for c in range(5):
                    self.table.item(row, c).setBackground(bg_c)
