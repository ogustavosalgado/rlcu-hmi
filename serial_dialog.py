# Kivy imports
from kivy.clock import Clock

# KivyMD imports
from kivymd.app import MDApp
from kivymd.uix.button import MDButton, MDButtonText
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.dialog import (
    MDDialog,
    MDDialogHeadlineText,
    MDDialogContentContainer,
    MDDialogButtonContainer,
)

# Local imports
from rlcu_serial import rlcu_serial


class SerialDialog(MDBoxLayout):
    """
    Dialog content for serial connection settings.
    Handles COM port and baudrate selection, connection/disconnection.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._setup_dropdowns()

    def _setup_dropdowns(self):
        """Initialize and bind COM-port and baudrate dropdown menus for reuse."""
        # COM port dropdown
        com_ports = rlcu_serial.get_serial_ports()
        if not com_ports:
            com_ports = [{"device": "No ports found", "description": ""}]
        self.selected_com_port = com_ports[0]["device"]
        self.com_dropdown_btn = self.ids.com_dropdown_btn
        display_text = (
            f"{com_ports[0]['description']}"
            if com_ports[0]["description"]
            else com_ports[0]["device"]
        )
        self.com_dropdown_btn.children[0].text = display_text

        menu_items = [
            {
                "text": f"{port['description']}"
                if port["description"]
                else port["device"],
                "on_release": lambda x=None, p=port: self.set_com_port(p),
            }
            for port in com_ports
        ]
        self.menu = MDDropdownMenu(
            caller=self.com_dropdown_btn, items=menu_items, width="400dp"
        )
        self.com_dropdown_btn.bind(on_release=lambda x: self.menu.open())

        # Baudrate dropdown
        baudrates = ["9600", "19200", "38400", "57600", "115200"]
        self.selected_baudrate = baudrates[4]  # Default to 115200
        self.baudrate_dropdown_btn = self.ids.baudrate_dropdown_btn
        self.baudrate_dropdown_btn.children[0].text = self.selected_baudrate

        baudrate_items = [
            {
                "text": rate,
                "on_release": lambda x=None, rate=rate: self.set_baudrate(rate),
            }
            for rate in baudrates
        ]
        self.baudrate_menu = MDDropdownMenu(
            caller=self.baudrate_dropdown_btn, items=baudrate_items, width="150dp"
        )
        self.baudrate_dropdown_btn.bind(on_release=lambda x: self.baudrate_menu.open())

    def set_com_port(self, port_dict):
        """Set the selected COM port from the dict."""
        self.selected_com_port = port_dict["device"]
        display_text = (
            f"{port_dict['description']}"
            if port_dict["description"]
            else port_dict["device"]
        )
        self.com_dropdown_btn.children[0].text = display_text
        self.menu.dismiss()

    def set_baudrate(self, rate):
        """Set the selected baudrate."""
        self.selected_baudrate = rate
        self.baudrate_dropdown_btn.children[0].text = rate
        self.baudrate_menu.dismiss()

    def on_connect(self, *args):
        """Attempt to connect to the selected serial port."""
        port = str(self.selected_com_port)
        baud = int(self.selected_baudrate)

        connect_btn = self.connect_btn
        cancel_btn = self.cancel_btn
        connect_btn.children[0].text = "Connecting..."
        cancel_btn.disabled = True

        def on_success():
            def do_success(dt):
                # Restore button state and refresh the overview status indicator.
                connect_btn.children[0].text = "Connect"
                cancel_btn.disabled = False
                overview = MDApp.get_running_app().root.get_screen("overview")
                overview.update_serial_label_color()
                self.dismiss()

            Clock.schedule_once(do_success, 0)

        def on_fail(err_msg):
            def do_fail(dt):
                # Surface connection errors while keeping the dialog open.
                connect_btn.children[0].text = "Connect"
                cancel_btn.disabled = False
                overview = MDApp.get_running_app().root.get_screen("overview")
                overview.update_serial_label_color()
                self.show_connection_error(err_msg)

            Clock.schedule_once(do_fail, 0)

        rlcu_serial.connect(port, baud, on_success, on_fail)

    def on_disconnect(self, *args):
        """Disconnect from the current serial port."""
        rlcu_serial.disconnect()
        overview = MDApp.get_running_app().root.get_screen("overview")
        overview.update_serial_label_color()
        self.dismiss()

    def show_connection_error(self, error_msg):
        """Display an error dialog for connection failures."""
        error_dialog = MDDialog(
            MDDialogHeadlineText(text="Connection Error"),
            MDDialogContentContainer(
                MDLabel(
                    text=f"Failed to connect to serial port.\n{error_msg}",
                    halign="center",
                )
            ),
            MDDialogButtonContainer(
                MDButton(
                    MDButtonText(text="OK"),
                    style="text",
                    on_release=lambda x: error_dialog.dismiss(),
                ),
            ),
        )
        error_dialog.open()

    def dismiss(self):
        """Dismiss the settings dialog."""
        self.dialog.dismiss()

    @classmethod
    def show(cls, screen):
        """Show the serial dialog with buttons and actions."""
        dialog_instance = cls()

        # Create buttons based on connection status
        button_text = "Disconnect" if rlcu_serial.connected else "Connect"
        connect_action = (
            dialog_instance.on_disconnect
            if rlcu_serial.connected
            else dialog_instance.on_connect
        )

        connect_btn = MDButton(
            MDButtonText(text=button_text),
            style="text",
            on_release=connect_action,
        )
        cancel_btn = MDButton(
            MDButtonText(text="Cancel"),
            style="text",
            on_release=lambda x: dialog.dismiss(),
        )

        # Store button references
        dialog_instance.connect_btn = connect_btn
        dialog_instance.cancel_btn = cancel_btn

        # Create the dialog
        dialog = MDDialog(
            MDDialogHeadlineText(text="Serial Settings"),
            MDDialogContentContainer(
                dialog_instance,
                orientation="vertical",
            ),
            MDDialogButtonContainer(
                connect_btn,
                cancel_btn,
            ),
            auto_dismiss=False,
        )

        # Store dialog reference
        dialog_instance.dialog = dialog
        dialog.open()
