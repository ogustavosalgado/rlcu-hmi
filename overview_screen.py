import sys
from datetime import datetime

# Kivy imports
from kivy.factory import Factory
from kivy.clock import Clock
from kivy.uix.screenmanager import Screen

# KivyMD imports
from kivymd.app import MDApp
from kivymd.uix.button import MDButton, MDButtonText
from kivymd.uix.label import MDLabel
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.dialog import (
    MDDialog,
    MDDialogHeadlineText,
    MDDialogContentContainer,
    MDDialogButtonContainer,
)

# Local imports
from globals import n_pads, flag_status
from rlcu_serial import rlcu_serial
from rlcu_socket import rlcu_socket
from serial_dialog import SerialDialog
from socket_dialog import SocketDialog

class OverviewScreen(Screen):
    """
    Main overview screen displaying the launch pads, connection status, and settings access.
    """

    _cards_added = False
    exit_dialog = None

    def set_flag(self, flag, *args):
        if flag == "green":
            self.ids.flag_image.source = "assets/greenflag.png"
            flag_status[0] = "green"
        elif flag == "yellow":
            self.ids.flag_image.source = "assets/yellowflag.png"
            flag_status[0] = "yellow"
        else:
            self.ids.flag_image.source = "assets/redflag.png"
            flag_status[0] = "red"
        self.flag_dialog.dismiss()

    def show_flag_dialog(self, *args):
        """Present a quick flag selector for the current launch range status."""

        self.flag_dialog = MDDialog(
            MDDialogHeadlineText(text="Select the flag color"),
            MDDialogButtonContainer(
                MDButton(
                    MDButtonText(text="Green"),
                    style="text",
                    on_release=lambda x: self.set_flag("green"),
                ),
                MDButton(
                    MDButtonText(text="Yellow"),
                    style="text",
                    on_release=lambda x: self.set_flag("yellow"),
                ),
                MDButton(
                    MDButtonText(text="Red"),
                    style="text",
                    on_release=lambda x: self.set_flag("red"),
                ),
            ),
            auto_dismiss=False,
        )
        self.flag_dialog.open()

    def show_serial_dialog(self):
        SerialDialog.show(self)

    def show_socket_dialog(self):
        SocketDialog.show(self)

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
        """Update the datetime label every second."""
        now = datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        self.ids.datetime_label.text = now

    def show_exit_dialog(self, *args):
        if self.exit_dialog:
            return
        self.exit_dialog = MDDialog(
            MDDialogHeadlineText(text="Exit Application"),
            MDDialogContentContainer(
                MDLabel(text="Are you sure you want to exit?", halign="center")
            ),
            MDDialogButtonContainer(
                MDButton(
                    MDButtonText(text="Cancel"),
                    style="text",
                    on_release=self.close_exit_dialog,
                ),
                MDButton(
                    MDButtonText(text="Exit"),
                    style="text",
                    on_release=self.exit_app,
                ),
            ),
            auto_dismiss=False,
        )
        self.exit_dialog.open()

    def close_exit_dialog(self, *args):
        if self.exit_dialog:
            self.exit_dialog.dismiss()
            self.exit_dialog = None

    def exit_app(self, *args):
        self.close_exit_dialog()
        MDApp.get_running_app().stop()
        sys.exit(0)
    
    def on_enter(self, *args):
        self.update_socket_label_color()
        self.update_serial_label_color()
        return super().on_enter(*args)
    
    def on_kv_post(self, base_widget):
        """Initialize the pad grid after KV loading."""
        if self._cards_added:
            return
        self.pad_cards = {}
        pad_grid = self.ids.pad_grid
        pad_grid.clear_widgets()

        for i in range(n_pads):
            card = Factory.PadCard()
            card.pad_num = i
            card.pad_letter = chr(ord('A') + i)
            self.pad_cards[i] = card
            pad_grid.add_widget(card)
        self._cards_added = True
        Clock.schedule_interval(self.update_time, 1)