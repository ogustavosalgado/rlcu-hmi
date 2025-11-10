"""Pad detail screen logic handling per-pad telemetry and launch controls."""

from datetime import datetime

# Kivy imports
from kivy.clock import Clock
from kivy.properties import NumericProperty, BooleanProperty, ColorProperty, StringProperty
from kivy.uix.screenmanager import Screen
from kivy.metrics import dp

# KivyMD imports
from kivymd.uix.snackbar import MDSnackbar, MDSnackbarSupportingText, MDSnackbarButtonContainer, MDSnackbarActionButton, MDSnackbarActionButtonText, MDSnackbarCloseButton

# Local imports
from globals import pad_data, pad_data_lock, flag_status
from rlcu_serial import rlcu_serial
from rlcu_socket import rlcu_socket


class PadDetailScreen(Screen):
    """Screen for detailed view of a specific launch pad."""
    pad_num = NumericProperty(0)
    pad_letter = StringProperty("")
    team_id = NumericProperty(0)
    rssi = NumericProperty(0.0)
    rssi_color = ColorProperty("red")
    continuity = BooleanProperty(False)
    continuity_color = ColorProperty("red")
    arm_status = BooleanProperty(False)
    arm_color = ColorProperty("red")
    voltage = NumericProperty(0.0)
    voltage_color = ColorProperty("red")
    last_seen = NumericProperty(0)
    last_seen_color = ColorProperty("black")
    ip_address = StringProperty("")
    arm_hmi = BooleanProperty(False)

    last_seen_checklist_color = ColorProperty("red")
    flag_checklist_color = ColorProperty("red")
    arm_checklist_color = ColorProperty("red")
    flag_checklist_status = StringProperty("red")


    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.pad_letter = ""
        self._suppress_arm_checkbox = False
        self._revert_event = None

    def update_serial_label_color(self):
        """Update the connection status label in the UI."""

        def do_update(dt):
            label = self.ids.get("serial_label")
            if label:
                if rlcu_serial.connected:
                    label.md_theme_color = "Custom"
                    label.text_color = (0, 1, 0, 1)  # Green
                else:
                    label.md_theme_color = "Custom"
                    label.text_color = (1, 0, 0, 1)  # Red
        Clock.schedule_once(do_update, 0)

    def update_socket_label_color(self):
        """Update the socket status label in the UI."""

        def do_update(dt):
            label = self.ids.get("socket_label")
            if label:
                if rlcu_socket.listening:
                    label.md_theme_color = "Custom"
                    label.text_color = (0, 1, 0, 1)  # Green
                else:
                    label.md_theme_color = "Custom"
                    label.text_color = (1, 0, 0, 1)  # Red

        Clock.schedule_once(do_update, 0)

    def update_time(self, dt):
        now = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        self.ids.datetime_label.text = now

    def update_data(self, dt):
        """Update pad data fields."""
        with pad_data_lock:
            pad = pad_data[self.pad_num]
        self.team_id = pad.team_id
        self.rssi = pad.rssi
        self.rssi_color = pad.rssi_color
        self.continuity = pad.continuity
        self.continuity_color = pad.continuity_color
        self.arm_status = pad.arm_status
        self.arm_color = pad.arm_color
        self.voltage = pad.voltage
        self.voltage_color = pad.voltage_color
        self.ip_address = pad.ip_address
        self.last_seen = pad.last_seen
        self.last_seen_color = pad.last_seen_color

        self._update_checklist_status()
        self._update_flag_image()

    def set_team_id(self):
        """Update the team ID on the corresponding pad card."""
        team_id = self.ids.team_id_field.text.strip()
        with pad_data_lock:
            pad_data[self.pad_num].team_id = int(team_id) if team_id.isdigit() else 0
            self.team_id = pad_data[self.pad_num].team_id

    def _update_checklist_status(self):
        # Update Checklist Statuses
        self.last_seen_checklist_color = (
            "green" if self.last_seen <= 30 else "red"
        )
        self.ids.last_seen_icon.icon = (
            "check-circle" if self.last_seen <= 30 else "alert-circle"
        )
        
        if flag_status[0] == "red":
            self.flag_checklist_color = "green"
            self.ids.flag_icon.icon = "check-circle"
            self.flag_checklist_status = "Launch Area is CLEAR"
        else:
            self.flag_checklist_color = "red"
            self.ids.flag_icon.icon = "alert-circle"
            self.flag_checklist_status = "Launch Area is NOT CLEAR"
            
        self.arm_checklist_color = (
            "green" if self.arm_status else "red"
        )
        self.ids.arm_icon.icon = (
            "check-circle" if self.arm_status else "alert-circle"
        )

    def _update_flag_image(self):
        if flag_status[0] == "green":
            self.ids.flag_image.source = "assets/greenflag.png"
        elif flag_status[0] == "yellow":
            self.ids.flag_image.source = "assets/yellowflag.png"
        else:
            self.ids.flag_image.source = "assets/redflag.png"

    def on_checkbox_active(self, checkbox, value):
        if self._suppress_arm_checkbox:
            return
        if value:
            self.arm_hmi = True
            self.ids.launch_button.md_bg_color = (0.7, 1, 0.7)
            if self._revert_event:
                Clock.unschedule(self._revert_event)
                self._revert_event = None
        else:
            self.arm_hmi = False
            self.ids.launch_button.md_bg_color = (1, 0.7, 0.7)
        with pad_data_lock:
            pad_data[self.pad_num].rdy_on = self.arm_hmi
        if rlcu_socket.has_active_connection(self.pad_num):
            rlcu_socket.send_command(
                pad_num=self.pad_num,
                command=rlcu_socket.CMD_RDY_TO_FIRE,
                enable=self.arm_hmi,
            )

    def initiate_launch_sequence(self):
        """Initiate the launch sequence if all conditions are met."""
        if not self.arm_hmi:
            snackbar =MDSnackbar(
                MDSnackbarSupportingText(
                    text="Please confirm launch by checking the box.",
                    font_style="Headline",
                    role="large",
                    halign="center",
                ),
                MDSnackbarButtonContainer(
                    MDSnackbarCloseButton(
                        icon="close",
                        on_release=lambda x: snackbar.dismiss(),
                    ),
                    pos_hint={"center_y": 0.5}
                ),
                y=dp(24),
                orientation="horizontal",
                pos_hint={"center_x": 0.5, "center_y": 0.5},
                size_hint_x=0.5,
                size_hint_y=0.06,
            )
            snackbar.open()
        else:
            snackbar =MDSnackbar(
                MDSnackbarSupportingText(
                    text="Launch sequence initiated!",
                    font_style="Headline",
                    role="large",
                    halign="center",
                ),
                MDSnackbarButtonContainer(
                    MDSnackbarCloseButton(
                        icon="close",
                        on_release=lambda x: snackbar.dismiss(),
                    ),
                    pos_hint={"center_y": 0.5}
                ),
                y=dp(24),
                orientation="horizontal",
                pos_hint={"center_x": 0.5, "center_y": 0.5},
                size_hint_x=0.5,
                size_hint_y=0.06,
            )
            snackbar.open()
            if rlcu_socket.has_active_connection(self.pad_num):
                rlcu_socket.send_command(
                    pad_num=self.pad_num,
                    command=rlcu_socket.CMD_LAUNCH,
                    enable=None,
                )
            if self._revert_event:
                Clock.unschedule(self._revert_event)
            # Schedule an automatic revert to reset the HMI arm state post-launch.
            self._revert_event = Clock.schedule_once(
                lambda dt: self.revert_arm_hmi(), 1
            )

    def revert_arm_hmi(self):
        if self._revert_event:
            Clock.unschedule(self._revert_event)
            self._revert_event = None
        if not self.arm_hmi:
            return
        self.arm_hmi = False
        self.ids.arm_hmi_checkbox.active = False
        with pad_data_lock:
            pad_data[self.pad_num].rdy_on = False
        if rlcu_socket.has_active_connection(self.pad_num):
            rlcu_socket.send_command(
                pad_num=self.pad_num,
                command=rlcu_socket.CMD_RDY_TO_FIRE,
                enable=False,
            )

    def update_button_texts(self):
        """Update the button texts based on current states."""
        with pad_data_lock:
            if pad_data[self.pad_num].buzzer_on:
                self.ids.buzzer_button_text.text = "Buzzer OFF"
            else:
                self.ids.buzzer_button_text.text = "Buzzer ON"

            if pad_data[self.pad_num].led_on:
                self.ids.led_button_text.text = "LED OFF"
            else:
                self.ids.led_button_text.text = "LED ON"
    
    def toggle_buzzer(self):
        """Toggle the buzzer state."""
        with pad_data_lock:
            current_state = pad_data[self.pad_num].buzzer_on
        next_state = not current_state
        if rlcu_socket.send_command(
            pad_num=self.pad_num,
            command=rlcu_socket.CMD_BUZZER,
            enable=next_state,
        ):
            with pad_data_lock:
                pad_data[self.pad_num].buzzer_on = next_state
        self.update_button_texts()

    def toggle_led(self):
        """Toggle the LED state."""
        with pad_data_lock:
            current_state = pad_data[self.pad_num].led_on
        next_state = not current_state
        if rlcu_socket.send_command(
            pad_num=self.pad_num,
            command=rlcu_socket.CMD_LED,
            enable=next_state,
        ):
            with pad_data_lock:
                pad_data[self.pad_num].led_on = next_state
        self.update_button_texts()


    def on_enter(self, *args):
        """Called when entering the pad detail screen."""
        self.update_data(0)
        self.update_socket_label_color()
        self.update_serial_label_color()
        self.update_button_texts()
        self.pad_letter = chr(ord('A') + self.pad_num)

    def on_leave(self):
        if self._revert_event:
            Clock.unschedule(self._revert_event)
            self._revert_event = None
        self.arm_hmi = False
        self.ids.arm_hmi_checkbox.active = False
        with pad_data_lock:
            pad_data[self.pad_num].rdy_on = False
        if rlcu_socket.has_active_connection(self.pad_num):
            rlcu_socket.send_command(
                pad_num=self.pad_num,
                command=rlcu_socket.CMD_RDY_TO_FIRE,
                enable=False,
            )

    def on_kv_post(self, base_widget):
        self.update_event = Clock.schedule_interval(self.update_data, 1)
        Clock.schedule_interval(self.update_time, 1)

    def _has_active_pad_connection(self):
        return rlcu_socket.has_active_connection(self.pad_num)