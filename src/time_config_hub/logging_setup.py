import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def setup_logging(app_config: dict):
    """
    Setup logging configuration.

    :param str log_dir: Directory path for log files
    :param bool verbose: Enable console logging output
    :param str log_level: Logging level (INFO, ERROR)
    :return: None
    :rtype: None
    """
    verbose = app_config.get("General", {}).get("Verbosity", False)
    log_config = app_config.get("Logging", {})
    log_level = log_config.get("LogLevel", "INFO")
    log_dir = log_config.get("LogDirectory", "/var/log/tch")
    log_file = log_config.get("LogFile", "tch.log")

    # Map string log level to logging level
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "ERROR": logging.ERROR,
    }

    # Invalid log level found
    if log_level.upper() not in level_map:
        print(f"Invalid log level '{log_level}'. Defaulting to INFO.")
        log_level = "INFO"
    level = level_map.get(log_level.upper(), logging.INFO)

    log_handler = []

    try:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)

        # File handler for tch (not daemon)
        log_file = log_path / log_file
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(file_formatter)
        log_handler.append(file_handler)

    except PermissionError:
        # Can't create log directory
        print(
            f"Permission denied: cannot create log directory or log file '{log_dir}'."
        )

    console_handler = logging.StreamHandler()
    if verbose:
        console_handler.setLevel("INFO")
    else:
        console_handler.setLevel("ERROR")
    console_formatter = logging.Formatter("%(message)s")
    console_handler.setFormatter(console_formatter)
    log_handler.append(console_handler)

    logging.basicConfig(
        level=level,
        handlers=log_handler,
    )

    logger.debug(f"Logging initialized. Level: {log_level}, Directory: {log_dir}")
