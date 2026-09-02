"""Keyboard-driven TUI using only Python's standard curses module."""
from __future__ import annotations

import curses
import sys


ITEMS = ["Refresh status", "Configure SSH", "Telegram credentials", "Log into X",
         "Deploy worker", "Sync credentials", "Start worker", "Stop worker",
         "Open VPS terminal", "Exit"]


def _run_action(index: int) -> None:
    from .health import run_checks
    from .worker import WorkerController
    if index == 0:
        return
    if index == 1:
        from .cli import cmd_connect
        cmd_connect(type("Args", (), {"host": None, "user": None, "port": 22})())
    elif index == 2:
        from .cli import cmd_creds
        cmd_creds(type("Args", (), {"token": None, "chat_id": None})())
    elif index == 3:
        from .cli import cmd_xlogin
        cmd_xlogin(type("Args", (), {"session": None, "port": None, "max_wait": 300.0, "browser": None})())
    elif index == 4:
        print(WorkerController().deploy())
    elif index == 5:
        print(WorkerController().sync_credentials())
    elif index in (6, 7):
        print(WorkerController().run_action("start" if index == 6 else "stop"))
    elif index == 8:
        from .cli import cmd_terminal
        cmd_terminal(None)


def _draw_status(stdscr, report: dict, selection: int) -> None:
    stdscr.addstr(0, 2, "Telegram-X Manager", curses.A_BOLD)
    stdscr.addstr(1, 2, "Up/Down: select   Enter: open   Esc: back/refresh   Q: quit")
    t, x, w = report.get("telegram", {}), report.get("x_session", {}), report.get("workflow", {})
    bp = report.get("browser_profile", {})
    service = str(w.get("service", "")); health = (w.get("health") or {}).get("status", "")
    worker_ok = service.startswith(("running", "active")) or health == "running"
    statuses = [("SSH connection", bool(w.get("connected")), w.get("detail", "")),
                ("X session", bool(x.get("ok")), x.get("detail", "")),
                ("Chrome profile", bool(bp.get("exists")), bp.get("path", "")),
                ("Telegram pipeline", bool(t.get("ok")), t.get("detail", "")),
                ("Worker", worker_ok, service or health or "not running")]
    row = 3
    for label, ok, detail in statuses:
        color = 2 if ok else 1
        stdscr.addstr(row, 3, "GREEN" if ok else "RED", curses.color_pair(color) | curses.A_BOLD)
        stdscr.addstr(row, 11, f"{label}: {detail}"[: max(1, curses.COLS - 14)])
        row += 1
    stdscr.addstr(row + 1, 2, "Actions", curses.A_BOLD)
    for i, item in enumerate(ITEMS):
        marker = ">" if i == selection else " "
        attr = curses.A_REVERSE if i == selection else 0
        stdscr.addstr(row + 2 + i, 3, f"{marker} {item}"[: max(1, curses.COLS - 6)], attr)


def _main(stdscr) -> None:
    curses.curs_set(0); curses.start_color(); curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_RED, -1); curses.init_pair(2, curses.COLOR_GREEN, -1)
    selection = 0
    while True:
        report = __import__("telegram_x_manager.health", fromlist=["run_checks"]).run_checks()
        stdscr.clear(); _draw_status(stdscr, report, selection); stdscr.refresh()
        key = stdscr.getch()
        if key in (ord("q"), ord("Q"), 27):
            return
        if key in (curses.KEY_UP, ord("k")): selection = (selection - 1) % len(ITEMS)
        elif key in (curses.KEY_DOWN, ord("j")): selection = (selection + 1) % len(ITEMS)
        elif key in (10, 13, curses.KEY_ENTER):
            if selection == len(ITEMS) - 1: return
            curses.endwin()
            try: _run_action(selection)
            except Exception as exc: print(f"Error: {exc}")
            input("\nPress Enter to return to the TUI...")


def run() -> int:
    try: curses.wrapper(_main); return 0
    except curses.error:
        print("This terminal does not support the keyboard TUI. Use a real terminal.", file=sys.stderr)
        return 1
