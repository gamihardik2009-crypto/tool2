"""telegram_x_manager — CLI to control a Telegram→X VPS worker from your PC.

Commands:
  * xlogin   – capture/refresh the X session via your real browser (CDP).
  * connect  – one-time, password-based setup of key-based SSH access to the VPS
               (thereafter every op is key-auth, no password).
  * creds    – store the Telegram bot token + chat id locally.
  * health   – show telegram pipeline, X session, workflow connection, activity.
  * status   – quickly test the SSH connection to the VPS.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from . import config


def add_xlogin_parser(sub) -> None:
    p = sub.add_parser("xlogin", help="Log into X in a real browser and save the session")
    p.add_argument("--port", type=int, default=None,
                   help="CDP debugging port (default: auto-pick a free one)")
    p.add_argument("--max-wait", type=float, default=300.0,
                   help="Seconds to wait for the X login (default: 300)")
    p.add_argument("--session", type=str, default=None,
                   help="Output session file path (default: the manager state dir)")
    p.add_argument("--browser", type=str, default=None,
                   help="Explicit path to a Chrome/Chromium/Edge binary (skips auto-detection)")
    p.set_defaults(func=cmd_xlogin)


def cmd_xlogin(args) -> int:
    from . import activity
    from .session import xlogin
    try:
        session_path = config.session_file_path() if not args.session else Path(args.session).expanduser()
        profile_dir = config.browser_profile_dir()
        xlogin(session_path, profile_dir, port=args.port, max_wait=args.max_wait,
               browser_path=args.browser)
        activity.record("xlogin", True, f"session saved → {session_path}")
        return 0
    except Exception as exc:
        activity.record("xlogin", False, str(exc))
        print(f"❌ xlogin failed: {exc}")
        return 1


def add_connect_parser(sub) -> None:
    p = sub.add_parser("connect", help="Set up access to the VPS")
    p.add_argument("--host", help="VPS IP or hostname")
    p.add_argument("--user", help="VPS SSH username")
    p.add_argument("--port", type=int, default=22)
    p.set_defaults(func=cmd_connect)


def cmd_connect(args) -> int:
    from . import activity
    from .remote import ConnectionProfile, save_profile, verify_connection

    try:
        host = args.host or input("VPS IP/hostname: ").strip()
        user = args.user or input("VPS SSH username [root]: ").strip() or "root"
        if not host:
            raise SystemExit("Host is required.")
        port = args.port or 22
        profile = ConnectionProfile(host=host, username=user, port=port, alias=getattr(args, "alias", ""))

        username = verify_connection(profile)
        save_profile(profile)
        activity.record("connect", True, f"verified existing SSH connection to {user}@{host}")
        print(f"✅ Existing SSH connection verified for {username}@{host}:{port}.")
        print("Next: run `creds`, `xlogin`, then `deploy` or `sync`.")
        return 0
    except Exception as exc:
        activity.record("connect", False, str(exc))
        print(f"❌ connect failed: {exc}")
        print("Check that the host, username, port, and existing SSH key/config are correct.")
        return 1


def add_creds_parser(sub) -> None:
    p = sub.add_parser("creds", help="Store the Telegram bot token + chat id locally")
    p.add_argument("--token", help="Telegram bot token from @BotFather")
    p.add_argument("--chat-id", help="Optional Telegram group id (negative number)")
    p.set_defaults(func=cmd_creds)


def cmd_creds(args) -> int:
    import getpass
    from . import activity, creds
    from .health import check_bot_token
    try:
        token = args.token or getpass.getpass("Telegram bot token (hidden): ").strip()
        if not token:
            raise SystemExit("Bot token is required.")
        chat_id = args.chat_id if args.chat_id is not None else input("Telegram chat id (optional): ").strip()
        creds.save(token, chat_id)
        print("Credentials stored locally.")
        result = check_bot_token(token)
        mark = "valid" if result.get("ok") else "rejected"
        activity.record("creds", bool(result.get("ok")),
                        f"bot token {mark} {result.get('detail', '')}")
        print(f"Bot token check: {mark} — {result.get('detail', '')}")
        return 0
    except Exception as exc:
        activity.record("creds", False, str(exc))
        print(f"❌ creds failed: {exc}")
        return 1


def add_health_parser(sub) -> None:
    p = sub.add_parser("health", help="Show manager, telegram, X, workflow and activity status")
    p.set_defaults(func=cmd_health)


def cmd_health(_args) -> int:
    from . import activity
    from .health import run_checks, render
    try:
        report = run_checks()
        print(render(report))
        activity.record("health", True, "health report shown")
        return 0
    except Exception as exc:
        activity.record("health", False, str(exc))
        print(f"❌ health failed: {exc}")
        return 1


def add_status_parser(sub) -> None:
    p = sub.add_parser("status", help="Quickly test the SSH connection to the VPS")
    p.set_defaults(func=cmd_status)

def add_terminal_parser(sub) -> None:
    p = sub.add_parser("terminal", help="Open an interactive terminal on the VPS")
    p.set_defaults(func=cmd_terminal)

def cmd_terminal(_args) -> int:
    from .remote import Remote, load_profile
    profile = load_profile()
    if profile is None:
        print("Not connected - run `connect` first.")
        return 1
    try:
        return Remote(profile).interactive()
    except Exception as exc:
        print(f"Could not open VPS terminal: {exc}")
        return 1


def cmd_status(_args) -> int:
    from . import activity
    from .remote import Remote, RemoteError, load_profile
    profile = load_profile()
    if profile is None:
        print("Not connected — run `connect` first.")
        return 1
    try:
        with Remote() as remote:
            remote.run("echo ok; id -un")
        print(f"✅ Connected to {profile.username}@{profile.host}:{profile.port}")
        activity.record("status", True, f"connected to {profile.host}")
        return 0
    except RemoteError as exc:
        activity.record("status", False, str(exc))
        print(f"❌ Not connected: {exc}")
        return 1


def add_deploy_parser(sub) -> None:
    p = sub.add_parser("deploy", help="Push the worker to the VPS and start it")
    p.add_argument("--token", help="Telegram bot token (default: the stored one)")
    p.add_argument("--chat-id", help="Optional Telegram group id")
    p.add_argument("--session", help="Path to X session file (default: the captured one)")
    p.set_defaults(func=cmd_deploy)


def cmd_deploy(args) -> int:
    from . import activity
    from .worker import WorkerController
    try:
        ctl = WorkerController()
        out = ctl.deploy(token=args.token, chat_id=args.chat_id,
                         session_path=Path(args.session) if args.session else None)
        print(out)
        activity.record("deploy", True, "worker deployed and started")
        return 0
    except Exception as exc:
        activity.record("deploy", False, str(exc))
        print(f"❌ deploy failed: {exc}")
        return 1


def add_control_parser(sub) -> None:
    p = sub.add_parser("control", help="start, stop, status or logs the worker on the VPS")
    p.add_argument("action", choices=["start", "stop", "status", "logs"])
    p.add_argument("--lines", type=int, default=50, help="lines for `logs`")
    p.set_defaults(func=cmd_control)

def add_sync_parser(sub) -> None:
    p = sub.add_parser("sync", help="Send Telegram and X credentials to the worker over SSH")
    p.set_defaults(func=cmd_sync)

def cmd_sync(_args) -> int:
    from .worker import WorkerController
    try:
        print(WorkerController().sync_credentials())
        return 0
    except Exception as exc:
        print(f"❌ sync failed: {exc}")
        return 1


def add_history_parser(sub) -> None:
    p = sub.add_parser("history", help="Show recent manager activity")
    p.add_argument("--lines", type=int, default=15)
    p.set_defaults(func=cmd_history)


def cmd_history(args) -> int:
    from .activity import history
    for entry in history(max(1, args.lines)):
        mark = "OK" if entry.get("ok") else "FAIL"
        print(f"{mark} {entry.get('ts', '')} {entry.get('action', '')} - {entry.get('detail', '')}")
    return 0


def cmd_tui(_args) -> int:
    from .tui import run
    return run()


def cmd_control(args) -> int:
    from . import activity
    from .worker import WorkerController
    try:
        out = WorkerController().run_action(args.action, args.lines)
        print(out)
        if args.action in ("start", "stop"):
            activity.record("control/" + args.action, True, "worker " + args.action)
        return 0
    except Exception as exc:
        activity.record("control/" + args.action, False, str(exc))
        print(f"❌ {args.action} failed: {exc}")
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="telegram-x-manager",
        description="Control a Telegram→X VPS worker from your PC.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    add_xlogin_parser(sub)
    add_connect_parser(sub)
    add_creds_parser(sub)
    add_health_parser(sub)
    add_status_parser(sub)
    add_terminal_parser(sub)
    add_deploy_parser(sub)
    add_control_parser(sub)
    add_sync_parser(sub)
    add_history_parser(sub)
    sub.add_parser("tui", help="Open the interactive terminal interface").set_defaults(func=cmd_tui)
    return parser


def main(argv: list[str] | None = None) -> int:
    if argv is None and not __import__('sys').argv[1:]:
        return cmd_tui(None)
    args = build_parser().parse_args(argv)
    return int(args.func(args))
