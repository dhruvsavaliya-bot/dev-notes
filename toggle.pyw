"""
dev-notes automation toggle
Double-click this file -> a small window with one big button.
GREEN  = automation ON  (Task Scheduler will run add-note.py daily)
RED    = automation OFF (task disabled, nothing runs)
Click the button to switch. Uses the Windows scheduled task "dev-notes-auto".
Saved as .pyw so no console window appears.
"""

import subprocess
import tkinter as tk

TASK = "dev-notes-auto"


def sh(*cmd):
    return subprocess.run(
        cmd, capture_output=True, text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def task_exists():
    return sh("schtasks", "/Query", "/TN", TASK).returncode == 0


def is_enabled():
    r = sh("schtasks", "/Query", "/TN", TASK, "/FO", "LIST", "/V")
    return "Disabled" not in r.stdout


def refresh():
    if not task_exists():
        btn.config(text="TASK NOT FOUND\n(create it first)", bg="#777777")
        status.config(text=f'Scheduled task "{TASK}" does not exist yet.')
        return
    if is_enabled():
        btn.config(text="AUTOMATION: ON\n(click to turn OFF)", bg="#2e9e44")
        status.config(text="add-note.py will run automatically every day.")
    else:
        btn.config(text="AUTOMATION: OFF\n(click to turn ON)", bg="#c0392b")
        status.config(text="Automation paused. Nothing will run.")


def toggle():
    if not task_exists():
        return
    if is_enabled():
        r = sh("schtasks", "/Change", "/TN", TASK, "/Disable")
    else:
        r = sh("schtasks", "/Change", "/TN", TASK, "/Enable")
    if r.returncode != 0:
        status.config(text=f"Error: {r.stderr.strip()[:80]}")
    refresh()


root = tk.Tk()
root.title("dev-notes automation")
root.geometry("340x200")
root.resizable(False, False)
root.configure(bg="#1e1e1e")

tk.Label(
    root, text="dev-notes daily contribution",
    fg="white", bg="#1e1e1e", font=("Segoe UI", 12, "bold"),
).pack(pady=(16, 8))

btn = tk.Button(
    root, command=toggle, fg="white",
    font=("Segoe UI", 13, "bold"),
    width=24, height=3, relief="flat", cursor="hand2",
)
btn.pack()

status = tk.Label(root, text="", fg="#aaaaaa", bg="#1e1e1e", font=("Segoe UI", 9))
status.pack(pady=10)

refresh()
root.mainloop()
