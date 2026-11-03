"""Tkinter launcher for nontechnical users; parsing runs in a child process."""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Optional


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    p = argparse.ArgumentParser(description="Окно сбора контактов")
    p.parse_args(argv)
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
        from tkinter.scrolledtext import ScrolledText
    except ImportError:
        print("Нет tkinter. Linux: sudo apt install python3-tk (Debian/Ubuntu) или sudo dnf install python3-tkinter (Fedora).")
        return 2
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        print(f"Не удалось открыть окно: {exc}. Для терминала используйте python -m parser_toolkit contacts --help")
        return 2
    root.title("Сбор контактов компаний")
    root.geometry("850x700")
    root.minsize(650, 550)
    frame = ttk.Frame(root, padding=18)
    frame.pack(fill="both", expand=True)
    frame.columnconfigure(1, weight=1)
    ttk.Label(frame, text="Контакты организаций", font=("Arial", 18, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 14))
    source = tk.StringVar(value="2ГИС")
    city = tk.StringVar(value="Алматы")
    query = tk.StringVar(value="")
    limit = tk.StringVar(value="50")
    folder = tk.StringVar(value=str(Path("output").resolve()))
    websites = tk.BooleanVar(value=True)
    controls = []
    for row, title, var in ((1, "Источник", source), (2, "Город (или несколько через ;)", city),
                            (3, "Категория или название компании", query), (4, "Лимит на город и источник", limit)):
        ttk.Label(frame, text=title).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=6)
        if row == 1:
            widget = ttk.Combobox(frame, textvariable=var, values=("2ГИС", "Яндекс Карты", "Оба источника"), state="readonly")
        else:
            widget = ttk.Entry(frame, textvariable=var)
        widget.grid(row=row, column=1, columnspan=2, sticky="ew", pady=6)
        controls.append(widget)
    ttk.Label(frame, text="Папка результатов").grid(row=5, column=0, sticky="w", pady=6)
    entry = ttk.Entry(frame, textvariable=folder)
    entry.grid(row=5, column=1, sticky="ew")
    browse = ttk.Button(frame, text="Выбрать", command=lambda: folder.set(filedialog.askdirectory() or folder.get()))
    browse.grid(row=5, column=2, padx=(8, 0))
    check = ttk.Checkbutton(frame, text="Дополнительно искать контакты на сайтах компаний (до 3 страниц)", variable=websites)
    check.grid(row=6, column=0, columnspan=3, sticky="w", pady=10)
    controls.extend((entry, browse, check))
    ttk.Label(frame, text="Подписи берутся из источника. Отсутствующие роли и контакты не придумываются.", wraplength=700).grid(row=7, column=0, columnspan=3, sticky="w")
    buttons = ttk.Frame(frame)
    buttons.grid(row=8, column=0, columnspan=3, sticky="w", pady=14)
    state = {"process": None, "log": None}
    events = queue.Queue()
    status = tk.StringVar(value="Введите запрос, проверьте город и нажмите «Собрать контакты».")
    ttk.Label(frame, textvariable=status, wraplength=760).grid(row=9, column=0, columnspan=3, sticky="w")
    log = ScrolledText(frame, height=18, wrap="word", state="disabled")
    log.grid(row=10, column=0, columnspan=3, sticky="nsew", pady=(10, 0))
    frame.rowconfigure(10, weight=1)

    def append(text):
        log.configure(state="normal")
        log.insert("end", text)
        log.see("end")
        log.configure(state="disabled")

    def open_folder():
        destination = Path(folder.get()).expanduser().resolve()
        destination.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(str(destination))
            else:
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(destination)])
        except OSError as exc:
            messagebox.showerror("Не удалось открыть папку", str(exc))

    def reader(process, logfile):
        with open(logfile, "w", encoding="utf-8") as f:
            for line in process.stdout:
                f.write(line)
                f.flush()
                events.put(("line", line))
        events.put(("done", process.wait()))

    def start():
        if state["process"] is not None:
            return
        cities = [c.strip() for c in city.get().split(";") if c.strip()]
        try:
            n = int(limit.get())
            if n <= 0 or not query.get().strip() or not cities or not folder.get().strip():
                raise ValueError
        except ValueError:
            messagebox.showerror("Проверьте поля", "Заполните запрос, город, папку и положительный целый лимит.")
            return
        destination = Path(folder.get()).expanduser().resolve()
        base = destination / ("contacts_" + datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f"))
        sources = {"2ГИС": "2gis", "Яндекс Карты": "yandex-maps", "Оба источника": "both"}
        cmd = [sys.executable, "-u", "-m", "parser_toolkit", "contacts", "--source", sources[source.get()],
               "--query", query.get().strip(), "--max", str(n), "--out", str(base)]
        for c in cities:
            cmd.extend(["--city", c])
        if websites.get():
            cmd.append("--websites")
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        try:
            destination.mkdir(parents=True, exist_ok=True)
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       text=True, encoding="utf-8", errors="replace", env=env,
                                       creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        except OSError as exc:
            messagebox.showerror("Ошибка запуска", str(exc))
            return
        state["process"] = process
        state["log"] = str(base) + ".log.txt"
        for control in controls:
            control.configure(state="disabled")
        start_button.configure(state="disabled")
        status.set("Идёт сбор. Результаты сохраняются по мере обработки; подробности ниже.")
        append("\nНовый сбор: " + str(base) + "\n")
        threading.Thread(target=reader, args=(process, state["log"]), daemon=True).start()

    def poll():
        while True:
            try:
                kind, value = events.get_nowait()
            except queue.Empty:
                break
            if kind == "line":
                append(value)
            else:
                state["process"] = None
                for control in controls:
                    control.configure(state="normal")
                controls[0].configure(state="readonly")
                start_button.configure(state="normal")
                status.set("Сбор завершён. Нажмите «Открыть результаты». Проверьте сообщения о недоступных страницах в журнале." if value == 0
                           else "Сбор завершился с ошибкой. Прочитайте журнал ниже; уже сохранённые результаты лежат в выбранной папке.")
        root.after(150, poll)

    def close():
        process = state["process"]
        if process is not None:
            if not messagebox.askyesno("Идёт сбор", "Закрыть окно и остановить сбор? Сохранённые файлы останутся, текущая операция может не сохраниться."):
                return
            process.terminate()
        root.destroy()

    start_button = ttk.Button(buttons, text="Собрать контакты", command=start)
    start_button.pack(side="left")
    ttk.Button(buttons, text="Открыть результаты", command=open_folder).pack(side="left", padx=10)
    root.protocol("WM_DELETE_WINDOW", close)
    poll()
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
