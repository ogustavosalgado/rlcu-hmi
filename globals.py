import threading

n_pads = 6

class Pad:
    def __init__(self):
        self.team_id = 0
        self.ip_address = ""
        self.rssi = -100
        self.rssi_color = "red"
        self.continuity = False
        self.continuity_color = "red"
        self.voltage = 0.0
        self.voltage_color = "red"
        self.arm_status = False
        self.arm_color = "green"
        self.last_seen = 0
        self.last_seen_color = "black"
        self.buzzer_on = False
        self.led_on = False
        self.rdy_on = False

pad_data = {i: Pad() for i in range(n_pads)}

pad_data_lock = threading.Lock()

flag_status = ["green"]