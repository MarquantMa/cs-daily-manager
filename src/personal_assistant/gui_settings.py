import tkinter as tk
from tkinter import ttk
import json
import os

SETTINGS_FILE = os.path.join(os.path.dirname(__file__), 'settings.json')

DEFAULT_SETTINGS = {
    "Monday": {"sleep": "23:00-07:00", "class": "08:00-16:00"},
    "Tuesday": {"sleep": "23:00-07:00", "class": "08:00-16:00"},
    "Wednesday": {"sleep": "23:00-07:00", "class": "08:00-16:00"},
    "Thursday": {"sleep": "23:00-07:00", "class": "08:00-16:00"},
    "Friday": {"sleep": "23:00-07:00", "class": "08:00-16:00"},
    "Saturday": {"sleep": "23:00-08:00", "class": ""},
    "Sunday": {"sleep": "23:00-08:00", "class": ""}
}

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'r') as f:
            return json.load(f)
    return DEFAULT_SETTINGS

def save_settings(settings):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=4)

class TimetableGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Timetable Settings")
        self.settings = load_settings()
        self.entries = {}

        ttk.Label(root, text="Day").grid(row=0, column=0, padx=5, pady=5)
        ttk.Label(root, text="Sleep Hours (HH:MM-HH:MM)").grid(row=0, column=1, padx=5, pady=5)
        ttk.Label(root, text="Class Hours (HH:MM-HH:MM)").grid(row=0, column=2, padx=5, pady=5)

        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

        for i, day in enumerate(days):
            ttk.Label(root, text=day).grid(row=i+1, column=0, padx=5, pady=5)

            sleep_entry = ttk.Entry(root)
            sleep_entry.insert(0, self.settings.get(day, {}).get("sleep", ""))
            sleep_entry.grid(row=i+1, column=1, padx=5, pady=5)

            class_entry = ttk.Entry(root)
            class_entry.insert(0, self.settings.get(day, {}).get("class", ""))
            class_entry.grid(row=i+1, column=2, padx=5, pady=5)

            self.entries[day] = {"sleep": sleep_entry, "class": class_entry}

        save_btn = ttk.Button(root, text="Save Settings", command=self.save)
        save_btn.grid(row=8, column=0, columnspan=3, pady=10)

        self.status_label = ttk.Label(root, text="")
        self.status_label.grid(row=9, column=0, columnspan=3)

    def save(self):
        for day, entries in self.entries.items():
            self.settings[day] = {
                "sleep": entries["sleep"].get().strip(),
                "class": entries["class"].get().strip()
            }
        save_settings(self.settings)
        self.status_label.config(text="Settings saved successfully!")

if __name__ == "__main__":
    root = tk.Tk()
    app = TimetableGUI(root)
    root.mainloop()
