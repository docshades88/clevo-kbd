#!/bin/bash
# Installs the per-user Linux pieces. Needs no root and changes nothing outside
# your home directory. Run it yourself:  packaging/linux/install-user.sh
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
config_home="${XDG_CONFIG_HOME:-$HOME/.config}"
data_home="${XDG_DATA_HOME:-$HOME/.local/share}"
bin="$HOME/.local/bin/clevo-kbd"

mkdir -p "$HOME/.local/bin" "$data_home/applications" "$config_home/systemd/user"

ln -sfn "$repo/clevo-kbd" "$bin"
sed "s|@BIN@|$bin|" "$here/clevo-kbd.desktop" > "$data_home/applications/clevo-kbd.desktop"
install -m 0644 "$here/clevo-kbd-restore.service" "$config_home/systemd/user/"

systemctl --user daemon-reload
systemctl --user enable clevo-kbd-restore.service

echo "Installed: $bin"
echo "Installed: $data_home/applications/clevo-kbd.desktop"
echo "Enabled:   clevo-kbd-restore.service (restores at login)"
