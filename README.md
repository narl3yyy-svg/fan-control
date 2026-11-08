# Fan Control

A small Tkinter GUI for controlling fan speed on Linux through `/sys/class/hwmon`, with built-in support for the **Beelink EQ / ME N150** mini PCs (ITE IT8613E chip).

It shows the current CPU temperature and fan RPM, and lets you set the fan speed with a slider. Closing the app hands fan control back to the firmware (automatic mode).

## Requirements

- Linux with a desktop session (X11 or Wayland)
- Python 3 with Tkinter
- `lm-sensors`
- Root access (writing fan PWM values requires `sudo`)
- For Beelink EQ / ME N150: the out-of-tree [`it87`](https://github.com/frankcrawford/it87) driver

## Quick start (Ubuntu)

```bash
git clone https://github.com/narl3yyy-svg/fan-control.git
cd fan-control
chmod +x run.sh setup-it87.sh
./run.sh --setup   # first run on a Beelink: installs packages and the it87 driver
./run.sh           # every run after that
```

`run.sh` will:

1. Install any missing packages with apt (`python3`, `python3-tk`, `lm-sensors`).
2. With `--setup`, build and install the `it87` driver through DKMS (via `setup-it87.sh`).
3. Start the GUI as root, passing your display through so it opens on your desktop, including on Ubuntu's default Wayland session.

| Option | What it does |
| --- | --- |
| `--setup` | Also install the `it87` driver (needed for Beelink EQ / ME N150) |
| `--no-install` | Skip the apt package check |
| `--help` | Show usage |

## Installing the it87 driver manually

```bash
sudo ./setup-it87.sh
```

This installs the build tools (`dkms`, kernel headers, `build-essential`, `git`), builds the driver from [frankcrawford/it87](https://github.com/frankcrawford/it87), loads it with `ignore_resource_conflict=1`, and sets it to load on every boot. Check it worked with:

```bash
sensors
```

You should see an `it8613` section with a fan reading.

> **Secure Boot:** if Secure Boot is on, Ubuntu will ask you to set a password during the DKMS install and enroll the signing key (MOK) on the next reboot. If you skip that, the module won't load. Either enroll the key or turn Secure Boot off.

`setup-it87.sh` also works on Arch (it uses `pacman` there).

## Troubleshooting

- **"No fan controllers found" or "IT87 driver not loaded"**: the driver isn't loaded, so only ACPI fans (which don't drive the real CPU fan on Beelink PCs) are visible. Run `./run.sh --setup`, then check `lsmod | grep it87` and `sensors`.
- **"Write failed"**: the app wasn't started as root. Start it with `./run.sh`.
- **The window doesn't open / "couldn't connect to display"**: run `./run.sh` from a terminal inside your desktop session, not over SSH. On Wayland, make sure `xhost` is installed (`sudo apt install x11-xserver-utils`).
- **Driver stops working after a kernel update**: DKMS should rebuild it automatically. If not, run `sudo ./setup-it87.sh` again.

## Files

| File | Purpose |
| --- | --- |
| `fan_control.py` | The GUI |
| `run.sh` | Ubuntu launcher: dependencies, optional driver setup, starts the GUI as root |
| `setup-it87.sh` | Builds and installs the `it87` driver (Ubuntu/Debian and Arch) |
