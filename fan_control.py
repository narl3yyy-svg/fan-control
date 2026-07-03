#!/usr/bin/env python3
"""Fan control GUI for Linux, with Beelink EQ/ME N150 (IT8613E) support."""

from __future__ import annotations

import glob
import os
import re
import subprocess
import sys
import tkinter as tk
from dataclasses import dataclass, field
from tkinter import messagebox, ttk

BEELINK_MIN_PWM = 20
BEELINK_START_PWM = 30


@dataclass
class FanController:
    label: str
    kind: str  # "pwm" or "cooling"
    path: str
    max_value: int = 255
    enable_path: str | None = None
    rpm_path: str | None = None
    beelink: bool = False

    def read(self) -> int | None:
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                return int(handle.read().strip())
        except (OSError, ValueError):
            return None

    def read_rpm(self) -> int | None:
        if not self.rpm_path or not os.path.exists(self.rpm_path):
            return None
        try:
            with open(self.rpm_path, "r", encoding="utf-8") as handle:
                return int(handle.read().strip())
        except (OSError, ValueError):
            return None

    def set_manual_mode(self, enabled: bool) -> bool:
        if not self.enable_path or not os.path.exists(self.enable_path):
            return True
        try:
            with open(self.enable_path, "w", encoding="utf-8") as handle:
                handle.write("1" if enabled else "2")
            return True
        except OSError:
            return False

    def write_pwm(self, pwm_value: int) -> bool:
        pwm_value = max(0, min(pwm_value, self.max_value))
        if self.beelink and pwm_value == 0:
            current = self.read()
            if current and current > 0:
                try:
                    with open(self.path, "w", encoding="utf-8") as handle:
                        handle.write(str(BEELINK_MIN_PWM))
                except OSError:
                    return False
            try:
                with open(self.path, "w", encoding="utf-8") as handle:
                    handle.write("0")
                return True
            except OSError:
                return False

        if self.beelink:
            current = self.read()
            if current == 0 and pwm_value > 0:
                try:
                    with open(self.path, "w", encoding="utf-8") as handle:
                        handle.write(str(BEELINK_START_PWM))
                except OSError:
                    return False

        try:
            with open(self.path, "w", encoding="utf-8") as handle:
                handle.write(str(pwm_value))
            return True
        except OSError:
            return False

    def write(self, value: int) -> bool:
        if self.kind == "pwm":
            return self.write_pwm(value)
        value = max(0, min(value, self.max_value))
        try:
            with open(self.path, "w", encoding="utf-8") as handle:
                handle.write(str(value))
            return True
        except OSError:
            return False


def _hwmon_name(hwmon_dir: str) -> str:
    name_path = os.path.join(hwmon_dir, "name")
    if os.path.exists(name_path):
        with open(name_path, encoding="utf-8") as handle:
            return handle.read().strip()
    return "hwmon"


def discover_pwm_controllers() -> list[FanController]:
    controllers: list[FanController] = []

    for pwm_path in sorted(glob.glob("/sys/class/hwmon/hwmon*/pwm[0-9]*")):
        base = os.path.basename(pwm_path)
        if not base.startswith("pwm") or "_" in base:
            continue

        hwmon_dir = os.path.dirname(pwm_path)
        chip = _hwmon_name(hwmon_dir)
        pwm_num = re.search(r"pwm(\d+)", base)
        pwm_index = pwm_num.group(1) if pwm_num else "?"

        fan_candidates = glob.glob(os.path.join(hwmon_dir, f"fan{pwm_index}_input"))
        rpm_path = fan_candidates[0] if fan_candidates else None
        enable_path = os.path.join(hwmon_dir, f"{base}_enable")
        if not os.path.exists(enable_path):
            enable_path = None

        beelink = chip.startswith("it8613") or chip.startswith("it86")
        if chip == "it8613" and pwm_index != "2":
            continue

        label = f"{chip} CPU fan (PWM {pwm_index})"
        if rpm_path:
            label = f"{chip} fan{pwm_index}"

        controllers.append(
            FanController(
                label=label,
                kind="pwm",
                path=pwm_path,
                max_value=255,
                enable_path=enable_path,
                rpm_path=rpm_path,
                beelink=beelink,
            )
        )

    if controllers:
        paired = [c for c in controllers if c.rpm_path]
        return paired or controllers

    return []


