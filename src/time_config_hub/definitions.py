from pathlib import Path

APP_CONFIG_DIR = Path("/etc/tch/app_config")
TCH_APP_CONFIG_FILE = APP_CONFIG_DIR / "tch_app.conf"
TCH_DAEMON_SERVICE_FILE = Path("/etc/systemd/system/tch.service")
