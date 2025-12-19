"""
Time Config Hub Service Module

This module provides core service logic for the Time Config Hub,
including service orchestration, configuration management,
and integration with other TSN components.
"""

import logging
import os
import time

from watchdog.observers import Observer

from time_config_hub.config_reader import load_app_config
from time_config_hub.logging_setup import setup_logging

from .watch_handler import WatchHandler

logger = logging.getLogger("tch")


class Service:
    """
    Service class for managing Time Config Hub lifecycle.

    This class encapsulates the logic for monitoring configured directories for changes,
    handling automatic directory creation, and managing the observer thread
    for file system events.
    """

    def __init__(self, app_config: dict):
        """
        Initialize the Service instance.

        :param dict app_config: Application configuration dictionary.
        """
        self.app_config = app_config
        self.observer = Observer()

    def start(self):
        """
        Start the Time Config Hub service.

        Schedules the WatchHandler for each configured listening folder and
        starts the observer.

        :raises OSError: If a directory cannot be created.
        :raises Exception: If scheduling a handler fails.
        """
        logger.debug("[daemon] Starting service...")

        handler = WatchHandler(self.app_config)
        paths = self.app_config.get("General", {}).get("ListeningFolder", [])
        auto_create_dir = self.app_config.get("General", {}).get(
            "AutoCreateListeningFolder", False
        )

        for path in paths:
            # Check if path exists
            if not os.path.exists(path):
                if auto_create_dir:
                    try:
                        os.makedirs(path, exist_ok=True)
                        logger.info(f"[daemon] Created missing directory: {path}")

                    except Exception:
                        logger.exception(f"[daemon] Failed to create directory: {path}")
                        continue  # Skip scheduling if creation fails
                else:
                    logger.error(f"[daemon] Path does not exist: {path}")
                    continue  # Skip scheduling if path doesn't exist

            try:
                self.observer.schedule(handler, path, recursive=False)
                logger.info(f"[daemon] Watching {path}")

            except Exception:
                logger.exception(f"[daemon] Unexpected error watching: {path}")
                raise

        self.observer.start()
        logger.debug("[daemon] Service started successfully")

    def run_forever(self):
        """
        Run the service loop indefinitely.

        Keeps the service running until interrupted.
        Handles graceful shutdown on KeyboardInterrupt and logs unexpected errors.

        :raises KeyboardInterrupt: If interrupted by user.
        :raises Exception: For unexpected runtime errors.
        """
        logger.debug("[daemon] Running service loop...")
        try:
            while True:
                time.sleep(1)

        except KeyboardInterrupt:
            logger.debug("[daemon] KeyboardInterrupt received, stopping service.")
            self.observer.stop()

        except Exception:
            logger.exception("[daemon] Unexpected error in run_forever")
            self.observer.stop()

        self.observer.join()
        logger.debug("[daemon] Service exited run loop.")

    def stop(self):
        """
        Stop the Time Config Hub service.

        Stops the observer and waits for its thread to finish.
        """
        logger.debug("[daemon] Stopping service...")
        self.observer.stop()
        self.observer.join()
        logger.debug("[daemon] Service stopped.")


def main():
    """
    Entry point for the Time Config Hub service.
    Any exceptions encountered during execution are logged as fatal errors.
    """
    try:
        app_config = load_app_config()
        setup_logging(app_config)
        service = Service(app_config)
        service.start()
        service.run_forever()

    except Exception:
        logger.exception("[daemon] Fatal error in service")


if __name__ == "__main__":
    main()
