#!/bin/bash

# Installation script for Time Config Hub

set -e

echo "Installing Time Config Hub..."

# Fixed venv location (systemd will use this Python)
readonly APP_VENV_BASE_DIR="/opt/tch"
readonly VENV_DIR="${APP_VENV_BASE_DIR}/venv"

readonly TCH_SYMLINK_PATH="/usr/local/bin/tch"

readonly APP_INSTALL_DIR="/etc/tch"
readonly APP_CONFIG_SUBDIR_NAME="app_config"
readonly APP_CONFIG_DIR="${APP_INSTALL_DIR}/${APP_CONFIG_SUBDIR_NAME}"

readonly DEFAULT_CONFIG_DIR="${APP_INSTALL_DIR}/tsn_configs"
readonly DEFAULT_LOG_DIR="/var/log/tch"

readonly PROJECT_CONFIG_FILE="conf/tch_app.conf"

readonly SYSTEMD_SERVICE_TEMPLATE="src/time_config_hub/templates/tch.service"
readonly SYSTEMD_SERVICE_DEST="/etc/systemd/system/tch.service"

readonly BUILD_DIR="build"
readonly DIST_DIR="dist"
readonly EGG_INFO_GLOB_APP="src/time_config_hub/*.egg-info"
readonly EGG_INFO_GLOB_SRC="src/*.egg-info"

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
        echo "Error: This installation requires root privileges"
        echo "Please run with sudo: sudo ./install.sh"
        exit 1
    fi
}

# Function to validate project directory structure
validate_project_structure() {
    echo "Validating project structure..."
    
    if [[ ! -f "pyproject.toml" ]] || [[ ! -d "src/time_config_hub" ]]; then
        echo "Error: Please run this script from the project root directory"
        echo "Expected directory structure:"
        echo "  ."
        echo "  ├── pyproject.toml"
        echo "  ├── src/time_config_hub/"
        echo "  └── conf/"
        exit 1
    fi
    
    echo "✓ Project structure validated"
}

# Function to create directory structure
create_directory_structure() {
    echo "Creating directory structure..."
    
    mkdir -p "${APP_CONFIG_DIR}"          # Application config files
    mkdir -p "${CONFIG_DIR}"              # TSN traffic configuration files
    mkdir -p "${LOG_DIR}"                 # Application logs
    mkdir -p "${APP_VENV_BASE_DIR}"       # Python virtual environment base
    
    echo "✓ Directory structure created:"
    echo "  - Application config: ${APP_CONFIG_DIR}"
    echo "  - TSN config: ${CONFIG_DIR}"
    echo "  - Logs: ${LOG_DIR}"
    echo "  - Python venv base: ${APP_VENV_BASE_DIR}"
}

# Function to create Python virtual environment
create_python_venv() {
    echo "Creating Python virtual environment..."

    if ! command -v python3 &> /dev/null; then
        echo "Error: python3 not found. Please install Python 3 first."
        exit 1
    fi

    if [[ -x "${VENV_DIR}/bin/python" ]]; then
        echo "✓ Virtual environment already exists: ${VENV_DIR}"
        return
    fi

    # python3 -m venv may fail if python3-venv isn't installed on Debian/Ubuntu
    if ! python3 -m venv "${VENV_DIR}"; then
        echo "Error: Failed to create virtual environment at ${VENV_DIR}"
        echo "On Debian/Ubuntu you likely need: apt install python3-venv"
        exit 1
    fi

    echo "✓ Virtual environment created: ${VENV_DIR}"
}

