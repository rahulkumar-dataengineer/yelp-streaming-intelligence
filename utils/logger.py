import logging
import sys
from pathlib import Path


_LOG_FILE = Path("logs/app.log")
_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"


class Logger:
    _APP_ROOT: str = "yelp_platform"

    @classmethod
    def _configure(cls) -> None:
        """Configures handlers once"""
        app_logger = logging.getLogger(cls._APP_ROOT)

        if app_logger.handlers:
            return

        logging.getLogger().setLevel(logging.WARNING)
        app_logger.setLevel(logging.DEBUG)
        app_logger.propagate = False  # Never passes records up to root

        formatter = logging.Formatter(fmt=_FORMAT, datefmt=_DATE_FMT)

        # Console handler: INFO+
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)

        # File handler: DEBUG+
        _LOG_FILE.parent.mkdir(exist_ok=True)
        file_handler = logging.FileHandler(
            filename=_LOG_FILE,
            mode="a",        
            encoding="utf-8",
        )

        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)

        app_logger.addHandler(console_handler)
        app_logger.addHandler(file_handler)


    @classmethod
    def get(cls, name: str) -> logging.Logger:
        return logging.getLogger(f"{cls._APP_ROOT}.{name}")


Logger._configure()