def discover_acpi_fans() -> list[FanController]:
    controllers: list[FanController] = []
    for device_path in sorted(glob.glob("/sys/class/thermal/cooling_device*")):
        type_path = os.path.join(device_path, "type")
        state_path = os.path.join(device_path, "cur_state")
        max_path = os.path.join(device_path, "max_state")
        if not all(os.path.exists(p) for p in (type_path, state_path, max_path)):
            continue
        with open(type_path, encoding="utf-8") as handle:
            if handle.read().strip() != "Fan":
                continue
        with open(max_path, encoding="utf-8") as handle:
            max_state = int(handle.read().strip())
        index = os.path.basename(device_path).replace("cooling_device", "")
        controllers.append(
            FanController(
                label=f"ACPI Fan {index} (usually not the real fan)",
                kind="cooling",
                path=state_path,
                max_value=max_state,
            )
        )
    return controllers


def discover_controllers() -> list[FanController]:
    pwm = discover_pwm_controllers()
    if pwm:
        return pwm
    return discover_acpi_fans()


def it87_driver_loaded() -> bool:
    try:
        with open("/proc/modules", encoding="utf-8") as handle:
            return any(line.startswith("it87 ") for line in handle)
    except OSError:
        return False


def read_cpu_temp_c() -> str:
    for path in sorted(glob.glob("/sys/class/hwmon/hwmon*/temp*_input")):
        hwmon_dir = os.path.dirname(path)
        if _hwmon_name(hwmon_dir) != "coretemp":
            continue
        label_path = path.replace("_input", "_label")
        if os.path.exists(label_path):
            with open(label_path, encoding="utf-8") as handle:
                label = handle.read().strip().lower()
            if "package" not in label:
                continue
        with open(path, encoding="utf-8") as handle:
            return f"{int(handle.read().strip()) / 1000:.1f} °C"

    try:
        output = subprocess.check_output(["sensors"], text=True, stderr=subprocess.DEVNULL)
        match = re.search(r"Package id \d+:\s+\+?([\d.]+)", output)
        if match:
            return f"{match.group(1)} °C"
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return "N/A"


