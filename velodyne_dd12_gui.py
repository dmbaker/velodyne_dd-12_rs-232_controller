import tkinter as tk
from tkinter import ttk, messagebox
import serial
import serial.tools.list_ports

# -----------------------------
# Velodyne DD-12 RS-232 settings
# -----------------------------
BAUDRATE = 9600
BYTESIZE = serial.SEVENBITS
PARITY = serial.PARITY_NONE
STOPBITS = serial.STOPBITS_ONE
TIMEOUT = 1

# Preset mapping (DD-12 has 6 presets)
# 1: Action/Adventure
# 2: Movies
# 3: Pop/Rock
# 4: Jazz/Classical
# 5: Custom
# 6: EQ Defeat
PRESETS = [
    ("Action / Adventure", 1),
    ("Movies", 2),
    ("Pop / Rock", 3),
    ("Jazz / Classical", 4),
    ("Custom", 5),
    ("EQ Defeat", 6),
]

class VelodyneApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Velodyne DD-12 Controller")
        self.geometry("620x520")
        self.resizable(False, False)

        self.serial_port = None
        self.current_volume = 30  # default if query fails

        self.create_widgets()
        self.refresh_ports()

    # -----------------------------
    # UI
    # -----------------------------
    def create_widgets(self):
        # Frame: Serial connection
        conn_frame = ttk.LabelFrame(self, text="Serial Connection")
        conn_frame.pack(fill="x", padx=10, pady=10)

        ttk.Label(conn_frame, text="Port:").grid(row=0, column=0, padx=5, pady=5, sticky="w")

        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(conn_frame, textvariable=self.port_var, width=30, state="readonly")
        self.port_combo.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        self.refresh_button = ttk.Button(conn_frame, text="Refresh", command=self.refresh_ports)
        self.refresh_button.grid(row=0, column=2, padx=5, pady=5)

        self.connect_button = ttk.Button(conn_frame, text="Connect", command=self.toggle_connection)
        self.connect_button.grid(row=0, column=3, padx=5, pady=5)

        # Status label
        self.status_var = tk.StringVar(value="Disconnected")
        self.status_label = ttk.Label(conn_frame, textvariable=self.status_var, foreground="red")
        self.status_label.grid(row=1, column=0, columnspan=4, padx=5, pady=5, sticky="w")

        # Frame: Volume
        vol_frame = ttk.LabelFrame(self, text="Volume")
        vol_frame.pack(fill="x", padx=10, pady=10)

        # Absolute volume slider (0–99)
        ttk.Label(vol_frame, text="Absolute Volume (0–99):").grid(row=0, column=0, padx=5, pady=5, sticky="w")

        self.volume_var = tk.IntVar(value=self.current_volume)
        self.volume_slider = ttk.Scale(
            vol_frame,
            from_=0,
            to=99,
            orient="horizontal",
            variable=self.volume_var,
            command=self.on_volume_slider_release  # called continuously; we'll debounce
        )
        self.volume_slider.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        vol_frame.columnconfigure(1, weight=1)

        self.volume_label = ttk.Label(vol_frame, text=str(self.current_volume))
        self.volume_label.grid(row=0, column=2, padx=5, pady=5)

        # Relative volume buttons
        self.vol_down_button = ttk.Button(vol_frame, text="Vol -", width=6,
                                          command=lambda: self.send_relative_volume(-1))
        self.vol_down_button.grid(row=1, column=0, padx=5, pady=5, sticky="w")

        self.vol_up_button = ttk.Button(vol_frame, text="Vol +", width=6,
                                        command=lambda: self.send_relative_volume(1))
        self.vol_up_button.grid(row=1, column=1, padx=5, pady=5, sticky="w")

        self.sync_vol_button = ttk.Button(vol_frame, text="Sync from Sub", command=self.query_and_sync_volume)
        self.sync_vol_button.grid(row=1, column=2, padx=5, pady=5, sticky="e")

        # Frame: Presets
        preset_frame = ttk.LabelFrame(self, text="Presets")
        preset_frame.pack(fill="x", padx=10, pady=10)

        row = 0
        col = 0
        for label, num in PRESETS:
            btn = ttk.Button(
                preset_frame,
                text=f"{label} (P{num})",
                command=lambda n=num, l=label: self.set_preset(n, l)
            )
            btn.grid(row=row, column=col, padx=5, pady=5, sticky="ew")
            col += 1
            if col >= 3:
                col = 0
                row += 1

        # Frame: Common controls
        ctrl_frame = ttk.LabelFrame(self, text="Controls")
        ctrl_frame.pack(fill="x", padx=10, pady=10)

        self.mute_button = ttk.Button(ctrl_frame, text="Mute", command=self.toggle_mute)
        self.mute_button.grid(row=0, column=0, padx=5, pady=5)

        self.night_on_button = ttk.Button(ctrl_frame, text="Night On",
                                          command=lambda: self.send_simple_state("NM", 1, "Night Mode ON"))
        self.night_on_button.grid(row=0, column=1, padx=5, pady=5)

        self.night_off_button = ttk.Button(ctrl_frame, text="Night Off",
                                           command=lambda: self.send_simple_state("NM", 0, "Night Mode OFF"))
        self.night_off_button.grid(row=0, column=2, padx=5, pady=5)

        self.light_on_button = ttk.Button(ctrl_frame, text="Logo Light On",
                                          command=lambda: self.send_simple_state("LT", 1, "Logo Light ON"))
        self.light_on_button.grid(row=1, column=0, padx=5, pady=5)

        self.light_off_button = ttk.Button(ctrl_frame, text="Logo Light Off",
                                           command=lambda: self.send_simple_state("LT", 0, "Logo Light OFF"))
        self.light_off_button.grid(row=1, column=1, padx=5, pady=5)

        self.power_on_button = ttk.Button(ctrl_frame, text="Power On",
                                          command=lambda: self.send_simple_state("JU", 1, "Power ON"))
        self.power_on_button.grid(row=2, column=0, padx=5, pady=5)

        self.power_off_button = ttk.Button(ctrl_frame, text="Power Off",
                                           command=lambda: self.send_simple_state("JU", 0, "Power OFF"))
        self.power_off_button.grid(row=2, column=1, padx=5, pady=5)

        # Frame: Custom command
        custom_frame = ttk.LabelFrame(self, text="Custom Command")
        custom_frame.pack(fill="x", padx=10, pady=10)

        ttk.Label(custom_frame, text="Core command (without # or $):").grid(row=0, column=0, padx=5, pady=5, sticky="w")

        self.custom_var = tk.StringVar()
        self.custom_entry = ttk.Entry(custom_frame, textvariable=self.custom_var, width=20)
        self.custom_entry.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        self.custom_button = ttk.Button(custom_frame, text="Send", command=self.send_custom_command)
        self.custom_button.grid(row=0, column=2, padx=5, pady=5)

        # Log output
        log_frame = ttk.LabelFrame(self, text="Log")
        log_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.log_text = tk.Text(log_frame, height=10, state="disabled")
        self.log_text.pack(fill="both", expand=True, padx=5, pady=5)

    # -----------------------------
    # Serial handling
    # -----------------------------
    def refresh_ports(self):
        ports = serial.tools.list_ports.comports()
        port_names = [p.device for p in ports]
        self.port_combo["values"] = port_names
        if port_names and not self.port_var.get():
            self.port_var.set(port_names[0])

    def toggle_connection(self):
        if self.serial_port and self.serial_port.is_open:
            self.disconnect()
        else:
            self.connect()

    def connect(self):
        port_name = self.port_var.get()
        if not port_name:
            messagebox.showerror("Error", "No serial port selected.")
            return

        try:
            self.serial_port = serial.Serial(
                port=port_name,
                baudrate=BAUDRATE,
                bytesize=BYTESIZE,
                parity=PARITY,
                stopbits=STOPBITS,
                timeout=TIMEOUT
            )
            self.status_var.set(f"Connected to {port_name}")
            self.status_label.configure(foreground="green")
            self.connect_button.configure(text="Disconnect")
            self.log(f"Connected to {port_name}")

            # Try to sync volume from sub
            self.query_and_sync_volume()
        except Exception as e:
            self.serial_port = None
            self.status_var.set("Connection failed")
            self.status_label.configure(foreground="red")
            messagebox.showerror("Connection Error", str(e))
            self.log(f"Connection error: {e}")

    def disconnect(self):
        if self.serial_port:
            try:
                self.serial_port.close()
            except Exception:
                pass
        self.serial_port = None
        self.status_var.set("Disconnected")
        self.status_label.configure(foreground="red")
        self.connect_button.configure(text="Connect")
        self.log("Disconnected")

    # -----------------------------
    # Low-level send / receive
    # -----------------------------
    def send_raw(self, core_cmd):
        """
        core_cmd: string WITHOUT # or $
        """
        if not self.serial_port or not self.serial_port.is_open:
            messagebox.showwarning("Not connected", "Please connect to a serial port first.")
            return False

        msg = f"#{core_cmd}$"
        try:
            self.serial_port.write(msg.encode("ascii"))
            self.log(f"Sent: {msg}")
            return True
        except Exception as e:
            self.log(f"Error sending {msg}: {e}")
            messagebox.showerror("Send Error", str(e))
            return False

    def send_and_readline(self, core_cmd):
        """
        Send a command and read one line/response (if any).
        """
        if not self.send_raw(core_cmd):
            return None
        try:
            sp = self.serial_port
            if sp is None or not getattr(sp, "is_open", False):
                self.log("No open serial port to read from")
                return None

            resp = sp.readline().decode("ascii", errors="ignore").strip()
            if resp:
                self.log(f"Received: {resp}")
            return resp
        except Exception as e:
            self.log(f"Error reading response: {e}")
            return None

    # -----------------------------
    # Volume handling
    # -----------------------------
    def on_volume_slider_release(self, _event=None):
        """
        Called whenever the slider moves; we debounce by only sending
        when connected and value changed meaningfully.
        """
        new_vol = int(self.volume_var.get())
        if new_vol == self.current_volume:
            self.volume_label.config(text=str(new_vol))
            return

        self.set_absolute_volume(new_vol)

    def set_absolute_volume(self, value):
        """
        Absolute volume: #VOnn$
        """
        value = max(0, min(99, int(value)))
        core_cmd = f"VO{value:02d}"
        if self.send_raw(core_cmd):
            self.current_volume = value
            self.volume_var.set(value)
            self.volume_label.config(text=str(value))
            self.log(f"Set volume to {value}")

    def send_relative_volume(self, direction):
        """
        Relative volume: #VO+$ or #VO-$
        direction: +1 or -1
        """
        if direction > 0:
            core_cmd = "VO+"
        else:
            core_cmd = "VO-"
        if self.send_raw(core_cmd):
            # Optimistically adjust local state by 1
            new_vol = max(0, min(99, self.current_volume + direction))
            self.current_volume = new_vol
            self.volume_var.set(new_vol)
            self.volume_label.config(text=str(new_vol))
            self.log(f"Relative volume {'up' if direction > 0 else 'down'} -> {new_vol}")

    def query_and_sync_volume(self):
        """
        Query volume: #VO?$
        Response is typically something like #VOxx$
        """
        resp = self.send_and_readline("VO?")
        if not resp:
            self.log("No volume response; keeping local volume.")
            self.volume_var.set(self.current_volume)
            self.volume_label.config(text=str(self.current_volume))
            return

        # Try to extract two digits from response
        import re
        m = re.search(r"VO(\d{2})", resp)
        if m:
            vol = int(m.group(1))
            self.current_volume = vol
            self.volume_var.set(vol)
            self.volume_label.config(text=str(vol))
            self.log(f"Synchronized volume from sub: {vol}")
        else:
            self.log("Could not parse volume from response; keeping local value.")
            self.volume_var.set(self.current_volume)
            self.volume_label.config(text=str(self.current_volume))

    # -----------------------------
    # Presets
    # -----------------------------
    def set_preset(self, preset_num, label):
        """
        Preset select: #PSn$
        """
        core_cmd = f"PS{preset_num}"
        if self.send_raw(core_cmd):
            self.log(f"Preset {preset_num} ({label}) selected")

    # -----------------------------
    # Simple state controls (Night, Light, Power, etc.)
    # -----------------------------
    def send_simple_state(self, prefix, state, description):
        """
        Generic state command: e.g. #NM1$, #LT0$, #JU1$
        """
        core_cmd = f"{prefix}{state}"
        if self.send_raw(core_cmd):
            self.log(description)

    def toggle_mute(self):
        """
        Simple mute toggle using explicit states:
        We'll just send MU1 (mute) if not muted, MU0 (unmute) if muted.
        Since we don't track state from the sub, we just flip a local flag.
        """
        if not hasattr(self, "_muted"):
            self._muted = False

        new_state = 0 if self._muted else 1
        desc = "Mute OFF" if self._muted else "Mute ON"
        if self.send_simple_state("MU", new_state, desc):
            self._muted = not self._muted

    # -----------------------------
    # Custom command
    # -----------------------------
    def send_custom_command(self):
        core_cmd = self.custom_var.get().strip().upper()
        if not core_cmd:
            messagebox.showwarning("No command", "Enter a core command (e.g., VO25, VO+, PS2).")
            return
        self.send_raw(core_cmd)

    # -----------------------------
    # Logging
    # -----------------------------
    def log(self, text):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")


if __name__ == "__main__":
    app = VelodyneApp()
    app.mainloop()
