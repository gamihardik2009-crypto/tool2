"""Deploy and control the Telegram→X worker on the VPS (or Termux) over SSH.

The worker is fully self-contained (see the project `setup.sh`), so the manager
just pushes the code, runs setup, drops in the credentials + X session, and
starts it with the portable `run.sh` (pid + log — works without systemd, so it
also works on Termux and a plain VPS).
"""
from __future__ import annotations

import io
import tarfile
import time
from pathlib import Path

from . import activity, config, creds
from .remote import Remote, RemoteError

# Worker files the manager ships (everything the worker itself needs; the
# systemd deploy/ folder and the manager package are not needed on the worker).
WORKER_FILES = [
    "main.py", "collector.py", "x_publisher.py", "database.py", "health.py",
    "config.py", "session_keeper.py",
    "requirements.txt", "requirements-full.txt", ".env.example",
    "setup.sh", "run.sh",
]

REMOTE_DIR = "~/telegram-x"


def _make_archive() -> bytes:
    buf = io.BytesIO()
    root = config.resources_root()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name in WORKER_FILES:
            path = root / name
            if path.is_file():
                tar.add(path, arcname=name)
    return buf.getvalue()


def _worker_env(token: str, chat_id: str) -> str:
    return (
        "TELEGRAM_BOT_TOKEN={}\n"
        "TELEGRAM_CHAT_ID={}\n"
        "DATABASE_PATH=data/messages.db\n"
        "LOG_PATH=data/collector.log\n"
        "X_SESSION_PATH=data/x-session.json\n"
        "HEALTH_PATH=data/health.json\n"
    ).format(token.strip(), chat_id.strip())


class WorkerController:
    """Run deploy / start / stop / status / logs against a remote worker."""

    def __init__(self, remote_dir: str = REMOTE_DIR) -> None:
        self.remote_dir = remote_dir

    def _r(self, remote: Remote, cmd: str, timeout: float = 120) -> tuple[int, str]:
        code, out = remote.run(cmd, timeout=timeout)
        return code, out

    def deploy(self, token: str | None = None, chat_id: str | None = None,
               session_path: Path | None = None) -> str:
        token = token if token is not None else creds.bot_token()
        if not token:
            raise RemoteError("No Telegram bot token stored. Run `creds` first.")
        chat_id = chat_id if chat_id is not None else creds.chat_id()
        session_path = session_path or config.session_file_path()
        if not session_path.is_file():
            raise RemoteError(
                f"X session not found ({session_path}). Run `xlogin` first."
            )

        archive = _make_archive()
        env_script = _worker_env(token, chat_id)

        remote = Remote()
        remote.open()
        try:
            # 1. Upload worker code. (Home dir, not /tmp — Termux has no /tmp.)
            remote.put_bytes(archive, "~/telegram-x.tar.gz")
            code, out = self._r(
                remote,
                f"mkdir -p {self.remote_dir} && "
                f"tar -xzf ~/telegram-x.tar.gz -C {self.remote_dir} && "
                "rm -f ~/telegram-x.tar.gz && "
                f"cd {self.remote_dir} && sh setup.sh",
                timeout=900,  # pip install can take minutes on small hosts
            )
            if code != 0:
                raise RemoteError(f"Worker setup failed:\n{out}")

            # 2. Write .env and X session atomically.
            remote.put_bytes(env_script.encode(), f"{self.remote_dir}/.env")
            self._mkdirs(remote)
            remote.put_bytes(
                session_path.read_bytes(), f"{self.remote_dir}/data/x-session.json"
            )
            code, out = self._r(
                remote,
                f"chmod 600 {self.remote_dir}/.env "
                f"{self.remote_dir}/data/x-session.json",
            )
            if code != 0:
                raise RemoteError(f"Could not lock permissions:\n{out}")

            # 3. Start the worker.
            code, out = self._r(remote, f"cd {self.remote_dir} && sh run.sh start",
                                timeout=60)
            if code != 0:
                raise RemoteError(f"Could not start worker:\n{out}")

            # 4. Give it a few seconds, then confirm it is actually alive.
            time.sleep(5)
            code, out2 = self._r(remote, f"cd {self.remote_dir} && sh run.sh status",
                                 timeout=30)
            if "running" not in out2:
                logs = self._r(remote, f"cd {self.remote_dir} && sh run.sh logs 30",
                               timeout=30)[1]
                raise RemoteError(
                    f"Worker did not stay up (status: {out2}).\nLast logs:\n{logs}"
                )
            out = f"{out}\nWorker is up: {out2}"
        finally:
            remote.close()

        return out

    def sync_credentials(self, token: str | None = None, chat_id: str | None = None,
                         session_path: Path | None = None) -> str:
        """Update the running worker's .env and X session over SSH."""
        token = token if token is not None else creds.bot_token()
        if not token:
            raise RemoteError("No Telegram bot token stored. Run `creds` first.")
        session_path = session_path or config.session_file_path()
        if not session_path.is_file():
            raise RemoteError("X session not found. Run `xlogin` first.")
        remote = Remote(); remote.open()
        try:
            self._mkdirs(remote)
            remote.put_bytes(_worker_env(token, chat_id or creds.chat_id()).encode(), f"{self.remote_dir}/.env")
            remote.put_bytes(session_path.read_bytes(), f"{self.remote_dir}/data/x-session.json")
            code, out = self._r(remote, f"chmod 600 {self.remote_dir}/.env {self.remote_dir}/data/x-session.json && cd {self.remote_dir} && sh run.sh stop >/dev/null 2>&1 || true; cd {self.remote_dir} && sh run.sh start")
            if code != 0:
                raise RemoteError(out)
            return "Credentials synced to the worker and worker restarted."
        finally:
            remote.close()

    def _mkdirs(self, remote: Remote) -> None:
        self._r(remote, f"mkdir -p {self.remote_dir}/data")

    def run_action(self, action: str, n: int = 50) -> str:
        remote = Remote()
        remote.open()
        try:
            if action == "logs":
                code, out = self._r(
                    remote, f"cd {self.remote_dir} && sh run.sh logs {n}"
                )
            else:
                code, out = self._r(
                    remote, f"cd {self.remote_dir} && sh run.sh {action}"
                )
        finally:
            remote.close()
        return f"{out}" if code != 0 else out
