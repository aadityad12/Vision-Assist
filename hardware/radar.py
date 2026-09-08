import math
import re
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    serial = None


APP_TITLE = "PSoC Radar Display"
DEFAULT_BAUD = 115200
MAX_DISTANCE_CM = 175

# Accepts lines like:
# Distance: 42 cm
# Distance = 0.42 m
# Strongest target at bin: 7 | Magnitude: 12.34
DIST_CM_RE = re.compile(r"distance\s*[:=]\s*([0-9.]+)\s*cm", re.I)
DIST_M_RE = re.compile(r"distance\s*[:=]\s*([0-9.]+)\s*m", re.I)
BIN_RE = re.compile(r"bin\s*[:=]\s*(\d+).*?magnitude\s*[:=]\s*([0-9.]+)", re.I)
TARGET_RE = re.compile(r"TARGET,([0-9.]+),(\d+),([0-9.]+)", re.I)
NO_TARGET_RE = re.compile(r"NO_TARGET", re.I)

# Temporary demo conversion if firmware only prints bins.
# Replace BIN_SIZE_CM after calibrating your firmware/radar settings.
BIN_SIZE_CM = 2.73
MIN_MAGNITUDE = 1.0


class RadarDisplay(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("980x620")
        self.configure(bg="#001a00")

        self.serial_port = None
        self.reader_thread = None
        self.running = False

        self.distance_cm = None
        self.magnitude = 0.0
        self.bin_index = None
        self.angle_deg = 90  # FMCW distance-only mode has no real angle yet; use center beam.
        self.last_line = "Waiting for radar data..."

        self._build_ui()
        self._draw_radar()
        self.after(60, self._animation_loop)

    def _build_ui(self):
        top = tk.Frame(self, bg="#001a00")
        top.pack(fill=tk.X, padx=10, pady=8)

        tk.Label(top, text="Port", fg="#00ff00", bg="#001a00", font=("Menlo", 12, "bold")).pack(side=tk.LEFT)
        self.port_var = tk.StringVar()
        self.port_box = ttk.Combobox(top, textvariable=self.port_var, width=32, values=self._list_ports())
        self.port_box.pack(side=tk.LEFT, padx=8)

        tk.Button(top, text="Refresh", command=self._refresh_ports).pack(side=tk.LEFT, padx=4)
        self.connect_button = tk.Button(top, text="Connect", command=self._toggle_connection)
        self.connect_button.pack(side=tk.LEFT, padx=4)

        tk.Label(top, text="Baud", fg="#00ff00", bg="#001a00", font=("Menlo", 12, "bold")).pack(side=tk.LEFT, padx=(20, 4))
        self.baud_var = tk.StringVar(value=str(DEFAULT_BAUD))
        tk.Entry(top, textvariable=self.baud_var, width=8).pack(side=tk.LEFT)

        self.canvas = tk.Canvas(self, width=960, height=520, bg="#001a00", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        bottom = tk.Frame(self, bg="#001a00")
        bottom.pack(fill=tk.X, padx=10, pady=(0, 10))
        self.status_var = tk.StringVar(value="Not connected")
        tk.Label(bottom, textvariable=self.status_var, fg="#00ff00", bg="#001a00", font=("Menlo", 11)).pack(anchor="w")

    def _list_ports(self):
        if serial is None:
            return []
        ports = [p.device for p in serial.tools.list_ports.comports()]
        # Prefer KitProg-style modem ports on macOS if present.
        ports.sort(key=lambda p: ("usbmodem" not in p.lower(), p))
        return ports

    def _refresh_ports(self):
        ports = self._list_ports()
        self.port_box["values"] = ports
        if ports and not self.port_var.get():
            self.port_var.set(ports[0])

    def _toggle_connection(self):
        if self.running:
            self._disconnect()
        else:
            self._connect()

    def _connect(self):
        if serial is None:
            messagebox.showerror("Missing dependency", "Install pyserial first:\n\npython3 -m pip install pyserial")
            return

        port = self.port_var.get().strip()
        if not port:
            messagebox.showwarning("No port", "Select the radar serial port first.")
            return

        try:
            baud = int(self.baud_var.get())
            self.serial_port = serial.Serial(port, baudrate=baud, timeout=0.1)
        except Exception as exc:
            messagebox.showerror("Connection failed", str(exc))
            return

        self.running = True
        self.connect_button.config(text="Disconnect")
        self.status_var.set(f"Connected to {port}")
        self.reader_thread = threading.Thread(target=self._read_serial_loop, daemon=True)
        self.reader_thread.start()

    def _disconnect(self):
        self.running = False
        if self.serial_port:
            try:
                self.serial_port.close()
            except Exception:
                pass
        self.serial_port = None
        self.connect_button.config(text="Connect")
        self.status_var.set("Disconnected")

    def _read_serial_loop(self):
        while self.running and self.serial_port:
            try:
                raw = self.serial_port.readline()
                if not raw:
                    continue
                line = raw.decode(errors="ignore").strip()
                if line:
                    self._parse_line(line)
            except Exception as exc:
                self.last_line = f"Serial error: {exc}"
                self.running = False
                break

    def _parse_line(self, line):
        self.last_line = line

        m = TARGET_RE.search(line)
        if m:
            distance_m = float(m.group(1))
            self.distance_cm = distance_m * 100.0
            self.bin_index = int(m.group(2))
            self.magnitude = float(m.group(3))
            return

        m = NO_TARGET_RE.search(line)
        if m:
            self.distance_cm = None
            self.bin_index = None
            self.magnitude = 0.0
            return

        m = DIST_CM_RE.search(line)
        if m:
            self.distance_cm = float(m.group(1))
            self.bin_index = None
            return

        m = DIST_M_RE.search(line)
        if m:
            self.distance_cm = float(m.group(1)) * 100.0
            self.bin_index = None
            return

        m = BIN_RE.search(line)
        if m:
            self.bin_index = int(m.group(1))
            self.magnitude = float(m.group(2))
            if self.magnitude >= MIN_MAGNITUDE:
                self.distance_cm = self.bin_index * BIN_SIZE_CM
            return

    def _animation_loop(self):
        self._draw_radar()
        self.after(60, self._animation_loop)

    def _draw_radar(self):
        c = self.canvas
        c.delete("all")

        w = max(c.winfo_width(), 960)
        h = max(c.winfo_height(), 520)
        cx = w // 2
        cy = h - 65
        radius = min(w // 2 - 70, h - 100)

        green = "#00ff00"
        dim_green = "#007a00"
        red = "#ff2020"

        # Radar arcs.
        for frac in (0.25, 0.5, 0.75, 1.0):
            r = radius * frac
            c.create_arc(cx - r, cy - r, cx + r, cy + r, start=0, extent=180, outline=green, width=2)

        # Base line.
        c.create_line(cx - radius, cy, cx + radius, cy, fill=green, width=2)

        # Angle rays.
        for deg in range(0, 181, 30):
            rad = math.radians(deg)
            x = cx + radius * math.cos(rad)
            y = cy - radius * math.sin(rad)
            c.create_line(cx, cy, x, y, fill=dim_green, width=1)

        # Title and readouts.
        c.create_text(cx, 45, text="Radar Display", fill=green, font=("Menlo", 22, "bold"))

        if self.distance_cm is None:
            distance_text = "Distance: -- cm"
        else:
            distance_text = f"Distance: {self.distance_cm:.1f} cm"

        c.create_text(25, 45, text="Angle: center", anchor="w", fill=green, font=("Menlo", 18, "bold"))
        c.create_text(25, 78, text=distance_text, anchor="w", fill=green, font=("Menlo", 18, "bold"))

        if self.bin_index is not None:
            c.create_text(25, 112, text=f"Bin: {self.bin_index}  Mag: {self.magnitude:.2f}", anchor="w", fill=green, font=("Menlo", 14, "bold"))

        # Range labels.
        for label_cm in (50,100,150):
            r = radius * (label_cm / MAX_DISTANCE_CM)
            if r <= radius:
                c.create_text(cx + r + 8, cy - 10, text=f"{label_cm} cm", anchor="w", fill=green, font=("Menlo", 14, "bold"))

        # Sweep beam.
        t = time.time()
        sweep_deg = 20 + 140 * ((math.sin(t * 1.8) + 1) / 2)
        for offset in range(-8, 9):
            deg = sweep_deg + offset * 0.9
            rad = math.radians(deg)
            x = cx + radius * math.cos(rad)
            y = cy - radius * math.sin(rad)
            c.create_line(cx, cy, x, y, fill=green, width=max(1, 5 - abs(offset) // 2))

        # Target point. For distance-only radar, draw it on center line.
        if self.distance_cm is not None:
            clipped = max(0, min(self.distance_cm, MAX_DISTANCE_CM))
            r = radius * (clipped / MAX_DISTANCE_CM)
            rad = math.radians(self.angle_deg)
            x = cx + r * math.cos(rad)
            y = cy - r * math.sin(rad)
            c.create_oval(x - 8, y - 8, x + 8, y + 8, fill=red, outline=red)
            c.create_text(x + 14, y - 14, text=f"{self.distance_cm:.1f} cm", anchor="w", fill=red, font=("Menlo", 13, "bold"))

        # Raw serial line.
        c.create_text(25, h - 28, text=self.last_line[:120], anchor="w", fill=green, font=("Menlo", 11))


if __name__ == "__main__":
    app = RadarDisplay()
    app.mainloop()
