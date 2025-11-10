"""
# This module handles the serial communication with the RLCU control remote box.
Remote box consists of a key switch for local arming, and a toggle switch for launching, as well as status LEDs for connection, arming, local arming and continuity (4 LEDs total).

"""

import serial
import serial.tools.list_ports
import threading

TX_ARM_HMI = 0b00000001
TX_ARM_PAD = 0b00000010
TX_CONTINUITY = 0b00000100

RX_ARM_HMI = 0b00000001
RX_LAUNCH = 0b00000010


class RLCUSerial:
    def __init__(self):
        self._serial_obj = None
        self.connected = False

        self._listener_thread = None
        self._stop_event = threading.Event()
        self._event_callback = None

        self._lock = threading.Lock()
        self._tx_mask = 0
        self._rx_mask = 0

    def get_serial_ports(self):
        """Returns the available serial ports as a list of dicts with 'device' and 'description'."""
        ports = serial.tools.list_ports.comports()
        return [
            {"device": port.device, "description": port.description or "Unknown"}
            for port in ports
        ]

    def connect(self, port, baudrate, on_success, on_fail):
        """Connect to the serial port in a separate thread, calling callbacks on success/failure."""

        def connect_thread():
            try:
                print(f"DEBUG: Opening serial port {port} at {baudrate} baud")
                if self._serial_obj is not None and self._serial_obj.is_open:
                    self._serial_obj.close()
                self._serial_obj = serial.Serial(port, baudrate, timeout=1)
                print(f"DEBUG: Serial port opened: {self._serial_obj.is_open}")
                self.connected = True
                self._stop_event.clear()
                self._listener_thread = threading.Thread(
                    target=self._listen_serial, daemon=True
                )
                self._listener_thread.start()
                on_success()
            except Exception as exc:  # pylint: disable=broad-except
                self.connected = False
                on_fail(str(exc))

        threading.Thread(target=connect_thread, daemon=True).start()

    def disconnect(self):
        """Disconnect from the serial port and reset state."""
        if self._serial_obj is not None and self._serial_obj.is_open:
            self._serial_obj.close()
        self._serial_obj = None
        self.connected = False
        self._stop_event.set()
        if self._listener_thread and self._listener_thread.is_alive():
            self._listener_thread.join(timeout=1.0)
        with self._lock:
            self._tx_mask = 0
            self._rx_mask = 0
        self._event_callback = None

    def is_serial_open(self):
        """Check if the serial port is currently open."""
        return self._serial_obj is not None and self._serial_obj.is_open

    def register_event_callback(self, callback):
        """Register a callable that receives event dictionaries from the ESP32."""
        self._event_callback = callback

    def send_status_update(self, arm_pad, arm_hmi, continuity):
        """
        Push the current system status to the ESP32 so it can update its LEDs.
        """
        mask = 0
        if arm_hmi:
            mask |= TX_ARM_HMI
        if arm_pad:
            mask |= TX_ARM_PAD
        if continuity:
            mask |= TX_CONTINUITY
        with self._lock:
            self._tx_mask = mask
        self._write_byte(mask)

    def _write_byte(self, value):
        """Write a single byte to the ESP32."""
        if self._serial_obj and self._serial_obj.is_open:
            try:
                self._serial_obj.write(bytes([value & 0xFF]))
                self._serial_obj.flush()
            except Exception as exc:  # pylint: disable=broad-except
                print(f"DEBUG: Serial write failed: {exc}")

    def _listen_serial(self):
        """Continuously consume bytes emitted by the ESP32."""
        while not self._stop_event.is_set():
            try:
                if not (self._serial_obj and self._serial_obj.is_open):
                    break
                raw = self._serial_obj.read(1)
                if not raw:
                    continue
                self._handle_rx_byte(raw[0])
            except Exception as exc:  # pylint: disable=broad-except
                if not self._stop_event.is_set():
                    print(f"DEBUG: Serial listener error: {exc}")
                break

    def _handle_rx_byte(self, byte):
        """Handle received byte and detect edges for launch signal."""
        with self._lock:
            prev_mask = self._rx_mask
            if byte == prev_mask:
                return
            self._rx_mask = byte
        payload = {
            "type": "status",
            "arm_hmi": bool(byte & RX_ARM_HMI),
            "launch": bool(byte & RX_LAUNCH),
            "launch_edge": bool((byte & RX_LAUNCH) and not (prev_mask & RX_LAUNCH)),
        }
        self._emit_event(payload)

    def _emit_event(self, payload):
        """Invoke the registered callback (if any) with the latest payload."""
        if self._event_callback:
            try:
                self._event_callback(payload)
            except Exception as exc:  # pylint: disable=broad-except
                print(f"DEBUG: Serial callback error: {exc}")


rlcu_serial = RLCUSerial()