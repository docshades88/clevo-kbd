# clevo-kbd

Colour and brightness control for a three-zone keyboard backlight on Linux: a window
and a command line on one shared backend.

## Tested on

One machine, and nothing else:

- Laptop: Clevo P650HS-G (board `P65_67HSHP`)
- BIOS: 1.05.05
- EC firmware: 1.05.01
- Distribution: Manjaro
- Driver: `tuxedo-drivers` 4.24.0
- Secure Boot: disabled

Everything else is untested, including other Clevo models and this model on other
firmware.

On that machine the window, the commands and restore at login have run on the real
keyboard. Restore after resume was seen to finish once there. The colours came through a
suspend without it.

## What it needs

- Python 3.
- PySide6, for the window only. The command line runs without it.
- A kernel driver that exposes the LED devices `rgb:kbd_backlight`,
  `rgb:kbd_backlight_1` and `rgb:kbd_backlight_2`.

This app installs no driver. The tested machine uses `tuxedo-drivers`, which is
third-party software: see [Install the driver](#install-the-driver). This project is
not affiliated with Clevo or TUXEDO.

Windows is not supported today.

## Install the app

Any folder works.

```bash
git clone https://github.com/docshades88/clevo-kbd
cd clevo-kbd
packaging/linux/install-user.sh
sudo packaging/linux/install-system.sh
```

Read both scripts first, because the second one runs as root. Run them in this order:
the system script enables a service that needs the link the user script creates.

- `install-user.sh` needs no root. It links `~/.local/bin/clevo-kbd` to this clone, adds
  a menu entry, and enables restore at login. If you move the clone, run it again.
- `install-system.sh` creates the `clevo-kbd` group, adds you to it, installs a udev
  rule that lets that group write the backlight, and enables restore after resume.
  It installs no driver. Restore after resume looks for the app under `/home/<user>`,
  so it fails if your home directory is anywhere else.

**Then reboot,** to pick up the new group. Logging out is not enough when your user
manager lingers. After the reboot, `id -nG` must list `clevo-kbd`.

If `clevo-kbd` is not found, `~/.local/bin` is not on your `PATH`. Add it, or use the
full path. Until a driver is loaded, `clevo-kbd status` says no backlight device was
found.

## Commands

```bash
clevo-kbd status
clevo-kbd set --zone left --color '#ff0000'
clevo-kbd brightness 128
clevo-kbd off
clevo-kbd on
clevo-kbd apply
clevo-kbd gui
```

`status` shows the zones, colours and brightness. `--zone` takes `left`, `centre`,
`right` or `all`. `brightness` takes 0 to the maximum, which is 255 on the tested
machine. `off` keeps the saved brightness. `apply` re-applies the saved state.

Exit codes: 0 fine, 1 other error, 2 bad value, 3 no backlight device, 4 not allowed to
write, 5 no backend for this operating system.

Colours are per zone. Brightness is one value for the whole keyboard, because the tested
driver and firmware have a single brightness setting.

Settings are saved in `~/.config/clevo-kbd/state.json`, or under `$XDG_CONFIG_HOME` if
that is set. A value is saved only after the hardware accepted it.

In the window, the colour dialog stays open and applies as you drag. Close it when you
are done.

## Install the driver

Check first. If this lists the three LED devices, you already have a driver. Skip the
numbered steps, but still read the battery warning below.

```bash
ls /sys/class/leds | grep kbd_backlight
```

Otherwise, read this whole section before you install anything. The steps use Manjaro's
tools and assume Grub, because that is what was tested. They are a tidied version of
what was done on that one machine, and they have not been repeated from scratch. If you
do not boot with Grub, you need your own way to add a kernel parameter for one boot.

### What can go wrong

**Your firmware.** Compare yours with the tested machine first. Neither command changes
anything.

```bash
cat /sys/class/dmi/id/board_name /sys/class/dmi/id/bios_version
sudo sha256sum /sys/firmware/acpi/tables/DSDT
```

The tested machine prints `P65_67HSHP`, `1.05.05 02/23/2017` and
`cf5e1146671054d236d741d31478fb35d6d45cdd74032357297b3573dc94277c`. Linux does not show
the EC version: read `KBC/EC Firmware Revision` on the Main page of BIOS Setup, which
shows 1.05.01 there. The hash may differ on the same BIOS with different RAM, but then
your ACPI tables are still unread.

**If any of these differs, stop here unless you accept the following.**

- On other firmware, no one on this project has checked what this driver does. That
  includes the tested laptop on a different BIOS or EC version. The worst case is
  unknown, and lasting firmware damage cannot be ruled out.
- When it loads, the driver sends the firmware a battery write command (`0x76`) to
  detect a charge limit feature. The tested machine's ACPI tables show that this changes
  nothing. On other firmware it has not been read.
- `tuxedo-drivers` is written for TUXEDO's laptops, and its compatibility check lets the
  tested machine through only because the CPU is old. Passing it does not mean your
  machine is supported.

Even on the tested firmware, what the embedded controller does inside its own code could
not be checked.

**Battery controls.** On the tested machine, loading this driver adds battery controls,
and it may on yours. Writes to them may persist in firmware, and removing the driver
does not undo them.

> **Do not write to `charge_type` or `charge_control_*`, and do not set a charge limit
> from your desktop: not "preserve battery health" in GNOME Settings, Power, not the
> charge limit in KDE's power settings, and not any other tool that sets one.**
>
> Those files appear under `/sys/class/power_supply/`, beside your battery. In GNOME the
> setting is one click with no password. If your firmware has battery settings, change
> them in BIOS Setup and nowhere else. There is no exception.

### Before first load

1. Make a live USB of your distribution and start it from the firmware boot menu. Check
   that it can reach your installed system. On Manjaro run `sudo manjaro-chroot -a`,
   then `exit`. On the tested machine F2 opens BIOS Setup and F7 opens the boot menu.
2. Photograph every page of BIOS Setup, including anything about the battery.
3. Copy [Recovery](#recovery) somewhere other than this laptop, on paper or on another
   device. If the laptop will not boot, this page is out of reach.
4. Find your own Grub entry, and keep it with your copy of Recovery. The first command
   prints the entry Grub saved, if it saves one. The second lists your entries, with
   each entry's id quoted after `$menuentry_id_option`.

   ```bash
   grep '^saved_entry' /boot/grub/grubenv
   sudo grep -E '^menuentry ' /boot/grub/grub.cfg
   ```

5. Save your work and plug in AC.

### 1. Create the hold

The hold stops the driver loading by itself, so a reboot returns to a machine with no
driver loaded. `modprobe` by name still works. It comes before the install, because
installing alone would commit the next boot to loading the driver.

```bash
printf 'blacklist %s\n' clevo_wmi clevo_acpi uniwill_wmi gxtp7380 stk8321 \
  ite_8291 ite_8291_lb ite_8297 ite_829x tuxi_acpi tuxedo_tuxi_fan_control tuxedo_io \
  tuxedo_nb02_nvidia_power_ctrl tuxedo_nb04_kbd_backlight tuxedo_nb04_keyboard \
  tuxedo_nb04_power_profiles tuxedo_nb04_sensors tuxedo_nb04_wmi_ab tuxedo_nb04_wmi_bs \
  tuxedo_nb05_ec tuxedo_nb05_fan_control tuxedo_nb05_kbd_backlight tuxedo_nb05_keyboard \
  tuxedo_nb05_power_profiles tuxedo_nb05_sensors \
  | sudo tee /etc/modprobe.d/clevo-kbd-hold.conf >/dev/null
```

These are the 25 modules in version 4.24.0 that can load by themselves. Step 6 removes
`clevo_wmi`. Keep the others for good: `tuxedo_io` creates a fan-control device, and the
backlight needs none of them. Another version may add modules, so step 4 checks for that
first.

### 2. Install the driver package

This builds the driver as root. `pacman -Si` shows the version on offer. Any version
other than 4.24.0 is untested too.

```bash
pacman -Si tuxedo-drivers-dkms
headers="linux$(uname -r | cut -d. -f1,2 | tr -d .)-headers"
sudo pacman -S --needed "$headers" tuxedo-drivers-dkms
dkms status
```

`dkms status` must say `tuxedo-drivers` is `installed` for your running kernel. If it
does not, stop: the build failed, so no driver will load.

To stop updates replacing the version you tested, add
`IgnorePkg = tuxedo-drivers-dkms` under `[options]` in `/etc/pacman.conf`.

On other distributions the package and its name may differ. Upstream is at
<https://gitlab.com/tuxedocomputers/development/packages/tuxedo-drivers>. The hold still
goes first.

### 3. Rehearse the recovery boot

Do this before the driver has ever loaded. It proves you can reach the menu, and that
the line you add really blocks the driver, before you need either.

Reboot and follow [Recovery](#recovery) step 3, parts 1 to 3. Then run this. `modprobe`
runs only if the kernel received the whole value, with a space before it. Without that
it would be the first load.

```bash
grep -qE '(^| )module_blacklist=clevo_wmi,tuxedo_keyboard,tuxedo_io,tuxedo_nb02_nvidia_power_ctrl( |$)' /proc/cmdline && sudo modprobe clevo_wmi
```

Pass: `modprobe` fails with `Operation not permitted`. `lsmod` may then list
`tuxedo_compatibility_check`, which `modprobe` loads first. Nothing uses it, and it goes
at the next boot.

If it prints nothing, the value did not reach the kernel as written, and nothing was
loaded. Reboot and try again. If `modprobe` succeeds, the line does not block the driver
here. Reboot, which clears it, then use [Remove](#remove).

If no menu appears, your system starts as usual. Try once more, holding `Shift`. If
there is still no menu, make it show by itself, then reboot and repeat this step. The
menu then shows at every boot for `GRUB_TIMEOUT` seconds, so that must be above 0.

```bash
sudo sed -i 's/^GRUB_TIMEOUT_STYLE=hidden/GRUB_TIMEOUT_STYLE=menu/' /etc/default/grub
sudo update-grub
```

If there is still no menu, stop, and do not load the driver: [Recovery](#recovery) step
3 will not work on this machine. Use [Remove](#remove).

Booting an edited entry can blank Grub's saved default, so check it afterwards with
[Recovery](#recovery) step 6.

### 4. First load

Reboot normally, because the rehearsal boot refuses the driver. Run these two checks
before the load.

```bash
lsmod | grep -E 'clevo|tuxedo|tuxi|uniwill|ite_82|stk8321|gxtp7380'
sudo dmesg | grep -E 'Oops|Call Trace|BUG:|WARNING:'
```

`lsmod` must print nothing. If it prints anything, the hold does not cover your machine,
so stop, and use [Remove](#remove). Note anything the log check prints: that did not
come from the driver.

Then load it. The keyboard goes dark, because the driver starts at brightness 0.

```bash
sudo modprobe clevo_wmi
sudo dmesg | grep -iE 'clevo|tuxedo|hook'
ls /sys/class/leds | grep kbd_backlight
sudo dmesg | grep -E 'Oops|Call Trace|BUG:|WARNING:'
```

`ls` must show the three LED devices, and the last command must print nothing new. On
the tested machine the log shows `CLEVO_CMD_GET_SPECS does not exist on this device or
return value has wrong type` three times, then `new hook: TUXEDO Flexicharger Extension`
and `interface initialized`. All of that was harmless there.

Now read the battery settings. This does not write to them. Use your battery's name if
it is not `BAT0`: `ls /sys/class/power_supply/` shows it.

```bash
cat /sys/class/power_supply/BAT0/charge_type /sys/class/power_supply/BAT0/charge_control_start_threshold /sys/class/power_supply/BAT0/charge_control_end_threshold
upower -d | grep charge-threshold-enabled
test -e /var/lib/upower/charging-threshold-status && echo 'status file present: stop' || echo 'status file absent: ok'
```

Copy down the three `charge_*` values. With a limit set in BIOS Setup, `charge_type`
should read `Custom` and the two numbers should match it. That was seen on the tested
machine. With no limit it should read `Standard`, and the numbers may still show old
values, but that has not been seen. If they disagree with BIOS Setup, stop, and do not
lift the hold. If the `charge_*` files do not exist, the driver added no battery controls
here, so skip those checks. The rule above still applies. `upower` must print nothing,
or a line ending in `no`.

| What you see | What it means |
|---|---|
| `modprobe` fails with `No such device` | The driver's compatibility check refused this machine. Stop, and use [Remove](#remove). |
| No `kbd_backlight` device | The firmware did not report a keyboard type the driver handles. Stop, and use [Remove](#remove). |
| New `Oops`, `BUG:`, `Call Trace` or `WARNING:` lines | Stop. Reboot, which clears the driver, and do not lift the hold. |
| Status file present, or `upower` ends in `yes` | A charge limit is active. Do not lift the hold. See [Recovery](#recovery) step 1. |

### 5. Test it under the hold

While the hold is on, run `sudo modprobe clevo_wmi` after each reboot. Until you do, the
login restore service may show as failed, because it has colours to restore and no
device. That is harmless.

**Colours.** Check by eye that each zone shows its colour, in the right place, and that
`brightness` changes the light.

```bash
clevo-kbd brightness 128
clevo-kbd set --zone left --color '#ff0000'
clevo-kbd set --zone centre --color '#00ff00'
clevo-kbd set --zone right --color '#0000ff'
```

**Suspend.** Run `systemctl suspend`, then wake the laptop. It must wake normally, the
keyboard and touchpad must work, and the colours must be as you left them or come back
with `clevo-kbd apply`.

**Cold boot.** Run `systemctl poweroff`, wait 30 s, and power on. Then run this:

```bash
lsmod | grep -E 'clevo|tuxedo'
test ! -e /dev/tuxedo_io && echo 'fan device absent: ok'
```

`lsmod` must print nothing, the second line must print `ok`, and the keyboard and fans
must behave normally. Then run `sudo modprobe clevo_wmi`: the three LED devices must
appear, and the colours must set again.

### 6. Lift the hold

Do this only after step 5 passes. Remove this one line, and no other.

```bash
sudo sed -i '/^blacklist clevo_wmi$/d' /etc/modprobe.d/clevo-kbd-hold.conf
cat /etc/modprobe.d/clevo-kbd-hold.conf
```

The file must still list `tuxedo_io` and `tuxedo_nb02_nvidia_power_ctrl`, and must not
list `clevo_wmi`. From now on the driver loads by itself at every boot.

The next boot is the one the hold was protecting against, so have [Recovery](#recovery)
to hand. Run `systemctl poweroff`, wait 30 s, power on, and do not run `modprobe`.

```bash
lsmod | grep -E '^(clevo_wmi|tuxedo_keyboard) '
test ! -e /dev/tuxedo_io && echo 'fan device absent: ok'
ls /sys/class/leds | grep kbd_backlight
sudo dmesg | grep -E 'Oops|Call Trace|BUG:|WARNING:'
cat /sys/class/power_supply/BAT0/charge_type /sys/class/power_supply/BAT0/charge_control_start_threshold /sys/class/power_supply/BAT0/charge_control_end_threshold
upower -d | grep charge-threshold-enabled
test -e /var/lib/upower/charging-threshold-status && echo 'status file present: stop' || echo 'status file absent: ok'
systemctl --failed
systemctl --user --failed
```

Pass needs all of these:

- The laptop reached the login screen in about the usual time.
- `lsmod` lists both modules, and the fan device line prints `ok`.
- `ls` shows the three LED devices, and the log check prints nothing new.
- The three `charge_*` values match what you copied down.
- `upower` prints nothing or a line ending in `no`, and the status file is absent.
- Neither `--failed` list names `clevo`, `tuxedo` or `backlight`.
- Your colours came back, or come back with `clevo-kbd apply`.

If the laptop will not reach the login screen, use [Recovery](#recovery) step 3. If it
boots but a check fails, put the hold line back, as in Recovery step 3 part 4, and
reboot.

### Recovery

**Keep a copy of these steps somewhere other than this laptop.** Work through them in
order.

1. **Battery first.** Never write to the `charge_*` files to fix anything. If any
   battery setting is not what you chose, open BIOS Setup and set it there. If BIOS
   Setup has no such setting, leave it as it is. If
   `/var/lib/upower/charging-threshold-status` exists, delete it, because UPower
   re-applies a limit at every boot while it is there:

   ```bash
   sudo rm /var/lib/upower/charging-threshold-status
   ```

2. **During the hold.** Just reboot. Hold the power button 10 s if the machine has hung.
   Nothing loads on the next boot.

3. **After the hold is lifted, if boot misbehaves.**
   1. Power off, then on. Hold the power button 10 s if it has hung. Right after the
      firmware logo, tap `Esc`, or hold `Shift`, until the Grub menu appears.
   2. On your usual entry press `e`. Find the line starting `linux`, go to its end,
      type a space, and add:

      `module_blacklist=clevo_wmi,tuxedo_keyboard,tuxedo_io,tuxedo_nb02_nvidia_power_ctrl`

   3. Press `Ctrl+X` or `F10`. This applies to one boot only.
   4. Once up, put the hold line back, then reboot. To take the driver off for good, use
      [Remove](#remove).

      ```bash
      echo 'blacklist clevo_wmi' | sudo tee -a /etc/modprobe.d/clevo-kbd-hold.conf
      ```

4. **If Grub will not help.** Boot the live USB and reach your installed system. On
   Manjaro run `sudo manjaro-chroot -a`, then
   `echo 'blacklist clevo_wmi' >> /etc/modprobe.d/clevo-kbd-hold.conf`, then `exit`, and
   reboot. If the driver still loads after that, repeat this step with
   `pacman -Rns tuxedo-drivers-dkms` in place of the `echo` line.

5. **If the laptop will not power on, or the keyboard, fans or charging misbehave with
   the module gone.** Shut down, unplug AC, hold the power button 30-60 s, and restart.
   Use a USB keyboard if the built-in one is dead. If it persists, BIOS Setup's
   load-defaults option is the last resort. It resets every page, so set your values
   back from your photos before you save. If Windows uses BitLocker, have its recovery
   key to hand first. Do not flash anything.

6. **If Grub starts the wrong entry.** Booting an edited entry can blank Grub's saved
   default when `GRUB_SAVEDEFAULT=true` is set. Compare this with what you noted before
   first load:

   ```bash
   grep '^saved_entry' /boot/grub/grubenv
   ```

   If it differs, set it back, using your own entry id from
   [Before first load](#before-first-load), step 4. From the live USB, run it inside the
   system you reached in step 4, without `sudo`.

   ```bash
   sudo grub-set-default '<your entry id>'
   ```

### Remove

Do [Recovery](#recovery) step 1 first. Any battery setting that was changed stays set
after removal. If your firmware has that setting, BIOS Setup can still reach it.

To remove the driver, run this. Errors saying a module is not loaded are fine.

```bash
sudo modprobe -r clevo_wmi tuxedo_io tuxedo_keyboard tuxedo_compatibility_check
sudo pacman -Rns tuxedo-drivers-dkms
sudo rm /etc/modprobe.d/clevo-kbd-hold.conf
```

If you added it, delete the `IgnorePkg = tuxedo-drivers-dkms` line from
`/etc/pacman.conf`. If any other module from the package was loaded, a reboot clears it.

The keyboard may stay dark afterwards. Unloading turns the LEDs off, and no driver is
left to turn them back on. A full power cycle may bring them back, but that is
unverified.

To remove the app, run this, then delete the clone and `~/.config/clevo-kbd/`.

```bash
sudo systemctl disable "clevo-kbd-resume@$USER.service"
sudo rm /etc/systemd/system/clevo-kbd-resume@.service /etc/udev/rules.d/90-clevo-kbd.rules
sudo systemctl daemon-reload
sudo udevadm control --reload
sudo gpasswd -d "$USER" clevo-kbd
sudo groupdel clevo-kbd
systemctl --user disable clevo-kbd-restore.service
rm ~/.config/systemd/user/clevo-kbd-restore.service
systemctl --user daemon-reload
rm ~/.local/share/applications/clevo-kbd.desktop ~/.local/bin/clevo-kbd
```

## Tests

The tests need PySide6. They run against a private fake device tree and never touch
`/sys`. The window runs on Qt's offscreen platform, so nothing appears on your desktop.
Run them from the clone:

```bash
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -t .
```

## Licence

MIT, see `LICENSE`. Use at your own risk; no support is promised.
