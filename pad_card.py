"""Lightweight card widget mirroring per-pad state in the overview grid."""

# Kivy imports
from kivy.clock import Clock
from kivy.properties import NumericProperty, BooleanProperty, ColorProperty, StringProperty

# KivyMD imports
from kivymd.uix.card import MDCard

# Local imports
from globals import pad_data, pad_data_lock


class PadCard(MDCard):
    """Card widget representing a launch pad."""

    # Initial pad data properties
    pad_num = NumericProperty(0)
    pad_letter = StringProperty("")
    team_id = NumericProperty(0)
    continuity = BooleanProperty(False)
    continuity_color = ColorProperty("red")
    arm_status = BooleanProperty(False)
    arm_color = ColorProperty("red")
    last_seen = NumericProperty(0)
    last_seen_color = ColorProperty("red")

    def update_pad_data(self, dt):
        """Update pad data fields every second."""

        with pad_data_lock:
            pad = pad_data[self.pad_num]
        self.team_id = pad.team_id
        self.continuity = pad.continuity
        self.continuity_color = pad.continuity_color
        self.arm_status = pad.arm_status
        self.arm_color = pad.arm_color
        self.last_seen = pad.last_seen
        self.last_seen_color = pad.last_seen_color

    def on_kv_post(self, base_widget):
        Clock.schedule_interval(self.update_pad_data, 1)
