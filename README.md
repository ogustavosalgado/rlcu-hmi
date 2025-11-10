# RLCU Ground-Control HMI

Interactive Kivy/KivyMD application to monitor and control Range Launch Control Units (RLCUs). Pads announce over UDP, stream telemetry via TCP, and accept command bitmasks. The UI visualizes each pad, provides detailed drill-down, and layers an optional (partial) serial bridge to a local controller box.

---

## Key Features

| Area | Summary |
|------|---------|
| **Pad Discovery** | Pads broadcast an authenticated UDP frame; the app establishes a TCP session per pad for telemetry and commands. |
| **Telemetry UI** | Real-time continuity, arm, RSSI, voltage, and freshness indicators on overview cards and detail screens. |
| **Command Bitmask** | Command channel exposes ready-to-fire, launch (momentary pulse), LED, and buzzer flags with state tracking. |
| **Launch Workflow** | Detail screen enforces arm confirmation, executes launch pulse, and automatically resets local readiness. |
| **Socket Simulator** | Included simulator (`socket_sim/socket_sim.py`) mimics pads for offline testing. |
| **Serial Bridge (Partial)** | Serial dialog connects to an ESP32 control box. |

---

## Architecture Overview

```
UI (Kivy/KivyMD)
 ├─ overview_screen.py       # Grid of pad cards + global controls
 ├─ pad_card.py              # Lightweight pad summary widgets
 └─ pad_detail_screen.py     # Detailed telemetry + launch actions

Networking
 ├─ rlcu_socket.py           # UDP discovery + TCP telemetry + command bitmask
 └─ socket_sim/socket_sim.py # Local pad simulator (optional)

Data Model
 └─ globals.py               # `Pad` dataclass-like container + shared locks

Serial (partial)
 ├─ rlcu_serial.py           # Bitmask-based UART shim (controller box)
 ├─ serial_dialog.py         # UI dialog for COM selection/connection
 └─ ESP32 firmware (Controller/main/main.c)
```

---

## Getting Started

1. **Create a virtual environment (optional but recommended)**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate        # Linux/macOS
   .venv\Scripts\activate           # Windows
   ```
2. **Install dependencies**: Python ≥ 3.10, Kivy 2.3+, KivyMD 2.0, `pyserial`.
   - NOTE: KivyMD 2.0 is not yet available on pip repos. Install it with:
     ```bash
     pip install https://github.com/kivymd/KivyMD/archive/master.zip
     ```
3. **Run simulator (optional)**:
   ```bash
   python socket_sim/socket_sim.py
   ```
4. **Launch HMI**:
   ```bash
   python main.py
   ```
5. **Serial (optional)**: Connect ESP32, use the Serial Settings dialog to open the port.

---

## Development Notes

- Shared pad state is guarded with `pad_data_lock`; UI code acquires it before reads/writes.
- TCP workers resynchronize the stored command mask immediately after reconnect.
- `pad_detail_screen` guards command sends to avoid blocking when no pad link exists.
- Logs (`INFO`, `DEBUG`) are printed to stdout for socket-level activity; adjust or route as needed.

---

## Testing Checklist

- Launch the simulator and verify pads appear with changing telemetry.
- Toggle HMI arm checkbox → command log should show ready-to-fire bit and revert after launch.
- Buzzer/LED buttons should toggle and persist across reconnections.
- Socket dialog start/stop should reflect in the header.
- Serial dialog connects (if hardware present) but does not yet drive UI changes.

---

## License

This project is released under the [GNU General Public License v3.0](LICENSE).  
You are free to use, modify, and distribute the software under the terms of the GPLv3.

