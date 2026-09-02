from __future__ import annotations

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, Label, Static

from . import activity, config, creds


class FormScreen(ModalScreen[dict[str, str] | None]):
    def __init__(self, kind: str) -> None:
        super().__init__()
        self.kind = kind

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Connect to worker" if self.kind == "ssh" else "Telegram credentials", classes="dialog-title")
            if self.kind == "ssh":
                yield Label("Use a normal address or an automatically detected Tailscale device.", id="ssh_hint")
                yield Input(placeholder="Host or SSH alias", id="host")
                yield Input(placeholder="Username (for example root)", id="username")
                yield Input(value="22", placeholder="Port", id="port")
            else:
                yield Input(placeholder="Bot token", password=True, id="token")
                yield Input(placeholder="Chat ID (optional)", id="chat_id")
            with Horizontal(classes="dialog-actions"):
                yield Button("Cancel", id="cancel")
                yield Button("Save", id="submit", variant="primary")

    def on_mount(self) -> None:
        if self.kind != "ssh":
            return
        from .tailscale import preferred_termux_peer
        peer = preferred_termux_peer()
        if peer:
            self.query_one("#host", Input).value = peer["ip"]
            if peer["os"] == "android":
                self.query_one("#port", Input).value = "8022"
            self.query_one("#ssh_hint", Label).update(
                f"Tailscale device found: {peer['name']} ({peer['ip']})"
            )
        else:
            self.query_one("#ssh_hint", Label).update(
                "No online Tailscale device detected. Enter an IP, hostname, or SSH alias."
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
            return
        ids = ("host", "username", "port") if self.kind == "ssh" else ("token", "chat_id")
        values = {key: self.query_one(f"#{key}", Input).value.strip() for key in ids}
        if self.kind == "ssh":
            values["username"] = values["username"] or "root"
            values["port"] = values["port"] or "22"
        self.dismiss(values)


class ManagerApp(App):
    TITLE = "Telegram-X Manager"
    SUB_TITLE = "Worker control"
    CSS = """
    Screen { background: #10151c; color: #e8edf2; }
    Header { background: #17212b; }
    #content { padding: 1 3; }
    #intro { color: #9fb0bf; margin-bottom: 1; }
    #statuses { height: 9; }
    .status { width: 1fr; height: 7; margin-right: 1; padding: 1 2;
              background: #18232e; border: round #33485c; }
    .status-title { text-style: bold; color: #69d2e7; }
    .status-value { margin-top: 1; text-style: bold; }
    .status-detail { color: #9fb0bf; margin-top: 1; }
    #actions { height: 5; margin-top: 1; }
    #actions Button { width: 1fr; margin-right: 1; height: 3; }
    #message { margin-top: 1; padding: 1 2; height: 4; background: #131c25;
               border-left: thick #69d2e7; color: #c7d4df; }
    ModalScreen { align: center middle; background: #000000 60%; }
    #dialog { width: 62; height: auto; padding: 1 2; background: #18232e;
              border: round #69d2e7; }
    .dialog-title { text-style: bold; color: #69d2e7; margin-bottom: 1; }
    #dialog Input { margin-bottom: 1; }
    .dialog-actions { height: 3; align-horizontal: right; }
    .dialog-actions Button { margin-left: 1; }
    """
    BINDINGS = [("r", "refresh", "Refresh"), ("q", "quit", "Quit")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="content"):
            yield Static("Live status and the four actions needed to run your worker.", id="intro")
            with Horizontal(id="statuses"):
                yield self.card("Telegram", "Checking...", "Validating bot token", "telegram")
                yield self.card("X session", "Checking...", "Checking login session", "x")
                yield self.card("SSH + worker", "Checking...", "Looking for target", "workflow")
                yield self.card("Chrome profile", "Checking...", "Dedicated login profile", "browser")
            with Horizontal(id="actions"):
                yield Button("SSH connection", id="connect", variant="primary")
                yield Button("Telegram token", id="credentials")
                yield Button("X login", id="xlogin")
                yield Button("Start worker", id="worker", variant="success")
            yield Static("Ready.", id="message")
        yield Footer()

    @staticmethod
    def card(title: str, value: str, detail: str, ident: str) -> Static:
        return Static(f"[status-title]{title}[/]\n[status-value]{value}[/]\n[status-detail]{detail}[/]",
                      id=ident, classes="status", markup=True)

    def on_mount(self) -> None:
        self.refresh_status()

    def action_refresh(self) -> None:
        self.refresh_status()

    def message(self, text: str) -> None:
        self.query_one("#message", Static).update(text)

    @work(thread=True, exclusive=True, group="health")
    def refresh_status(self) -> None:
        from .health import run_checks
        self.call_from_thread(self.message, "Refreshing Telegram, X, SSH and worker status...")
        report = run_checks()
        t, x, w, bp = report["telegram"], report["x_session"], report["workflow"], report.get("browser_profile", {})
        service = str(w.get("service") or "not running")
        running = service == "active" or service.startswith("running")
        cards = {
            "telegram": ("Telegram", "[green]Connected[/green]" if t.get("ok") else "[red]Needs setup[/red]", t.get("detail", "")),
            "x": ("X session", "[green]Connected[/green]" if x.get("ok") else "[red]Needs login[/red]", x.get("detail", "")),
            "workflow": ("SSH + worker", "[green]Worker running[/green]" if running else ("[yellow]SSH connected[/yellow]" if w.get("connected") else "[red]Not connected[/red]"), f"{w.get('username', '')}@{w.get('host', '')}" if w.get("connected") else w.get("detail", "Add SSH connection")),
            "browser": ("Chrome profile", "[green]Ready[/green]" if bp.get("exists") else "[yellow]Not created[/yellow]", bp.get("path", "Dedicated X login profile")),
        }
        for ident, (title, value, detail) in cards.items():
            text = f"[status-title]{title}[/]\n[status-value]{value}[/]\n[status-detail]{detail}[/]"
            self.call_from_thread(self.query_one(f"#{ident}", Static).update, text)
        button = self.query_one("#worker", Button)
        self.call_from_thread(setattr, button, "label", "Stop worker" if running else "Start worker")
        self.call_from_thread(setattr, button, "variant", "error" if running else "success")
        self.call_from_thread(self.message, "Status refreshed. Press R anytime to refresh.")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "connect":
            self.push_screen(FormScreen("ssh"), self.connect_result)
        elif event.button.id == "credentials":
            self.push_screen(FormScreen("telegram"), self.credentials_result)
        elif event.button.id == "xlogin":
            self.login_x()
        elif event.button.id == "worker":
            self.control_worker("stop" if "Stop" in str(event.button.label) else "start")

    def connect_result(self, values: dict[str, str] | None) -> None:
        if values:
            self.connect_ssh(values)

    def credentials_result(self, values: dict[str, str] | None) -> None:
        if values:
            self.save_credentials(values)

    @work(thread=True)
    def connect_ssh(self, values: dict[str, str]) -> None:
        from .remote import ConnectionProfile, save_profile, verify_connection
        self.call_from_thread(self.message, "Connecting over SSH...")
        try:
            profile = ConnectionProfile(values["host"], values["username"], int(values["port"]))
            verify_connection(profile)
            save_profile(profile)
            activity.record("connect", True, f"connected to {profile.username}@{profile.host}")
            self.call_from_thread(self.message, "SSH connection saved successfully.")
            self.refresh_status()
        except Exception as exc:
            activity.record("connect", False, str(exc))
            self.call_from_thread(self.message, f"SSH connection failed: {exc}")

    @work(thread=True)
    def save_credentials(self, values: dict[str, str]) -> None:
        from .health import check_bot_token
        if not values["token"]:
            self.call_from_thread(self.message, "Telegram bot token is required.")
            return
        self.call_from_thread(self.message, "Validating Telegram bot token...")
        creds.save(values["token"], values["chat_id"])
        result = check_bot_token(values["token"])
        activity.record("creds", bool(result.get("ok")), "bot token validation completed")
        self.call_from_thread(self.message, result.get("detail", "Credentials saved."))
        self.refresh_status()

    @work(thread=True)
    def login_x(self) -> None:
        from .session import xlogin
        self.call_from_thread(self.message, "Opening Chrome. Complete the X login in the browser window...")
        try:
            xlogin(config.session_file_path(), config.browser_profile_dir())
            activity.record("xlogin", True, "session saved")
            self.call_from_thread(self.message, "X session captured successfully.")
            self.refresh_status()
        except Exception as exc:
            activity.record("xlogin", False, str(exc))
            self.call_from_thread(self.message, f"X login failed: {exc}")

    @work(thread=True)
    def control_worker(self, action: str) -> None:
        from .worker import WorkerController
        self.call_from_thread(self.message, f"{action.title()}ing worker...")
        try:
            result = WorkerController().run_action(action)
            activity.record(f"control/{action}", True, f"worker {action}")
            self.call_from_thread(self.message, result)
            self.refresh_status()
        except Exception as exc:
            activity.record(f"control/{action}", False, str(exc))
            self.call_from_thread(self.message, f"Worker action failed: {exc}")


def run() -> int:
    """Run a small dependency-light terminal menu for the manager."""
    from .health import render, run_checks
    from .worker import WorkerController

    while True:
        print("\nTelegram-X Manager")
        print("1) Refresh status   2) SSH connect   3) Telegram token")
        print("4) X login          5) Deploy         6) Sync credentials")
        print("7) Start/stop worker 8) Open VPS terminal  0) Exit")
        choice = input("> ").strip()
        try:
            if choice == "0":
                return 0
            if choice == "1":
                print(render(run_checks()))
            elif choice == "2":
                from .cli import cmd_connect
                cmd_connect(type("Args", (), {"host": None, "user": None, "port": 22})())
            elif choice == "3":
                from .cli import cmd_creds
                cmd_creds(type("Args", (), {"token": None, "chat_id": None})())
            elif choice == "4":
                from .cli import cmd_xlogin
                cmd_xlogin(type("Args", (), {"session": None, "port": None, "max_wait": 300.0, "browser": None})())
            elif choice == "5":
                print(WorkerController().deploy())
            elif choice == "6":
                print(WorkerController().sync_credentials())
            elif choice == "7":
                current = run_checks().get("workflow", {}).get("service", "")
                action = "stop" if str(current).startswith(("running", "active")) else "start"
                print(WorkerController().run_action(action))
            elif choice == "8":
                from .cli import cmd_terminal
                return cmd_terminal(None)
            else:
                print("Choose a number from 0 to 7.")
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        except Exception as exc:
            print(f"Error: {exc}")
