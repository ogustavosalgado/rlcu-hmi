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
from rlcu_socket import rlcu_socket


class SocketDialog(MDBoxLayout):
    """
    Dialog content for socket connection settings.
    Handles host and port selection.
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._setup_fields()
    
    def _setup_fields(self):
        """Populate form fields from the active socket configuration."""
        if rlcu_socket.port:
            self.ids.port_field.text = str(rlcu_socket.port)
        else:
            self.ids.port_field.text = ""

    def save_config(self, *args):
        """Save the current configuration with validation."""
        try:
            port_str = self.ids.port_field.text.strip()
            
            rlcu_socket.set_port(int(port_str))
            if rlcu_socket.listening:
                rlcu_socket.stop_listening()
                rlcu_socket.start_listening()
            self.dismiss()
        except (ValueError, OSError) as e:
            self.show_save_error(str(e))

    def toggle_listening(self, *args):
        """Toggle the listening state of the socket."""
        if rlcu_socket.listening:
            rlcu_socket.stop_listening()
            self.listen_btn.children[0].text = "Start Listening"
        else:
            rlcu_socket.start_listening()
            self.listen_btn.children[0].text = "Stop Listening"

    def dismiss(self):
        """Dismiss the settings dialog."""
        self.dialog.dismiss()

    def show_save_error(self, error_msg):
        """Display an error dialog for connection failures."""
        error_dialog = MDDialog(
            MDDialogHeadlineText(text="Save Error"),
            MDDialogContentContainer(
                MDLabel(
                    text=f"Failed to save configuration.\n{error_msg}",
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

    @classmethod
    def show(cls, screen):
        """Show the socket dialog with buttons and actions."""
        dialog_instance = cls()

        listen_btn_label = (
            "Stop Listening" if rlcu_socket.listening else "Start Listening"
        )

        def toggle_listening_action(*args):
            dialog_instance.toggle_listening()
            screen.update_socket_label_color()

        save_btn = MDButton(
            MDButtonText(text="Save"),
            style="text",
            on_release=dialog_instance.save_config,
        )
        cancel_btn = MDButton(
            MDButtonText(text="Cancel"),
            style="text",
            on_release=lambda x: dialog.dismiss(),
        )
        listen_btn = MDButton(
            MDButtonText(text=listen_btn_label),
            style="text",
            on_release=toggle_listening_action,
        )

        # Store button references
        dialog_instance.save_btn = save_btn
        dialog_instance.cancel_btn = cancel_btn
        dialog_instance.listen_btn = listen_btn

        # Create the dialog
        dialog = MDDialog(
            MDDialogHeadlineText(text="Socket Settings"),
            MDDialogContentContainer(
                dialog_instance,
                orientation="vertical",
            ),
            MDDialogButtonContainer(
                listen_btn,
                save_btn,
                cancel_btn,
            ),
            auto_dismiss=False,
        )

        # Store dialog reference
        dialog_instance.dialog = dialog
        dialog.open()
