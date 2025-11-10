"""Test harness simulating pad discovery, telemetry streaming, and command echoes."""
import socket
import struct
import threading
import time

PORT = 5555
AUTH_KEY = "RLCU!2025"
BUFFER_SIZE = 1024
TELEMETRY_STRUCT = struct.Struct("<ff??Bx")
connections_lock = threading.Lock()
tcp_connections = {}
COMMAND_INTERVAL = 2.0
RDY_TO_FIRE = 1 << 0
FIRE = 1 << 1
LED = 1 << 2
BUZZER = 1 << 3
COMMAND_PATTERN = [
    RDY_TO_FIRE,
    RDY_TO_FIRE | FIRE,
    LED,
    BUZZER,
]

def parse_payload(data: bytes):
    fmt = "!B16s"
    size = struct.calcsize(fmt)
    if len(data) < size:
        raise ValueError("Packet too short")
    device_id, auth_raw = struct.unpack(fmt, data[:size])
    auth_key = auth_raw.split(b"\x00", 1)[0].decode("ascii", errors="ignore")
    return device_id, auth_key

def parse_telemetry(data: bytes):
    payload = data[:TELEMETRY_STRUCT.size]
    if len(payload) < TELEMETRY_STRUCT.size:
        raise ValueError("Telemetry packet too short")
    voltage, rssi, rbf_status, squib_continuity, igniter_id = TELEMETRY_STRUCT.unpack(payload)
    return {
        "voltage": voltage,
        "rssi": rssi,
        "rbf_status": bool(rbf_status),
        "squib_continuity": bool(squib_continuity),
        "igniter_id": igniter_id,
    }

def recv_exact(sock: socket.socket, size: int) -> bytes:
    buffer = bytearray()
    while len(buffer) < size:
        try:
            chunk = sock.recv(size - len(buffer))
        except socket.timeout:
            raise TimeoutError("Telemetry receive timed out")
        if not chunk:
            raise ValueError("Telemetry connection closed prematurely")
        buffer.extend(chunk)
    return bytes(buffer)

def telemetry_loop(ip_address: str, conn: socket.socket):
    buffer = bytearray()
    last_data_ts = time.time()
    last_command_ts = 0.0
    conn.settimeout(1.0)
    try:
        while True:
            now = time.time()
            if now - last_command_ts >= COMMAND_INTERVAL:
                # Cycle through canned commands so the HMI can observe responses.
                command_idx = int(now / COMMAND_INTERVAL) % len(COMMAND_PATTERN)
                command_byte = COMMAND_PATTERN[command_idx]
                try:
                    conn.sendall(bytes([command_byte]))
                except OSError as exc:
                    print(f"Failed to send command to {ip_address} ({exc})")
                    break
                last_command_ts = now
            try:
                chunk = conn.recv(TELEMETRY_STRUCT.size - len(buffer))
            except socket.timeout:
                chunk = None
            except OSError as exc:
                print(f"Telemetry receive error from {ip_address} ({exc})")
                break
            if chunk is None:
                pass
            elif not chunk:
                print(f"Telemetry connection to {ip_address} lost (peer closed)")
                break
            else:
                buffer.extend(chunk)
                last_data_ts = time.time()
                while len(buffer) >= TELEMETRY_STRUCT.size:
                    packet = bytes(buffer[:TELEMETRY_STRUCT.size])
                    del buffer[:TELEMETRY_STRUCT.size]
                    try:
                        telemetry = parse_telemetry(packet)
                        print(
                            f"Telemetry from {ip_address}: "
                            f"voltage={telemetry['voltage']:.2f}V, "
                            f"rssi={telemetry['rssi']:.2f}, "
                            f"rbf={telemetry['rbf_status']}, "
                            f"continuity={telemetry['squib_continuity']}, "
                            f"id={telemetry['igniter_id']}"
                        )
                    except ValueError as exc:
                        print(f"Ignoring malformed telemetry from {ip_address} ({exc})")
            if time.time() - last_data_ts >= 10.0:
                print(f"Telemetry connection to {ip_address} lost (timeout)")
                break
    finally:
        conn.close()
        with connections_lock:
            tcp_connections.pop(ip_address, None)

def start_telemetry_connection(ip_address: str):
    with connections_lock:
        existing = tcp_connections.get(ip_address)
        if isinstance(existing, threading.Thread) and existing.is_alive():
            return
        if existing is not None:
            tcp_connections.pop(ip_address, None)
        tcp_connections[ip_address] = None
    try:
        conn = socket.create_connection((ip_address, PORT), timeout=2.0)
    except OSError as exc:
        print(f"Failed to establish telemetry connection to {ip_address}:{PORT} ({exc})")
        with connections_lock:
            tcp_connections.pop(ip_address, None)
        return
    thread = threading.Thread(target=telemetry_loop, args=(ip_address, conn), daemon=True)
    thread.start()
    with connections_lock:
        tcp_connections[ip_address] = thread
    print(f"Established telemetry connection to {ip_address}:{PORT}")

def main():
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    udp_sock.bind(("", PORT))
    print(f"Listening for UDP packets on port {PORT}")
    try:
        while True:
            data, addr = udp_sock.recvfrom(BUFFER_SIZE)
            try:
                device_id, auth = parse_payload(data)
                if auth != AUTH_KEY:
                    print(f"Ignoring packet from {addr[0]}: invalid auth key")
                    continue
                print(f"Received valid packet from {addr[0]} (ID {device_id})")
                start_telemetry_connection(addr[0])
            except ValueError as exc:
                print(f"Ignoring malformed packet from {addr[0]} ({exc})")
    except KeyboardInterrupt:
        print("Stopping listener")
    finally:
        udp_sock.close()

if __name__ == "__main__":
    main()
