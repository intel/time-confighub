# Time Config Hub

## Overview

The Time Config Hub provides a comprehensive tool for managing Time-Sensitive Networking (TSN) configurations on Intel TSN-capable hardware platforms. It includes both manual configuration management and automatic daemon functionality:

- **Manual Configuration**: Apply, validate, and manage TSN configurations
- **Daemon Mode**: Background monitoring for automatic configuration application

All functionality is available through the unified `tch` command-line interface.

Key features:
- Support for XML and YAML configuration formats
- Command-line interface with `tch` command
- Linux service for automatic configuration monitoring
- Configuration validation and dry-run mode
- Integration with Linux Traffic Control (TC) subsystem
- Network interface detection and validation
- Systemd service integration for production deployment

The Time Config Hub is designed to run on end stations equipped with TSN-capable hardware such as Intel i226 network cards.

## Requirements

### Hardware Support
- Intel i226 TSN-capable network cards
- Other Intel TSN-enabled hardware platforms

### Software Requirements
- Python 3.9 or higher
- Linux operating system (Ubuntu recommended)
- Root privileges for applying configurations
- Network interfaces with TSN capabilities
- Bash shell (for TSN Reference Software compatibility)
- systemd (for daemon mode)

## Installation

### Quick Install (Recommended)

```bash
cd <repo-root>
chmod +x install.sh
sudo ./install.sh
```

This script will:
- Install the Python package and all dependencies into a dedicated virtual environment
- Create a fixed venv at `/opt/tch/venv` (used by systemd)
- Create necessary directory structure:
  - `/etc/tch/app_config/` - Application configuration files
  - `/etc/tch/tsn_configs/` - TSN traffic configuration files (configurable via tch_app.conf)
  - `/var/log/tch/` - Application logs (configurable via tch_app.conf)
- Set up the `tch` command-line tool via a stable symlink: `/usr/local/bin/tch` → `/opt/tch/venv/bin/tch`
- Install systemd service file (`tch.service`) for daemon service
- Configure appropriate file permissions and ownership

### Uninstallation

To completely remove Time Config Hub:

```bash
cd <repo-root>
chmod +x uninstall.sh
sudo ./uninstall.sh
```

**Uninstall Options:**
- `./uninstall.sh --help` - Show help and available options
- `sudo ./uninstall.sh --force` - Skip confirmation prompts (automated uninstall)

The uninstall script will:
- Stop and disable the TSN daemon service
- Remove the virtual environment (`/opt/tch/`) and command-line symlink (`/usr/local/bin/tch`)
- Remove all application directories and configuration files
- Remove systemd service files



## Usage

### Command Line Interface

The `tch` command provides the main interface:

```bash
# Check version and installation
tch --version

# Apply configuration (dry run to validate)
tch apply config.yaml --interface eth0 --dry-run

# Apply configuration (requires root privileges)
sudo tch apply config.yaml --interface eth0

# Get current config status
tch status --interface eth0 --format json

# Reset TSN configuration
sudo tch reset --interface eth0

# Validate configuration file
tch validate config.yaml  # Note: Not yet implemented
```

#### Daemon Commands

```bash
# Check daemon status
tch daemon-status

# Control systemd daemon service
sudo tch daemon-start
sudo tch daemon-stop  
sudo tch daemon-restart
```

#### Available Commands Summary

| Command | Description |
|---------|-------------|
| `apply <config_file>` | Apply TSN configuration from XML/YAML file |
| `status [--interface]` | Show current config status |
| `reset [--interface]` | Reset TSN configuration |
| `daemon-status` | Show daemon status information |
| `daemon-start` | Start systemd daemon service |
| `daemon-stop` | Stop systemd daemon service |
| `daemon-restart` | Restart systemd daemon service |
| `validate <config_file>` | Validate configuration file format *(not yet implemented)* |
| `config-show` | Show current CLI configuration |

### Configuration Files

Time Config Hub supports both XML and YAML formats. 


#### TODO: Example YAML Configuration:


### Programmatic API

```python
from time_config_hub import TIMEConfigHub

# Initialize hub
config_hub = TIMEConfigHub()

# Apply configuration
success = config_hub.apply_config("config.yaml", interface="eth0")

# Get status
status = config_hub.get_status(interface="eth0")
print(f"Current config status: {status}")
```

### Functional Test Example
For detailed instructions and sample configuration files, see 
[examples/scenario_1](examples/scenario_1).


## Runtime Directories

After installation, the following system directories are created and used:

### Application Directories (Fixed Locations)
- `/etc/tch/app_config/` - Application configuration files (tch_app.conf)

### TSN Configuration Directories (Configurable)
These directories are configurable via the `tch_app.conf` file:
- **ConfigDirectory** (default: `/etc/tch/tsn_configs/`) - TSN traffic configuration files
- **LogDirectory** (default: `/var/log/tch/`) - Application logs

### Directory Configuration
The locations of ConfigDirectory and LogDirectory are read from:
`/etc/tch/app_config/tch_app.conf`

Example configuration:
```properties
General:
    Verbosity: true
    LogDirectory: /var/log/tch
    LogLevel: DEBUG
    ConfigDirectory: /etc/tch/tsn_configs
```

## Documentation

For technical and development information:
- [PACKAGE_STRUCTURE.md](PACKAGE_STRUCTURE.md) - Developer documentation and package details
- Configuration examples in the repository
- Inline code documentation

## Troubleshooting

**Command `tch` not found after installation**
- Verify the stable CLI symlink exists: `ls -l /usr/local/bin/tch`
- Verify the venv CLI works: `/opt/tch/venv/bin/tch --version`
- Verify the package inside the venv: `sudo /opt/tch/venv/bin/python -m pip show time_config_hub`
- If `/usr/local/bin` is not in `PATH`, add it or invoke `/opt/tch/venv/bin/tch` directly

**Permission denied when applying configurations**
- TSN configuration requires root privileges: `sudo tch apply ...`

**Interface not found error**
- Verify the network interface exists: `ip link show`
- Ensure the interface supports TSN features: `tch status --interface <interface>`

**Configuration parsing errors**
- Validate your XML/YAML files: `tch validate config.yaml`
- Use dry-run mode before applying: `tch apply config.yaml --dry-run`
- Check the configuration format matches the expected schema

**Daemon not responding**
- Check daemon status: `tch daemon-status`
- Verify daemon configuration: `tch config-show`
- Check systemd service: `sudo systemctl status tch.service`

## Disclaimer

* This project demonstrates TSN functionality on supported platforms
* Not intended for production use
* Intended for specific platforms and BSP - other HW/SW combinations YMMV
* Users are responsible for their own products' functionality and performance

## License

Refer to [LICENSE](LICENSE)

## Support

For issues and questions:
1. Check the troubleshooting section above
2. Review the documentation and examples in [PACKAGE_STRUCTURE.md](PACKAGE_STRUCTURE.md)
3. File issues in the project repository
4. Ensure you're using supported hardware (Intel i226 or compatible TSN cards)

## Disclaimer
This project is under development. All source code and features on the main
branch are for the purpose of testing or evaluation and not production ready.

