#!/bin/bash
# Installs the system-wide Linux pieces. Read it first, then run it yourself with
# sudo:  sudo packaging/linux/install-system.sh
#
# It creates the clevo-kbd group, adds you to it, installs the udev rule that
# lets that group write the backlight, and enables restore after resume. It does
# not install or load any kernel driver.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
	echo "Run this with sudo." >&2
	exit 1
fi
target_user="${SUDO_USER:-}"
if [ -z "$target_user" ] || [ "$target_user" = "root" ]; then
	echo "Run this with sudo from your own account, so it knows who to add." >&2
	exit 1
fi

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

groupadd --system --force clevo-kbd
usermod --append --groups clevo-kbd "$target_user"

install -m 0644 "$here/90-clevo-kbd.rules" /etc/udev/rules.d/90-clevo-kbd.rules
udevadm control --reload
# Applies the rule to any backlight LED that already exists.
udevadm trigger --action=add --subsystem-match=leds --sysname-match='*:kbd_backlight*'

install -m 0644 "$here/clevo-kbd-resume@.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable "clevo-kbd-resume@${target_user}.service"

echo "Done. Reboot so the clevo-kbd group takes effect."
