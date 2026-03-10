import signal
from utils.logger import Logger

log = Logger.get(__name__)

_running: bool = True

def get_running() -> bool:
    return _running

def _handle_shutdown(signum: int, frame) -> None:
    global _running
    _running = False
    log.info("Shutdown signal received (signal %s). Finishing current batch...", signum)

def register_signal_handlers() -> None:
    signal.signal(signal.SIGINT, _handle_shutdown)
    signal.signal(signal.SIGTERM, _handle_shutdown)
    log.debug("Signal handlers registered (SIGINT, SIGTERM).")
