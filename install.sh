#!/usr/bin/env bash
set -euo pipefail

BASE="${XDG_DATA_HOME:-$HOME/.local/share}/telegram-x-manager-tool2"
REPO="https://github.com/gamihardik2009-crypto/tool2.git"
BIN="${XDG_BIN_HOME:-$HOME/.local/bin}"

if [ ! -d "$BASE/.git" ]; then
  mkdir -p "$(dirname "$BASE")"
  git clone "$REPO" "$BASE"
else
  git -C "$BASE" pull --ff-only
fi

cd "$BASE/manager"
"${PYTHON:-python3}" -m venv .venv
"$BASE/manager/.venv/bin/python" -m pip install --upgrade pip >/dev/null
"$BASE/manager/.venv/bin/python" -m pip install -e . >/dev/null

mkdir -p "$BIN"
cat > "$BIN/tool2" <<EOF
#!/usr/bin/env bash
exec "$BASE/manager/.venv/bin/telegram-x-manager" tui "\$@"
EOF
chmod 755 "$BIN/tool2"

for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
  if [ -f "$rc" ] && ! grep -Fq "telegram-x-manager PATH" "$rc"; then
    printf '\n# telegram-x-manager PATH\nexport PATH="%s:$PATH"\n' "$BIN" >> "$rc"
  fi
done
case ":${PATH}:" in
  *":$BIN:"*) ;;
  *) echo "Run this once in the current terminal: export PATH=\"$BIN:\$PATH\"" ;;
esac
echo "Installed. Start the manager from anywhere with: tool2"
