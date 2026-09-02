"""Small synchronous terminal interface."""
from __future__ import annotations

def _pause():
    try: input("\nPress Enter to return to the menu...")
    except (EOFError, KeyboardInterrupt): pass

def run() -> int:
    from .health import render, run_checks
    from .worker import WorkerController
    while True:
        print("\n" + "=" * 48 + "\nTelegram-X Manager\n" + "=" * 48)
        print("1. Refresh status\n2. Configure SSH connection\n3. Save Telegram credentials")
        print("4. Log into X\n5. Deploy worker\n6. Sync credentials to worker")
        print("7. Start worker\n8. Stop worker\n9. Open VPS terminal\n0. Exit")
        try: choice = input("\nSelect an action: ").strip()
        except (EOFError, KeyboardInterrupt): print(); return 0
        if choice == "0": return 0
        try:
            if choice == "1": print(render(run_checks()))
            elif choice == "2":
                from .cli import cmd_connect
                cmd_connect(type("Args", (), {"host": None, "user": None, "port": 22})())
            elif choice == "3":
                from .cli import cmd_creds
                cmd_creds(type("Args", (), {"token": None, "chat_id": None})())
            elif choice == "4":
                from .cli import cmd_xlogin
                cmd_xlogin(type("Args", (), {"session": None, "port": None, "max_wait": 300.0, "browser": None})())
            elif choice == "5": print(WorkerController().deploy())
            elif choice == "6": print(WorkerController().sync_credentials())
            elif choice in ("7", "8"): print(WorkerController().run_action("start" if choice == "7" else "stop"))
            elif choice == "9":
                from .cli import cmd_terminal
                return cmd_terminal(None)
            else: print("Invalid choice."); continue
        except (EOFError, KeyboardInterrupt): print()
        except Exception as exc: print(f"\nError: {exc}")
        _pause()
