"""Re-exports from platform_commons for backward-compatible imports."""

from platform_commons.utils.signals import get_running, register_signal_handlers

__all__ = ["get_running", "register_signal_handlers"]
