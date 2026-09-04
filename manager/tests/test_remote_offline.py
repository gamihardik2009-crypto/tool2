"""Offline checks for remote/SSH helpers, credentials, profile and activity.

These validate the non-network parts of the SSH layer (shell-quoting, profile
round-trip) plus credential storage and the activity-history log. A live SSH
server connection is not exercised here.

Key generation is no longer manager-managed: SSH now uses the user's native
OpenSSH key/config, so `ensure_keypair` is disabled and raises. We assert that
disabled behavior instead of trying to generate a keypair. POSIX `chmod` checks
are guarded so the suite also runs green on Windows.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telegram_x_manager import activity, creds
from telegram_x_manager.remote import (
    ConnectionProfile, RemoteError, ensure_keypair, load_profile, save_profile, quote,
)

tmp = Path(tempfile.mkdtemp(prefix="tzx-remote-"))

# 1. Key generation is disabled now (native OpenSSH owns keys).
try:
    ensure_keypair()
    raise AssertionError("ensure_keypair() should raise (key gen is disabled)")
except RemoteError:
    print("OK ensure_keypair is disabled (native OpenSSH handles keys)")

# 2. Shell quoting prevents injection.
assert quote("bitwalker's data; rm -rf ~") == "'bitwalker'\\''s data; rm -rf ~'"
print("OK quote is injection-safe")

# 3. Profile round-trip.
prof = ConnectionProfile(host="203.0.113.7", username="deploy", port=2222)
p = tmp / "connection.json"
save_profile(prof, p)
assert load_profile(p) == prof
print("OK profile save/load round-trip")

# 4. Credential storage round-trip (token redacted in output, never printed).
c = tmp / "creds.json"
creds.save("123456:ABC-SECRET-TOKEN", "-100123456", c)
assert creds.bot_token(c) == "123456:ABC-SECRET-TOKEN"
assert creds.chat_id(c) == "-100123456"
if os.name != "nt":  # POSIX enforces 0600; Windows has no POSIX mode bits.
    assert (c.stat().st_mode & 0o777) == 0o600
    print("OK creds save/load (chmod 600)")
else:
    print("OK creds save/load (Windows: no POSIX mode-bit check)")

# 5. Activity history is trimmed to the newest N (default 10).
hist = tmp / "activity.json"
for i in range(15):
    activity.record(f"action-{i}", ok=True, detail="d", path=hist)
entries = activity.history(limit=10, path=hist)
assert len(entries) == 10, f"expected 10, got {len(entries)}"
assert entries[0]["action"] == "action-5", entries[0]["action"]
assert entries[-1]["action"] == "action-14"
print("OK activity history trimmed to newest 10")

print("\nAll remote/credential/activity checks passed.")
