#!/usr/bin/env bash
# Launch the fan control GUI on Ubuntu (also works on other Debian-based distros).
#
# Usage:
#   ./run.sh              install missing packages if needed, then start the GUI
#   ./run.sh --setup      also build/install the it87 driver (Beelink EQ / ME N150)
#   ./run.sh --no-install skip the apt dependency check
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

DO_SETUP=0
DO_INSTALL=1
for arg in "$@"; do
  case "$arg" in
    --setup) DO_SETUP=1 ;;
    --no-install) DO_INSTALL=0 ;;
    -h|--help)
      sed -n '2,7p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "Unknown option: $arg (see ./run.sh --help)" >&2
      exit 1
      ;;
  esac
done

# --- Dependencies ------------------------------------------------------------
# python3-tk provides tkinter, lm-sensors provides the `sensors` command.
if [[ "$DO_INSTALL" -eq 1 ]] && command -v apt-get >/dev/null 2>&1; then
  missing=()
  command -v python3 >/dev/null 2>&1 || missing+=(python3)
  python3 -c 'import tkinter' >/dev/null 2>&1 || missing+=(python3-tk)
  command -v sensors >/dev/null 2>&1 || missing+=(lm-sensors)
  if [[ ${#missing[@]} -gt 0 ]]; then
    echo "Installing missing packages: ${missing[*]}"
    sudo apt-get update
    sudo apt-get install -y "${missing[@]}"
  fi
fi

# --- it87 driver (Beelink EQ / ME N150) --------------------------------------
if [[ "$DO_SETUP" -eq 1 ]]; then
  sudo ./setup-it87.sh
elif ! grep -q '^it87 ' /proc/modules 2>/dev/null \
  && ! ls /sys/class/hwmon/hwmon*/pwm* >/dev/null 2>&1; then
  echo "Tip: no PWM fans found. Beelink EQ needs the it87 driver. Run: ./run.sh --setup"
fi

# --- Launch ------------------------------------------------------------------
# Writing to /sys/class/hwmon needs root. The GUI runs as root, so pass the
# desktop session's display variables through sudo. On Ubuntu's default
# Wayland session, Tk talks to XWayland, which also needs root allowed via xhost.
if [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
  echo "No graphical display found. Run this from a desktop session." >&2
  exit 1
fi

export XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"

if [[ "$EUID" -ne 0 ]] && command -v xhost >/dev/null 2>&1; then
  xhost +SI:localuser:root >/dev/null 2>&1 || true
  trap 'xhost -SI:localuser:root >/dev/null 2>&1 || true' EXIT
fi

if [[ "$EUID" -eq 0 ]]; then
  python3 fan_control.py
else
  sudo --preserve-env=DISPLAY,XAUTHORITY,WAYLAND_DISPLAY python3 fan_control.py
fi
