import logging
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from watchdog.events import FileSystemEventHandler

from .core import TIMEConfigHub

logger = logging.getLogger(__name__)

# Executor for handling file events asynchronously
TOTAL_WORKER = 1  # Adjust based on expected load
DEBOUNCE_INTERVAL = 0.5  # seconds
SUPPORTED_EXT = [".yaml", ".yml", ".xml"]
executor = ThreadPoolExecutor(max_workers=TOTAL_WORKER)  # adjust workers

logger.debug(f"ThreadPoolExecutor initialized with {TOTAL_WORKER} workers")
logger.debug(f"Debounce interval set to {DEBOUNCE_INTERVAL} seconds")
logger.debug(f"Supported configuration file extensions: {SUPPORTED_EXT}")


class WatchHandler(FileSystemEventHandler):
    """
    Handler for file system events.

    Processes file creation, modification, and deletion events in monitored directories.
    Filters out unwanted files.
    """

    def __init__(self, app_config: dict):
        logger.debug("Initializing WatchHandler...")
        super().__init__()
        self.app_config = app_config  # This ensures app_config state is preserved
        self.debounce_interval = DEBOUNCE_INTERVAL
        self._last_event_time = {}

    def _is_valid_config_file(self, file_path: str) -> bool:
        """
        Determine if a file is a valid configuration file that should be processed.

        Accepts:
        - Configuration files with valid extensions (.yaml, .yml, .xml)
        - Non-hidden files (not starting with .)
        - Non-temporary files (not editor swap/backup files)

        :param str file_path: Path to the file to check
        :return: True if file is a valid configuration file, False otherwise
        :rtype: bool
        """
        logger.debug(f"Checking if valid config file: {file_path}")

        file_path_obj = Path(file_path)
        filename = file_path_obj.name

        # Reject hidden files (starting with .)
        if filename.startswith("."):
            logger.debug(f"Ignoring hidden file: {file_path}")
            return False

        # Check if filename ends with ~ (backup files)
        if filename.endswith("~"):
            logger.debug(f"Ignoring backup file: {file_path}")
            return False

        # Accept only files with valid configuration extensions
        file_suffix = file_path_obj.suffix.lower()
        if file_suffix not in SUPPORTED_EXT:
            logger.debug(f"Ignoring file with unsupported extension: {file_path}")
            return False

        # This is a valid configuration file
        logger.debug(f"Valid configuration file detected: {file_path}")
        return True

    def on_created(self, event):
        """
        Handle file creation events.

        :param event: File system event object
        """
        logger.debug(f"on_created event: {event}")
        self._handle_event(event, "created")

    def on_modified(self, event):
        """
        Handle file modification events.

        :param event: File system event object
        """
        logger.debug(f"on_modified event: {event}")
        self._handle_event(event, "modified")

    def on_deleted(self, event):
        """
        Handle file deletion events.

        :param event: File system event object
        """
        logger.debug(f"on_deleted event: {event}")
        file_path = str(event.src_path)
        if not event.is_directory and self._is_valid_config_file(file_path):
            logger.info(f"Submitting deleted event for processing: {file_path}")
            executor.submit(
                TIMEConfigHub(self.app_config).file_event_handler,
                "deleted",
                file_path,
            )

    def _handle_event(self, event, event_type):
        """
        Internal handler to debounce duplicate events for the same file.

        :param event: File system event object
        :param event_type: Type of event ("created" or "modified")
        """
        file_path = str(event.src_path)
        # Ignore events for directories or invalid files
        if event.is_directory or not self._is_valid_config_file(file_path):
            return

        # Debounce logic, ignore events occurring within debounce_interval
        # If 2 events for the same file occur within debounce_interval,
        # only process the first one
        now = time.time()
        last_time = self._last_event_time.get(file_path, 0)
        if now - last_time < self.debounce_interval:
            logger.debug(f"Debounced duplicate {event_type} event for: {file_path}")
            return

        # Update last event time
        self._last_event_time[file_path] = now

        # Log and process the event
        logger.info(f"Submitting {event_type} event for processing: {file_path}")
        executor.submit(
            TIMEConfigHub(self.app_config).file_event_handler,
            event_type,
            file_path,
        )
