#!/usr/bin/env bash
# Install the out-of-tree it87 driver required for Beelink EQ / ME N150 fan control.
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo ./setup-it87.sh"
  exit 1
fi

echo "Installing build dependencies..."
if command -v apt-get >/dev/null 2>&1; then
  # Ubuntu / Debian
  apt-get update
  apt-get install -y dkms "linux-headers-$(uname -r)" git build-essential lm-sensors
elif command -v pacman >/dev/null 2>&1; then
  # Arch
  pacman -S --needed --noconfirm dkms linux-headers git base-devel lm_sensors
else
  echo "Unsupported distro: install dkms, kernel headers, git, a C toolchain and lm-sensors manually."
  exit 1
fi

WORKDIR="$(mktemp -d)"
trap 'rm -rf "${WORKDIR}"' EXIT

echo "Cloning frankcrawford/it87..."
git clone --depth 1 https://github.com/frankcrawford/it87.git "${WORKDIR}/it87"

echo "Installing via DKMS..."
(cd "${WORKDIR}/it87" && ./dkms-install.sh)

echo "Loading it87 module..."
modprobe -r it87 2>/dev/null || true
modprobe it87 ignore_resource_conflict=1

echo "it87" > /etc/modules-load.d/it87.conf
cat > /etc/modprobe.d/it87.conf <<'EOF'
options it87 ignore_resource_conflict=1
EOF

echo
echo "Done. Verify with: sensors"
sensors | grep -A6 -iE 'it8613|it87|fan' || sensors