class FanControlApp:
    def __init__(self, root: tk.Tk, controllers: list[FanController]) -> None:
        self.root = root
        self.controllers = controllers
        self.using_acpi_fallback = controllers and controllers[0].kind == "cooling"
        self.manual_mode = tk.BooleanVar(value=False)
        self.slider_value = tk.IntVar(value=50)
        self.status_text = tk.StringVar(value="Ready")
        self.temp_text = tk.StringVar(value="CPU: …")
        self.rpm_text = tk.StringVar(value="Fan RPM: …")

        root.title("Fan Control — Beelink EQ")
        root.geometry("500x340")
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        frame = ttk.Frame(root, padding=16)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Fan Control", font=("Sans", 16, "bold")).pack(anchor="w")
        ttk.Label(frame, textvariable=self.temp_text, font=("Sans", 12)).pack(anchor="w", pady=(8, 0))
        ttk.Label(frame, textvariable=self.rpm_text, font=("Sans", 12)).pack(anchor="w", pady=(0, 8))

        if self.using_acpi_fallback:
            warn = (
                "IT87 driver not loaded — ACPI fans on Beelink PCs do not control the real CPU fan.\n"
                "Run: sudo ./setup-it87.sh   then restart this app."
            )
            ttk.Label(frame, text=warn, foreground="#a33", wraplength=460).pack(anchor="w", pady=(0, 8))

        mode_row = ttk.Frame(frame)
        mode_row.pack(fill="x", pady=(0, 8))
        ttk.Checkbutton(
            mode_row,
            text="Manual control",
            variable=self.manual_mode,
            command=self.on_mode_change,
        ).pack(side="left")
        ttk.Label(mode_row, text="(off = EC auto)", foreground="#666").pack(side="left", padx=(8, 0))

        ttk.Label(frame, text="Fan speed").pack(anchor="w")
        slider_row = ttk.Frame(frame)
        slider_row.pack(fill="x", pady=(4, 8))

        self.slider = ttk.Scale(
            slider_row,
            from_=0,
            to=100,
            orient="horizontal",
            variable=self.slider_value,
            command=self.on_slider_move,
        )
        self.slider.pack(side="left", fill="x", expand=True)
        self.percent_label = ttk.Label(slider_row, text="50%", width=5)
        self.percent_label.pack(side="left", padx=(8, 0))

        self.fan_list = tk.Listbox(frame, height=4, activestyle="none")
        self.fan_list.pack(fill="both", expand=True, pady=(4, 8))

        ttk.Label(frame, textvariable=self.status_text, foreground="#444", wraplength=460).pack(anchor="w")

        self.update_temperature()
        self.update_fan_status()
        self.set_controls_enabled(False)

    def set_controls_enabled(self, enabled: bool) -> None:
        self.slider.configure(state="normal" if enabled else "disabled")

    def on_mode_change(self) -> None:
        if self.manual_mode.get():
            self.set_controls_enabled(True)
            for controller in self.controllers:
                if controller.kind == "pwm":
                    controller.set_manual_mode(True)
            self.apply_fan_speed(self.slider_value.get())
            self.status_text.set("Manual mode active")
        else:
            self.set_controls_enabled(False)
            for controller in self.controllers:
                if controller.kind == "pwm":
                    controller.set_manual_mode(False)
            self.status_text.set("Auto mode — embedded controller manages fan")

    def on_slider_move(self, _value: str) -> None:
        percent = int(float(_value))
        self.percent_label.configure(text=f"{percent}%")
        if self.manual_mode.get():
            self.apply_fan_speed(percent)

    def apply_fan_speed(self, percent: int) -> None:
        if not self.controllers:
            return

        failed = False
        pwm_controllers = [c for c in self.controllers if c.kind == "pwm"]
        cooling_controllers = [c for c in self.controllers if c.kind == "cooling"]

        for controller in pwm_controllers:
            pwm_value = round(255 * percent / 100)
            if not controller.set_manual_mode(True):
                failed = True
            if not controller.write_pwm(pwm_value):
                failed = True

        if cooling_controllers:
            if all(c.max_value == 1 for c in cooling_controllers):
                active_count = 0 if percent == 0 else max(1, round(percent / 100 * len(cooling_controllers)))
                for index, controller in enumerate(cooling_controllers):
                    if not controller.write(1 if index < active_count else 0):
                        failed = True
            else:
                for controller in cooling_controllers:
                    if not controller.write(round(percent / 100 * controller.max_value)):
                        failed = True

        if failed:
            self.status_text.set("Write failed — run with: sudo ./run.sh")
        elif self.using_acpi_fallback:
            self.status_text.set("ACPI write OK, but real fan likely unchanged — install it87 driver")
        else:
            self.status_text.set(f"PWM set to {percent}%")
        self.update_fan_status()

    def update_fan_status(self) -> None:
        self.fan_list.delete(0, "end")
        rpm_values: list[int] = []
        for controller in self.controllers:
            current = controller.read()
            rpm = controller.read_rpm()
            if rpm is not None:
                rpm_values.append(rpm)

            if current is None:
                state = "unknown"
            elif controller.kind == "pwm":
                state = f"PWM {current}/255 ({round(current / 255 * 100)}%)"
            elif controller.max_value == 1:
                state = "on" if current else "off"
            else:
                state = f"{round(current / controller.max_value * 100)}%"

            if rpm is not None:
                state += f", {rpm} RPM"

            self.fan_list.insert("end", f"{controller.label}: {state}")

        if rpm_values:
            self.rpm_text.set(f"Fan RPM: {max(rpm_values)}")
        else:
            self.rpm_text.set("Fan RPM: (install it87 driver to read)")

    def update_temperature(self) -> None:
        self.temp_text.set(f"CPU temperature: {read_cpu_temp_c()}")
        self.update_fan_status()
        self.root.after(2000, self.update_temperature)

    def on_close(self) -> None:
        for controller in self.controllers:
            if controller.kind == "pwm":
                controller.set_manual_mode(False)
        self.root.destroy()


def main() -> int:
    controllers = discover_controllers()
    if not controllers:
        print("No fan controllers found.")
        print("On Beelink EQ N150, run: sudo ./setup-it87.sh")
        return 1

    root = tk.Tk()
    if os.geteuid() != 0:
        messagebox.showwarning(
            "Root required",
            "Fan control needs root.\n\nRun:\n  sudo ./run.sh\n\n"
            "If the fan still does nothing, first run:\n  sudo ./setup-it87.sh",
        )
    elif not it87_driver_loaded() and controllers[0].kind == "cooling":
        messagebox.showwarning(
            "IT87 driver required",
            "Your Beelink CPU fan is controlled by the IT8613E chip,\n"
            "not ACPI. Install the driver first:\n\n"
            "  cd ~/fan-control\n"
            "  sudo ./setup-it87.sh\n\n"
            "Then restart this app.",
        )

    FanControlApp(root, controllers)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())