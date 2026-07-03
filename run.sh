#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if ! grep -q '^it87 ' /proc/modules 2>/dev/null; then
  if ! ls /sys/class/hwmon/hwmon*/pwm* >/dev/null 2>&1; then
    echo "Tip: Beelink EQ needs the it87 driver. Run: sudo ./setup-it87.sh"
  fi
fi

exec sudo python3 fan_control.py