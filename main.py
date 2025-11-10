"""
RLCU (Remote Launch Control Unit) HMI Application

"""

# Kivy imports
from kivy.lang import Builder
from kivy.core.window import Window
from kivy.factory import Factory

# KivyMD imports
from kivymd.app import MDApp

# Local imports
from overview_screen import OverviewScreen
from pad_detail_screen import PadDetailScreen
from pad_card import PadCard
from serial_dialog import SerialDialog
from socket_dialog import SocketDialog
from rlcu_socket import rlcu_socket

class RLCUApp(MDApp):
    """Main application class for the RLCU HMI."""

    def build(self):
        """Build and return the root widget."""
        self.theme_cls.theme_style = "Light"
        self.theme_cls.primary_palette = "Aqua"
        Window.fullscreen = "auto"

        # Load KV files
        Builder.load_file("pad_detail_screen.kv")
        Builder.load_file("pad_card.kv")
        Builder.load_file("serial_dialog.kv")
        Builder.load_file("socket_dialog.kv")
        root = Builder.load_file("overview_screen.kv")

        # Add pad detail screen
        pad_detail_screen = Factory.PadDetailScreen(name="pad_detail")
        root.add_widget(pad_detail_screen)

        from kivy.config import Config

        Config.set("input", "mouse", "mouse,disable_multitouch")

        # Bind window close event
        Window.bind(on_request_close=self.on_request_close)

        # Start socket listener
        rlcu_socket.start_listening()
        return root

    def on_request_close(self, window, source=None):
        """Handle window close request by showing exit dialog or navigating back."""
        if self.root.current == "pad_detail":
            # On pad detail screen, ESC goes back to overview
            self.root.current = "overview"
            return True  # Prevent window from closing
        else:
            # On overview screen, show exit dialog
            overview = self.root.get_screen("overview")
            overview.show_exit_dialog()
            return True


if __name__ == "__main__":
    RLCUApp().run()
