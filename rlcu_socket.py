"""
This module handles socket-based communication with the RLCU pads.

Pads announce themselves over UDP and, when authenticated, accept a TCP connection
for streaming telemetry. Each pad gets a dedicated worker responsible for keeping
its TCP session alive, parsing telemetry frames, and exposing a simple command path
for the UI to use.
"""

import socket
import struct
import threading
import time
from globals import pad_data, pad_data_lock, n_pads


AUTH_KEY = "RLCU!2025"
DISCOVERY_STRUCT = struct.Struct("!B16s")   # pad id + 16-byte auth key
TELEMETRY_STRUCT = struct.Struct("<ff??Bx")  # voltage, rssi, rbf, continuity, igniter, pad
TELEMETRY_TIMEOUT = 10.0                    # seconds without data before reconnect
RECONNECT_DELAY = 2.0                       # delay between reconnect attempts


class RLCUSocket:
    def __init__(self, broadcast_ip="127.0.0.255", port=5555):
        self.broadcast_ip = broadcast_ip
        self.port = port
        self.unicast_tx_mode = False

        self._udp_sock = None
        self._udp_thread = None
        self._stop_event = threading.Event()

        self._connections_lock = threading.Lock()
        self._connections = {}          # ip -> socket
        self._connection_threads = {}   # ip -> thread
        self._pad_peers = {}            # pad_num -> ip

        self.listening = False

        self._timer_thread = threading.Thread(target=self._timer_loop, daemon=True)
        self._timer_thread.start()

        # Command bit flags
        self.CMD_RDY_TO_FIRE = 0b00000001
        self.CMD_LAUNCH = 0b00000010
        self.CMD_LED = 0b00000100
        self.CMD_BUZZER = 0b00001000

        self._command_lock = threading.Lock()
        self._command_state = {i: 0 for i in range(n_pads)}
        # Track the last command mask per pad together with delivery status metadata.
        self._command_history = {
            i: {"mask": 0, "success": False, "timestamp": 0.0} for i in range(n_pads)
        }



    def validate_ip(self, ip):
        """Validate IP address."""
        socket.inet_aton(ip)

    def validate_port(self, port):
        """Validate port number."""
        if not (1 <= port <= 65535):
            raise ValueError("Port must be between 1 and 65535")

    def set_broadcast_ip(self, ip):
        """Set the UDP discovery address (kept for compatibility)."""
        self.validate_ip(ip)
        self.broadcast_ip = ip

    def set_port(self, port):
        """Set the UDP/TCP port used for discovery and telemetry."""
        self.validate_port(port)
        self.port = port

    def send_command(self, pad_num, command, enable=None):
        """
        Update the persistent command mask for *pad_num* and transmit the full
        state in a single byte. When *enable* is True/False the bit is set/cleared.
        When *enable* is None the command is treated as momentary (one-shot) and
        only OR’d into the transmitted mask.
        """
        with pad_data_lock:
            ip_address = pad_data.get(pad_num).ip_address if pad_num in pad_data else ""
        if not ip_address:
            print(f"INFO: Command skipped for pad {pad_num}: no IP address")
            return False

        with self._connections_lock:
            conn = self._connections.get(ip_address)
        if not conn:
            print(f"INFO: Command skipped for pad {pad_num}: no active TCP connection")
            return False

        with self._command_lock:
            state = self._command_state.get(pad_num, 0)
            original_state = state
            if enable is True and command:
                state |= command
            elif enable is False and command:
                state &= ~command
            if enable is not None:
                self._command_state[pad_num] = state
                mask = state
            else:
                mask = state | (command if command else 0)

        print(
            f"INFO: send_command -> pad={pad_num}, ip={ip_address}, "
            f"base_state=0b{original_state:08b}, command=0b{(command or 0):08b}, "
            f"enable={enable}, mask=0b{mask:08b}"
        )

        payload = bytes([mask & 0xFF])
        try:
            conn.sendall(payload)
            with self._command_lock:
                self._command_history[pad_num] = {
                    "mask": mask,
                    "success": True,
                    "timestamp": time.time(),
                }
            return True
        except OSError as exc:
            print(f"DEBUG: Failed to send command to pad {pad_num} ({exc})")
            with self._command_lock:
                self._command_history[pad_num] = {
                    "mask": mask,
                    "success": False,
                    "timestamp": time.time(),
                }
            return False

    def get_last_command_status(self, pad_num):
        """Return the most recent command state for a pad."""
        with self._command_lock:
            return dict(self._command_history.get(pad_num, {}))

    def has_active_connection(self, pad_num):
        """Check if there is an active TCP connection for the given pad."""
        with pad_data_lock:
            pad = pad_data.get(pad_num)
            ip_address = pad.ip_address if pad else ""
        if not ip_address:
            return False
        with self._connections_lock:
            return ip_address in self._connections

    def start_listening(self):
        """Start asynchronous UDP discovery."""
        if self.listening:
            return
        self.listening = True
        self._stop_event.clear()
        self._udp_thread = threading.Thread(target=self._udp_loop, name="RLCU-UDP", daemon=True)
        self._udp_thread.start()

    def stop_listening(self):
        """Stop discovery and tear down every TCP session."""
        if not self.listening:
            return
        self.listening = False
        self._stop_event.set()

        if self._udp_sock:
            try:
                self._udp_sock.close()
            except OSError:
                pass
            self._udp_sock = None

        if self._udp_thread and self._udp_thread.is_alive():
            self._udp_thread.join(timeout=1.0)
        self._udp_thread = None

        with self._connections_lock:
            for ip, conn in list(self._connections.items()):
                try:
                    conn.close()
                except OSError:
                    pass
            self._connections.clear()

        for ip, thread in list(self._connection_threads.items()):
            if thread.is_alive():
                thread.join(timeout=1.0)
        self._connection_threads.clear()
        self._pad_peers.clear()
        with self._command_lock:
            self._command_state = {i: 0 for i in range(n_pads)}
            self._command_history = {
                i: {"mask": 0, "success": False, "timestamp": time.time()}
                for i in range(n_pads)
            }
        self._stop_event.clear()

    def _udp_loop(self):
        """Listen for discovery packets and spawn per-pad TCP workers."""
        try:
            self._udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._udp_sock.bind(("", self.port))
            while not self._stop_event.is_set():
                try:
                    data, addr = self._udp_sock.recvfrom(1024)
                except OSError:
                    break
                self._handle_discovery(data, addr)
        finally:
            if self._udp_sock:
                try:
                    self._udp_sock.close()
                except OSError:
                    pass
                self._udp_sock = None

    def _handle_discovery(self, data, addr):
        """Validate discovery/authentication packets and ensure a TCP worker exists."""
        ip_address = addr[0]
        if len(data) < DISCOVERY_STRUCT.size:
            print(f"DEBUG: Ignoring short discovery from {ip_address}")
            return

        pad_num, raw_auth = DISCOVERY_STRUCT.unpack_from(data)
        auth_key = raw_auth.split(b"\x00", 1)[0].decode("ascii", errors="ignore")

        if auth_key != AUTH_KEY:
            print(f"DEBUG: Ignoring discovery from {ip_address}: invalid auth")
            return
        if pad_num >= n_pads:
            print(f"DEBUG: Ignoring discovery from {ip_address}: invalid pad index {pad_num}")
            return

        with pad_data_lock:
            pad = pad_data.get(pad_num)
            if pad:
                pad.ip_address = ip_address
                pad.last_seen = 0
                pad.last_seen_color = "black"

        self._pad_peers[pad_num] = ip_address
        self._ensure_connection(pad_num, ip_address)

    def _ensure_connection(self, pad_num, ip_address):
        """Create (or reuse) a TCP worker thread for a pad."""
        with self._connections_lock:
            worker = self._connection_threads.get(ip_address)
            if worker and worker.is_alive():
                return

        thread = threading.Thread(
            target=self._connection_worker, args=(pad_num, ip_address), daemon=True, name=f"RLCU-TCP-{ip_address}"
        )
        with self._connections_lock:
            self._connection_threads[ip_address] = thread
        thread.start()

    def _connection_worker(self, pad_num, ip_address):
        """Keep a live TCP session with a pad, reconnecting on failures."""
        while self.listening and not self._stop_event.is_set():
            conn = None
            try:
                conn = socket.create_connection((ip_address, self.port), timeout=2.0)
                conn.settimeout(1.0)
                with self._connections_lock:
                    self._connections[ip_address] = conn
                with self._command_lock:
                    mask = self._command_state.get(pad_num, 0)
                try:
                    conn.sendall(bytes([mask & 0xFF]))
                    with self._command_lock:
                        # Successful reconnection should re-confirm the stored command mask.
                        self._command_history[pad_num] = {
                            "mask": mask,
                            "success": True,
                            "timestamp": time.time(),
                        }
                except OSError as exc:
                    print(f"DEBUG: Failed to sync command mask to {ip_address} ({exc})")
                    with self._command_lock:
                        self._command_history[pad_num] = {
                            "mask": mask,
                            "success": False,
                            "timestamp": time.time(),
                        }
                self._telemetry_loop(pad_num, ip_address, conn)
            except OSError as exc:
                print(f"DEBUG: TCP error with {ip_address} ({exc})")
            finally:
                if conn:
                    try:
                        conn.close()
                    except OSError:
                        pass
                with self._connections_lock:
                    self._connections.pop(ip_address, None)

            if not self.listening or self._stop_event.is_set():
                break
            time.sleep(RECONNECT_DELAY)

        with self._connections_lock:
            self._connection_threads.pop(ip_address, None)

    def _telemetry_loop(self, pad_num, ip_address, conn):
        """Read and apply telemetry frames until the link drops."""
        buffer = bytearray()
        last_data_ts = time.time()

        while self.listening and not self._stop_event.is_set():
            try:
                chunk = conn.recv(TELEMETRY_STRUCT.size - len(buffer))
            except socket.timeout:
                chunk = None
            except OSError as exc:
                print(f"DEBUG: Telemetry receive error from {ip_address} ({exc})")
                break

            if chunk:
                buffer.extend(chunk)
                last_data_ts = time.time()
                while len(buffer) >= TELEMETRY_STRUCT.size:
                    frame = bytes(buffer[:TELEMETRY_STRUCT.size])
                    del buffer[:TELEMETRY_STRUCT.size]
                    telemetry = self._parse_telemetry(frame)
                    self._apply_telemetry(pad_num, ip_address, telemetry)
            elif chunk is None:
                pass
            else:  # peer closed
                print(f"DEBUG: Telemetry connection closed by {ip_address}")
                break

            if time.time() - last_data_ts >= TELEMETRY_TIMEOUT:
                print(f"DEBUG: Telemetry timeout for {ip_address}")
                break

    def _parse_telemetry(self, frame):
        """Decode a telemetry record."""
        if len(frame) != TELEMETRY_STRUCT.size:
            raise ValueError("Telemetry frame size mismatch")
        voltage, rssi, rbf_status, squib_continuity, igniter_id = TELEMETRY_STRUCT.unpack(frame)
        return {
            "voltage": voltage,
            "rssi": rssi,
            "rbf_status": bool(rbf_status),
            "squib_continuity": bool(squib_continuity),
            "igniter_id": igniter_id,
        }

    def _apply_telemetry(self, pad_num, ip_address, telemetry):
        """Update shared pad data from a telemetry frame."""
        with pad_data_lock:
            pad = pad_data.get(pad_num)
            if not pad:
                return
            pad.ip_address = ip_address
            pad.last_seen = 0
            pad.last_seen_color = "black"

            pad.voltage = telemetry["voltage"]
            pad.voltage_color = "green" if pad.voltage >= 10.0 else "red"

            pad.rssi = telemetry["rssi"]
            if pad.rssi > -50:
                pad.rssi_color = "green"
            elif pad.rssi > -70:
                pad.rssi_color = "yellow"
            else:
                pad.rssi_color = "red"

            pad.continuity = telemetry["squib_continuity"]
            pad.continuity_color = "green" if pad.continuity else "red"

            pad.arm_status = telemetry["rbf_status"]
            pad.arm_color = "red" if pad.arm_status else "green"

    def _timer_loop(self):
        """Increment last_seen counters once per second for UI staleness indicators."""
        while True:
            time.sleep(1)
            with pad_data_lock:
                for pad in pad_data.values():
                    pad.last_seen += 1
                    pad.last_seen_color = "red" if pad.last_seen > 30 else "black"


rlcu_socket = RLCUSocket()