# Function to copy configuration files
copy_configuration_files() {
    echo "Copying application configuration files..."
    
    if [[ -d "conf" ]]; then
        cp conf/*.conf "${APP_CONFIG_DIR}/" 2>/dev/null || true
        echo "✓ Application config files copied to ${APP_CONFIG_DIR}/"
    else
        echo "Warning: conf/ directory not found, no config files to copy"
    fi
}

# Function to install Python package
install_python_package() {
    echo "Installing Python package and dependencies..."

    create_python_venv

    # Install build tooling inside the venv (avoids PEP 668 externally-managed-environment)
    "${VENV_DIR}/bin/python" -m pip install --upgrade pip
    "${VENV_DIR}/bin/python" -m pip install --upgrade build

    # Build wheel from project and install it into the venv
    "${VENV_DIR}/bin/python" -m build
    "${VENV_DIR}/bin/python" -m pip install --upgrade dist/*.whl

    # Expose a stable CLI path for users
    mkdir -p "$(dirname "${TCH_SYMLINK_PATH}")"
    ln -sf "${VENV_DIR}/bin/tch" "${TCH_SYMLINK_PATH}"

    # Remove build artifacts
    rm -rf "${BUILD_DIR}" "${DIST_DIR}" ${EGG_INFO_GLOB_APP} ${EGG_INFO_GLOB_SRC}
    
    echo "✓ Python package installed successfully"
}

# Function to install systemd service
install_systemd_service() {
    echo "Installing systemd service file..."
    
    # Prefer the packaged template source of truth
    if [[ -f "${SYSTEMD_SERVICE_TEMPLATE}" ]]; then
        cp "${SYSTEMD_SERVICE_TEMPLATE}" "${SYSTEMD_SERVICE_DEST}"
        systemctl daemon-reload
        echo "✓ Systemd service file installed: ${SYSTEMD_SERVICE_DEST}"
        echo "  Service uses venv python: ${VENV_DIR}/bin/python"
    else
        echo "Note: Systemd service file not found. Service file can be generated later."
    fi
}

# Function to set file permissions
set_permissions() {
    echo "Setting permissions..."
    
    # TODO: Might need to revisit if we want root to be owner. we could create a tsnadmin group
    # but a discussion for future.
    chown -R root:root "${APP_INSTALL_DIR}"
    chmod 755 "${APP_INSTALL_DIR}"
    chmod 755 "${APP_CONFIG_DIR}"
    chmod -R 644 "${APP_CONFIG_DIR}"/*.conf 2>/dev/null || true

    # Set permissions for TSN config and log directories
    chown -R root:root "${CONFIG_DIR}"
    chmod 755 "${CONFIG_DIR}"
    chown -R root:root "${LOG_DIR}"
    chmod 755 "${LOG_DIR}"

    # Set permissions for venv base directory
    chown -R root:root "${APP_VENV_BASE_DIR}"
    chmod 755 "${APP_VENV_BASE_DIR}"
    
    echo "✓ Permissions set successfully"
}

# Function to verify installation
verify_installation() {
    echo "Verifying installation..."
    
    local all_ok=true
    
    # Check CLI command
    if command -v tch &> /dev/null; then
        echo "✓ Time Config Hub CLI installed successfully!"
        tch --version
    else
        echo "✗ Installation failed. tch command not found."
        echo "  Expected symlink: ${TCH_SYMLINK_PATH} -> ${VENV_DIR}/bin/tch"
        all_ok=false
    fi
    
    if [ "$all_ok" = true ]; then
        echo "✓ Available CLI commands:"
        tch --help
    else
        echo "✗ Installation verification failed."
        exit 1
    fi
}

# Main installation function
main() {
    echo "================================================"
    echo "Time Config Hub Installation Script"
    echo "================================================"
    echo ""
    
    # Perform installation steps
    validate_project_structure
    echo ""
    
    check_root
    echo ""
    
    create_directory_structure
    echo ""
    
    copy_configuration_files
    echo ""
    
    install_python_package
    echo ""
    
    install_systemd_service
    echo ""
    
    set_permissions
    echo ""
    
    verify_installation
    echo ""
    
    echo "================================================"
    echo "✓ Time Config Hub installation completed!"
    echo "================================================"
    
    # Explicitly return success
    exit 0
}

# Handle script arguments
case "${1:-}" in
    --help|-h)
        echo "Usage: $0 [OPTIONS]"
        echo ""
        echo "Install Time Config Hub and all its components."
        echo ""
        echo "Options:"
        echo "  --help, -h    Show this help message"
        echo ""
        echo "This script should be run from the project root directory."
        exit 0
        ;;
    "")
        # Normal installation mode
        ;;
    *)
        echo "Unknown option: $1"
        echo "Use --help for usage information"
        exit 1
        ;;
esac

# Read directories from project tch_app.conf for TSN traffic configs and logs
CONFIG_DIR="${DEFAULT_CONFIG_DIR}"  # TSN traffic configuration files
LOG_DIR="${DEFAULT_LOG_DIR}"

if [[ -f "${PROJECT_CONFIG_FILE}" ]]; then
    echo "Reading configuration from ${PROJECT_CONFIG_FILE}..."
    CONFIG_DIR=$(parse_config_value "${PROJECT_CONFIG_FILE}" "ConfigDirectory" "${DEFAULT_CONFIG_DIR}")
    LOG_DIR=$(parse_config_value "${PROJECT_CONFIG_FILE}" "LogDirectory" "${DEFAULT_LOG_DIR}")
    echo "ConfigDirectory (for traffic configs): $CONFIG_DIR"
    echo "LogDirectory: $LOG_DIR"
else
    echo "Configuration file ${PROJECT_CONFIG_FILE} not found, using default directories"
fi

# Run main function
main
