#!/bin/bash

# Uninstallation script for Time Config Hub

set -e

echo "Uninstalling Time Config Hub..."

# Fixed venv location
APP_VENV_BASE_DIR="/opt/tch"
VENV_DIR="${APP_VENV_BASE_DIR}/venv"
TCH_SYMLINK_PATH="/usr/local/bin/tch"

readonly SERVICE_NAME="tch"
readonly SERVICE_UNIT_NAME="${SERVICE_NAME}.service"
readonly SYSTEMD_SERVICE_DEST="/etc/systemd/system/${SERVICE_UNIT_NAME}"

readonly APP_INSTALL_DIR="/etc/tch"
readonly APP_CONFIG_SUBDIR_NAME="app_config"
readonly APP_CONFIG_DIR="${APP_INSTALL_DIR}/${APP_CONFIG_SUBDIR_NAME}"
readonly INSTALLED_CONFIG_FILENAME="tch_app.conf"
readonly INSTALLED_CONFIG_FILE="${APP_CONFIG_DIR}/${INSTALLED_CONFIG_FILENAME}"

# Default directories (used as fallbacks and for legacy cleanup)
DEFAULT_CONFIG_DIR="/etc/tch/tsn_configs"
DEFAULT_LOG_DIR="/var/log/tch"

# Safety wrapper around rm -rf for directory paths
safe_remove_dir() {
    local dir_path="$1"
    local label="$2"

    if [[ -z "${dir_path}" ]] || [[ "${dir_path}" == "/" ]]; then
        echo "  ! Refusing to remove unsafe ${label} path: '${dir_path}'"
        return 1
    fi

    if [[ "${dir_path}" != /* ]]; then
        echo "  ! Refusing to remove non-absolute ${label} path: ${dir_path}"
        return 1
    fi

    if [[ -d "${dir_path}" ]]; then
        echo "  - Removing ${label}: ${dir_path}"
        rm -rf "${dir_path}"
        echo "    ✓ ${label} removed"
    else
        echo "  - ${label} not found: ${dir_path}"
    fi
}

# Function to parse configuration values from tch_app.conf
parse_config_value() {
    local config_file="$1"
    local key="$2"
    local default_value="$3"
    
    if [[ -f "$config_file" ]]; then
        # Extract value using grep and sed, handling spaces around the colon
        local value=$(grep -E "^\s*${key}\s*:" "$config_file" | sed -E "s/^\s*${key}\s*:\s*//" | xargs)
        if [[ -n "$value" ]]; then
            echo "$value"
        else
            echo "$default_value"
        fi
    else
        echo "$default_value"
    fi
}

# Function to check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        echo "Error: This uninstallation requires root privileges"
        echo "Please run with sudo: sudo ./uninstall.sh"
        exit 1
    fi
}

# Function to stop and disable daemon service
stop_daemon() {
    echo "Stopping and disabling TSN daemon service..."
    
    # Stop daemon if running
    if systemctl is-active --quiet "${SERVICE_UNIT_NAME}" 2>/dev/null; then
        echo "  - Stopping ${SERVICE_UNIT_NAME}..."
        systemctl stop "${SERVICE_UNIT_NAME}"
        echo "    ✓ Service stopped"
    else
        echo "  - Service not running"
    fi
    
    # Disable daemon if enabled
    if systemctl is-enabled --quiet "${SERVICE_UNIT_NAME}" 2>/dev/null; then
        echo "  - Disabling ${SERVICE_UNIT_NAME}..."
        systemctl disable "${SERVICE_UNIT_NAME}"
        echo "    ✓ Service disabled"
    else
        echo "  - Service not enabled"
    fi
}

# Function to remove systemd service file
remove_systemd_service() {
    echo "Removing systemd service file..."
    
    if [[ -f "${SYSTEMD_SERVICE_DEST}" ]]; then
        rm -f "${SYSTEMD_SERVICE_DEST}"
        systemctl daemon-reload
        echo "  ✓ Removed systemd service file"
    else
        echo "  - Systemd service file not found"
    fi
}

# Function to remove Python package
remove_python_package() {
    echo "Removing Python package..."

    # Removing the venv is the cleanest uninstall (and avoids touching system Python).
    if [[ -d "${APP_VENV_BASE_DIR}" ]]; then
        echo "  - Detected Option A venv installation at: ${APP_VENV_BASE_DIR}"
        echo "    (venv removal will also remove the Python package)"
        return 0
    fi

    # Try to find and remove the package
    local package_removed=false
    
    # List of possible package names to try
    local package_names=(
        "time_config_hub"
    )

    # Check pip3 first
    if command -v pip3 &> /dev/null; then
        for package_name in "${package_names[@]}"; do
            if pip3 show "$package_name" >/dev/null 2>&1; then
                echo "  - Found package: $package_name"
                pip3 uninstall -y "$package_name" --break-system-packages
                echo "  ✓ Removed package via pip3: $package_name"
                package_removed=true
                break
            fi
        done
    fi

    # Try pip if pip3 didn't work
    if [[ "$package_removed" == false ]] && command -v pip &> /dev/null; then
        for package_name in "${package_names[@]}"; do
            if pip show "$package_name" >/dev/null 2>&1; then
                echo "  - Found package: $package_name"
                pip uninstall -y "$package_name" --break-system-packages
                echo "  ✓ Removed package via pip: $package_name"
                package_removed=true
                break
            fi
        done
    fi

    # Try to remove the command directly if package removal didn't work
    if [[ "$package_removed" == false ]]; then     
        # Remove CLI command
        if [[ -e "${TCH_SYMLINK_PATH}" ]]; then
            echo "  - Package not found via pip, removing CLI command directly"
            rm -f "${TCH_SYMLINK_PATH}"
            echo "  ✓ Removed command: ${TCH_SYMLINK_PATH}"
        fi
        
        package_removed=true
    fi

    if [[ "$package_removed" == false ]]; then
        echo "  ! Package not found in pip/pip3 and no command file found"
    fi
}

# Function to remove virtual environment and symlink
remove_virtualenv_installation() {
    echo "Removing virtual environment installation..."

    # Remove stable CLI symlink (created by install.sh)
    if [[ -e "${TCH_SYMLINK_PATH}" ]]; then
        echo "  - Removing CLI symlink: ${TCH_SYMLINK_PATH}"
        rm -f "${TCH_SYMLINK_PATH}"
        echo "    ✓ CLI symlink removed"
    else
        echo "  - CLI symlink not found: ${TCH_SYMLINK_PATH}"
    fi

    # Remove venv base directory
    if [[ -d "${APP_VENV_BASE_DIR}" ]]; then
        safe_remove_dir "${APP_VENV_BASE_DIR}" "Venv base directory"
    else
        echo "  - Venv base directory not found: ${APP_VENV_BASE_DIR}"
    fi
}

# Function to remove TSN directories (Log Directory and Config Directory from tch_app.conf)
remove_tsn_directories() {
    echo "Removing TSN directories from configuration..."
    
    # Remove ConfigDirectory (from installed config)
    safe_remove_dir "${CONFIG_DIR}" "ConfigDirectory"

    # Also remove the default config dir if it differs (legacy cleanup)
    if [[ "${DEFAULT_CONFIG_DIR}" != "${CONFIG_DIR}" ]]; then
        safe_remove_dir "${DEFAULT_CONFIG_DIR}" "Default ConfigDirectory"
    fi
    
    # Remove LogDirectory
    safe_remove_dir "${LOG_DIR}" "LogDirectory"
}

# Function to remove application directory
remove_application_directory() {
    echo "Removing application directory..."
    
    # Remove the entire application installation directory
    if [[ -d "${APP_INSTALL_DIR}" ]]; then
        echo "  (includes all application files and subdirectories)"
        safe_remove_dir "${APP_INSTALL_DIR}" "Application directory"
    else
        echo "  - Application directory not found: ${APP_INSTALL_DIR}"
    fi
}

# Function to verify uninstallation
verify_uninstallation() {
    echo "Verifying uninstallation..."
    
    local issues_found=false
    
    # Check if CLI command still exists
    if command -v tch &> /dev/null; then
        echo "  ! tch command still found in PATH"
        echo "    Location: $(which tch)"
        echo "    You may need to restart your shell or manually remove it"
        issues_found=true
    else
        echo "  ✓ tch command not found in PATH"
    fi

    # Check for remaining Option A venv
    if [[ -d "${APP_VENV_BASE_DIR}" ]]; then
        echo "  ! Venv base directory still exists: ${APP_VENV_BASE_DIR}"
        issues_found=true
    else
        echo "  ✓ Venv base directory removed: ${APP_VENV_BASE_DIR}"
    fi
    
    # Check for remaining application directory
    if [[ -d "${APP_INSTALL_DIR}" ]]; then
        echo "  ! Application directory still exists: ${APP_INSTALL_DIR}"
        if [[ -d "${APP_CONFIG_DIR}" ]]; then
            echo "    - Subdirectory: ${APP_CONFIG_DIR}"
        fi
        issues_found=true
    else
        echo "  ✓ Application directory removed: ${APP_INSTALL_DIR}"
    fi

    # Check for remaining config directory
    if [[ -d "$CONFIG_DIR" ]]; then
        echo "  ! ConfigDirectory still exists: ${CONFIG_DIR}"
        issues_found=true
    else
        echo "  ✓ ConfigDirectory removed: ${CONFIG_DIR}"
    fi

    # Check for remaining default config directory (legacy cleanup)
    if [[ "${DEFAULT_CONFIG_DIR}" != "${CONFIG_DIR}" ]]; then
        if [[ -d "${DEFAULT_CONFIG_DIR}" ]]; then
            echo "  ! Default ConfigDirectory still exists: ${DEFAULT_CONFIG_DIR}"
            issues_found=true
        else
            echo "  ✓ Default ConfigDirectory removed: ${DEFAULT_CONFIG_DIR}"
        fi
    fi

    # Check for remaining log directory
    if [[ -d "$LOG_DIR" ]]; then
        echo "  ! LogDirectory still exists: ${LOG_DIR}"
        issues_found=true
    else
        echo "  ✓ LogDirectory removed: ${LOG_DIR}"
    fi
    
    # Check for systemd service
    if [[ -f "${SYSTEMD_SERVICE_DEST}" ]]; then
        echo "  ! Systemd service file still exists: ${SYSTEMD_SERVICE_DEST}"
        issues_found=true
    else
        echo "  ✓ Systemd service file removed"
    fi
    
    if [[ "$issues_found" == false ]]; then
        echo "  ✓ Uninstallation appears complete"
        return 0
    else
        echo "  ! Some issues found - manual cleanup may be required"
        return 1
    fi
}

# Main uninstallation process
main() {
    echo "================================================"
    echo "Time Config Hub Uninstallation Script"
    echo "================================================"
    echo ""
    
    # Check if we need root privileges
    check_root

    echo "This will remove:"
    echo "  - Time Config Hub Python package"
    echo "  - Virtual environment base: ${APP_VENV_BASE_DIR}"
    echo "  - CLI symlink: ${TCH_SYMLINK_PATH}"
    echo "  - ConfigDirectory: ${CONFIG_DIR}"
    if [[ "${DEFAULT_CONFIG_DIR}" != "${CONFIG_DIR}" ]]; then
        echo "  - Default ConfigDirectory (legacy): ${DEFAULT_CONFIG_DIR}"
    fi
    echo "  - LogDirectory: ${LOG_DIR}"
    echo "  - Application directory: ${APP_INSTALL_DIR}"
    echo "    (includes application config files: tch_app.conf)"
    echo "  - Systemd service: ${SERVICE_NAME}"
    echo ""
    echo "Note: Directories are determined from the installed configuration file:"
    echo "      ${INSTALLED_CONFIG_FILE}"
    echo ""
    
    if [[ "${FORCE_MODE:-false}" != "true" ]]; then
        read -p "Are you sure you want to continue? [y/N]: " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "Uninstallation cancelled."
            exit 0
        fi
    else
        echo "Force mode: Proceeding without confirmation."
    fi
    
    echo ""
    echo "Starting uninstallation..."
    echo ""
    
    # Perform uninstallation steps
    stop_daemon
    echo ""
    
    remove_systemd_service
    echo ""

    remove_virtualenv_installation
    echo ""
    
    remove_python_package
    echo ""
    
    remove_tsn_directories
    echo ""
    
    remove_application_directory
    echo ""
    
    # Verify uninstallation and capture result
    if verify_uninstallation; then
        echo ""
        echo "================================================"
        echo "✓ Time Config Hub uninstallation completed!"
        echo "================================================"
        exit 0
    else
        echo ""
        echo "================================================"
        echo "✗ Time Config Hub uninstallation completed with issues!"
        echo "Please check the output above for remaining items that need manual cleanup."
        echo "================================================"
        exit 1
    fi
}

# Handle script arguments
case "${1:-}" in
    --help|-h)
        echo "Usage: $0 [OPTIONS]"
        echo ""
        echo "Uninstall Time Config Hub and all its components."
        echo ""
        echo "Options:"
        echo "  --help, -h    Show this help message"
        echo "  --force       Skip confirmation prompts (be careful!)"
        echo ""
        echo "This script requires root privileges (run with sudo)."
        exit 0
        ;;
    --force)
        # Skip confirmations for automated uninstall
        echo "Force mode enabled - skipping confirmations"
        FORCE_MODE=true
        ;;
    "")
        # Normal interactive mode
        ;;
    *)
        echo "Unknown option: $1"
        echo "Use --help for usage information"
        exit 1
        ;;
esac
# Read directories from the installed tch_app.conf to determine what to clean up
CONFIG_DIR="${DEFAULT_CONFIG_DIR}"  # TSN traffic configuration files
LOG_DIR="${DEFAULT_LOG_DIR}"

if [[ -f "${INSTALLED_CONFIG_FILE}" ]]; then
    echo "Reading configuration from ${INSTALLED_CONFIG_FILE}..."
    CONFIG_DIR=$(parse_config_value "${INSTALLED_CONFIG_FILE}" "ConfigDirectory" "${DEFAULT_CONFIG_DIR}")
    LOG_DIR=$(parse_config_value "${INSTALLED_CONFIG_FILE}" "LogDirectory" "${DEFAULT_LOG_DIR}")
    echo "ConfigDirectory (for traffic configs): $CONFIG_DIR"
    echo "LogDirectory: $LOG_DIR"
else
    echo "Installed configuration not found, using default directories"
fi

# Run main function
main
