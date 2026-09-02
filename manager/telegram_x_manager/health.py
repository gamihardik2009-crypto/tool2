"""Manager health: one clear screen of everything a non-technical user cares about.

Checks (in order, each independent):
  * Telegram   – API reachable?  bot token valid? (calls Telegram getMe)
  * X session  – is the captured session valid for tweetkit?
  * Workflow   – is the manager connected to the VPS? is the worker service
                 running? what does its health JSON say?
  * Activity   – last N manager actions (from the local history log).

Each remote check is best-effort: if we're not connected or a service is missing
it reports that gracefully instead of crashing.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen, URLError

from . import activity, config, creds
from .remote import Remote, RemoteError, load_profile

TELEGRAM_API = "https://api.telegram.org"


# --------------------------------------------------------------------------- #
# Local credential checks
# --------------------------------------------------------------------------- #
def check_bot_token(token: str) -> dict:
    """Return {ok, reachable, username, detail}."""
    if not token:
        return {"ok": False, "reachable": True, "detail": "No bot token stored yet (run `creds`)."}
    try:
        with urlopen(f"{TELEGRAM_API}/bot{token}/getMe", timeout=15) as resp:
            payload = json.load(resp)
    except URLError:
        return {"ok": False, "reachable": False,
                "detail": "Could not reach api.telegram.org (network/offline)."}
    except Exception as exc:  # e.g. HTTPError, JSON error
        return {"ok": False, "reachable": True, "detail": f"Bad response: {exc}"}
    ok = bool(payload.get("ok"))
    username = ""
    if ok:
        username = payload.get("result", {}).get("username", "")
    return {"ok": ok, "reachable": True, "username": username,
            "detail": f"Bot @{username}" if ok else (payload.get("description") or "Rejected by Telegram")}


def check_x_session() -> dict:
    """Validate the stored X session using tweetkit whoami()."""
    path = config.session_file_path()
    if not path.is_file():
        return {"ok": False, "detail": "No X session captured yet (run `xlogin`)."}
    try:
        from tweetkit_x import TweetKit
        from tweetkit_x.cookie import build_cookie_string
        flat = json.loads(path.read_text(encoding="utf-8"))
        cookie_string = build_cookie_string(flat)
        identity = TweetKit(cookie=cookie_string).whoami()
        return {"ok": bool(identity), "detail": f"X user {identity.get('user_id', 'unknown')}"}
    except Exception as exc:
        return {"ok": False, "detail": f"Session invalid or expired: {exc}"}


# --------------------------------------------------------------------------- #
# Remote (VPS) checks
# --------------------------------------------------------------------------- #
def check_workflow(timeout: float = 20) -> dict:
    """Return {connected, host, username, service, health} about the VPS worker."""
    result = {"connected": False}
    profile = load_profile()
    if profile:
        result["host"] = profile.host
        result["username"] = profile.username
    try:
        with Remote() as remote:
            result["connected"] = True
            # Portable worker (this project): health lives under ~/telegram-x/data.
            # systemd VPS install uses /var/lib/telegram-x/health.json instead.
            code, service = remote.run(
                "cd ~/telegram-x 2>/dev/null && sh run.sh status 2>/dev/null "
                "|| echo not-running", timeout=timeout,
            )
            result["service"] = (service or "not-running").strip()
            for candidate in ("~/telegram-x/data/health.json",
                              "/var/lib/telegram-x/health.json"):
                try:
                    raw = remote.download(candidate, timeout=timeout)
                    result["health"] = json.loads(raw)
                    break
                except Exception:
                    continue
    except RemoteError as exc:
        result["detail"] = str(exc)
    except Exception as exc:
        result["detail"] = f"Connection error: {exc}"
    return result


# --------------------------------------------------------------------------- #
# Assembly + CLI
# --------------------------------------------------------------------------- #
def check_telegram() -> dict:
    return check_bot_token(creds.bot_token())


def run_checks() -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "telegram": check_telegram(),
        "x_session": check_x_session(),
        "browser_profile": {
            "exists": config.browser_profile_dir().is_dir(),
            "path": str(config.browser_profile_dir()),
        },
        "workflow": check_workflow(),
        "activity_history": activity.history(limit=activity.DEFAULT_LIMIT),
    }


def render(report: dict) -> str:
    lines = ["Telegram → X Manager — Health", "=" * 32, ""]

    t = report["telegram"]
    lines.append("Telegram pipeline")
    lines.append(f"  reachable   : {'yes' if t.get('reachable') else 'no'}")
    lines.append(f"  bot token   : {'✅ valid (' + (t.get('username') or '?') + ')' if t.get('ok') else '❌ ' + t['detail']}")
    lines.append("")

    x = report["x_session"]
    lines.append("X session")
    lines.append(f"  {'✅ valid — ' + x['detail'] if x.get('ok') else '❌ ' + x['detail']}")
    lines.append("")

    bp = report.get("browser_profile", {})
    lines.append("Manager Chrome profile")
    lines.append(f"  {'✅ ready' if bp.get('exists') else '⚠ not created yet'} ({bp.get('path', '')})")
    lines.append("")

    w = report["workflow"]
    lines.append("Workflow (VPS)")
    if w.get("connected"):
        lines.append(f"  connected : ✅ ({w.get('username', '')}@{w.get('host', '')})")
        service = str(w.get('service') or 'not-running')
        active = service == 'active' or service.startswith('running')
        lines.append(f"  service   : {'✅ active' if active else '⚠ ' + service}")
        hw = w.get("health")
        if hw:
            lines.append(f"  last health: {hw.get('status', '?')} ({hw.get('updated_at', '?')})")
    else:
        lines.append(f"  connected : ❌ {w.get('detail', 'not configured (run `connect`)')}")
    lines.append("")

    lines.append("Recent activity (last {})".format(len(report["activity_history"])))
    if not report["activity_history"]:
        lines.append("  (none yet)")
    for entry in report["activity_history"]:
        mark = "✅" if entry.get("ok") else "❌"
        lines.append(f"  {mark} {entry.get('ts', '')} {entry.get('action', '')} — {entry.get('detail', '')}")
    return "\n".join(lines) + "\n"


def cmd_health() -> int:
    report = run_checks()
    print(render(report))
    return 0
