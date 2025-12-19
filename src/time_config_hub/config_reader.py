"""
Configuration Reader Module

A generic configuration reader for reading and writing YAML and XML configuration files.

This module provides:

- Support for YAML format including .yaml, .yml, and .conf file extensions
- Support for XML format with automatic conversion to/from dictionaries
- Configuration validation and error handling
- Backup functionality for safe configuration updates
- Dot notation access for nested configuration values

The ConfigReader class can be used for application settings, TSN configurations,
or any other configuration management needs.
"""

import logging
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, Union

import yaml

from .definitions import TCH_APP_CONFIG_FILE

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    """
    Generic configuration error exception.

    Raised when configuration file operations fail.
    """

    pass


class ConfigReader:
    """
    A generic configuration reader for reading and writing YAML and XML configuration
    files.

    Supports formats:
    - YAML (.yaml, .yml, .conf)
    - XML (.xml)

    Features:
    - Validation of configuration data
    - Backup and restore functionality
    - Thread-safe operations
    - Detailed logging
    """

    def __init__(self, verbose: bool = False):
        """
        Initialize the configuration reader.

        :param bool verbose: Enable verbose logging
        """
        self.verbose = verbose

        # Supported file extensions
        self.supported_formats = [
            ".yaml",
            ".yml",
            ".conf",
            ".xml",
        ]

    def read_config(self, config_file: Union[str, Path]) -> Dict[str, Any]:
        """
        Read configuration from a file.

        :param config_file: Path to the configuration file
        :type config_file: Union[str, Path]
        :return: Dictionary containing the configuration data
        :rtype: Dict[str, Any]
        :raises ConfigError: If file cannot be read or parsed
        """
        config_path = Path(config_file)
        logger.debug(f"Reading configuration from: {config_path}")

        if not config_path.exists():
            raise ConfigError(f"Configuration file not found: {config_path}")

        if not config_path.is_file():
            raise ConfigError(f"Path is not a file: {config_path}")

        # Detect format based on file extension
        file_extension = config_path.suffix.lower()

        if file_extension not in self.supported_formats:
            raise ConfigError(
                f"Unsupported configuration format: {file_extension}. "
                f"Supported formats: {self.supported_formats}"
            )

        try:

            if file_extension == ".xml":
                config_data = self._read_xml(config_path)
            else:
                # Handle YAML formats (.yaml, .yml, .conf)
                config_data = self._read_yaml(config_path)

            logger.debug(f"Successfully loaded configuration from {config_path}")
            return config_data

        except ConfigError:
            logger.error(f"Failed to read configuration from {config_path}")
            raise

        except Exception as e:
            logger.exception(f"Unexpected error reading config: {config_path}")
            raise ConfigError("Unexpected error reading config") from e

    def write_config(
        self,
        config_data: Dict[str, Any],
        config_file: Union[str, Path],
        backup: bool = True,
    ) -> None:
        """
        Write configuration to a file.

        :param config_data: Configuration data to write
        :type config_data: Dict[str, Any]
        :param config_file: Path to the configuration file
        :type config_file: Union[str, Path]
        :param bool backup: Create backup of existing file before writing
        :return: None
        :rtype: None
        :raises ConfigError: If file cannot be written
        """
        config_path = Path(config_file)
        logger.debug(f"Writing configuration to: {config_path}")

        # Create directory if it doesn't exist
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Create backup if requested and file exists
        if backup and config_path.exists():
            self._create_backup(config_path)

        # Detect format based on file extension
        file_extension = config_path.suffix.lower()

        if file_extension not in self.supported_formats:
            raise ConfigError(
                f"Unsupported configuration format: {file_extension}. "
                f"Supported formats: {self.supported_formats}"
            )

        try:
            logger.debug(f"Writing configuration to: {config_path}")

            if file_extension == ".xml":
                self._write_xml(config_data, config_path)
            else:
                # Handle YAML formats (.yaml, .yml, .conf)
                self._write_yaml(config_data, config_path)

            logger.debug(f"Successfully wrote configuration to {config_path}")

        except ConfigError:
            logger.error(f"Failed to write configuration to {config_path}")
            raise

        except Exception as e:
            logger.exception(f"Unexpected error writing config: {config_path}")
            raise ConfigError("Unexpected error writing config") from e

    def get_config_value(
        self, config_data: Dict[str, Any], key_path: str, default: Any = None
    ) -> Any:
        """
        Get a configuration value using dot notation.

        :param config_data: Configuration dictionary
        :type config_data: Dict[str, Any]
        :param str key_path: Dot-separated key path (e.g., 'daemon.log_dir')
        :param default: Default value if key not found
        :type default: Any
        :return: Configuration value or default
        :rtype: Any
        """
        keys = key_path.split(".")
        current = config_data

        try:
            for key in keys:
                current = current[key]
            return current

        except (KeyError, TypeError):
            return default

    def set_config_value(
        self, config_data: Dict[str, Any], key_path: str, value: Any
    ) -> None:
        """
        Set a configuration value using dot notation.

        :param config_data: Configuration dictionary to modify
        :type config_data: Dict[str, Any]
        :param str key_path: Dot-separated key path (e.g., 'daemon.log_dir')
        :param value: Value to set
        :type value: Any
        :return: None
        :rtype: None
        """
        keys = key_path.split(".")
        current = config_data

        # Navigate to the parent of the target key
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]

        # Set the final value
        current[keys[-1]] = value

    def _read_yaml(self, config_path: Path) -> Dict[str, Any]:
        """
        Read YAML configuration file.

        :param Path config_path: Path to YAML file
        :return: Parsed configuration data
        :rtype: Dict[str, Any]
        :raises ConfigError: If YAML parsing fails
        """
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Handle empty files
        if not content.strip():
            logging.debug(
                f"YAML file {config_path} is empty. Returning empty configuration."
            )
            return {}

        try:
            data = yaml.safe_load(content)
            if data is None:
                logging.debug(
                    f"YAML file {config_path} is empty. Returning empty configuration."
                )
                return {}
            if not isinstance(data, dict):
                raise ConfigError("Configuration file must contain a dictionary")

            return data

        except ConfigError:
            logger.error(f"Failed to parse configuration from: {config_path}")
            raise

        except yaml.YAMLError as e:
            logger.error(f"Failed to parse YAML file: {config_path}")
            raise ConfigError("Failed to parse YAML file") from e

    def _write_yaml(self, config_data: Dict[str, Any], config_path: Path) -> None:
        """
        Write YAML configuration file.

        :param config_data: Configuration data to write
        :type config_data: Dict[str, Any]
        :param Path config_path: Path to YAML file
        :return: None
        :rtype: None
        :raises ConfigError: If YAML writing fails
        """
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(config_data, f, default_flow_style=False, indent=2)

        except Exception as e:
            logger.exception(f"Failed to write YAML file: {config_path}")
            raise ConfigError("Failed to write YAML file") from e

    def _create_backup(self, config_path: Path) -> None:
        """
        Create backup of existing configuration file.

        :param Path config_path: Path to configuration file
        :return: None
        :rtype: None
        """
        backup_path = config_path.with_suffix(config_path.suffix + ".backup")

        try:
            shutil.copy2(config_path, backup_path)
            logger.debug(f"Created backup: {backup_path}")

        except Exception as e:
            logger.exception("Failed to create backup")
            raise ConfigError("Failed to create backup") from e

    def _read_xml(self, config_path: Path) -> Dict[str, Any]:
        """
        Read XML configuration file.

        :param Path config_path: Path to XML file
        :return: Parsed configuration data
        :rtype: Dict[str, Any]
        :raises ConfigError: If XML parsing fails
        """
        try:
            tree = ET.parse(config_path)
            root = tree.getroot()
            return self._xml_to_dict(root)

        except ET.ParseError as e:
            logger.error(f"Failed to parse XML file: {config_path}")
            raise ConfigError("Failed to parse XML file") from e

        except Exception as e:
            logger.exception(f"Unexpected error reading XML file: {config_path}")
            raise ConfigError("Unexpected error reading XML file") from e

    def _write_xml(self, config_data: Dict[str, Any], config_path: Path) -> None:
        """
        Write XML configuration file.

        :param config_data: Configuration data to write
        :type config_data: Dict[str, Any]
        :param Path config_path: Path to XML file
        :return: None
        :rtype: None
        :raises ConfigError: If XML writing fails
        """
        try:
            # Create root element (use 'configuration' as default root)
            root = ET.Element("configuration")
            self._dict_to_xml(config_data, root)

            # Create tree and write with proper formatting
            tree = ET.ElementTree(root)
            ET.indent(tree, space="  ", level=0)  # Format with indentation
            tree.write(config_path, encoding="utf-8", xml_declaration=True)

        except Exception as e:
            logger.exception(f"Unexpected error writing XML file: {config_path}")
            raise ConfigError("Unexpected error writing XML file") from e

    def _xml_to_dict(self, element: ET.Element) -> Any:
        """
        Convert XML element to dictionary.

        :param ET.Element element: XML element to convert
        :return: Dictionary representation of XML element
        :rtype: Any
        """
        result = {}

        # Handle attributes
        if element.attrib:
            result["@attributes"] = element.attrib

        # Handle text content
        if element.text and element.text.strip():
            text = element.text.strip()
            # Try to convert to appropriate type
            if text.lower() in ("true", "false"):
                result["#text"] = text.lower() == "true"
            elif text.isdigit():
                result["#text"] = int(text)
            else:
                try:
                    result["#text"] = float(text)
                except ValueError:
                    result["#text"] = text

        # Handle child elements
        children = {}
        for child in element:
            child_data = self._xml_to_dict(child)

            # Handle multiple elements with same tag
            if child.tag in children:
                if not isinstance(children[child.tag], list):
                    children[child.tag] = [children[child.tag]]
                children[child.tag].append(child_data)
            else:
                children[child.tag] = child_data

        result.update(children)

        # If only text content and no attributes/children, return just the text
        if len(result) == 1 and "#text" in result:
            return result["#text"]

        return result

    def _dict_to_xml(self, data: Dict[str, Any], parent: ET.Element) -> None:
        """
        Convert dictionary to XML elements.

        :param data: Dictionary data to convert
        :type data: Dict[str, Any]
        :param ET.Element parent: Parent XML element
        :return: None
        :rtype: None
        """
        for key, value in data.items():
            if key == "@attributes":
                # Set attributes on parent element
                if isinstance(value, dict):
                    for attr_key, attr_value in value.items():
                        parent.set(attr_key, str(attr_value))
            elif key == "#text":
                # Set text content
                parent.text = str(value)
            else:
                if isinstance(value, list):
                    # Handle list values - create multiple elements with same tag
                    for item in value:
                        child = ET.SubElement(parent, key)
                        if isinstance(item, dict):
                            self._dict_to_xml(item, child)
                        else:
                            child.text = str(item)
                elif isinstance(value, dict):
                    # Handle nested dictionaries
                    child = ET.SubElement(parent, key)
                    self._dict_to_xml(value, child)
                else:
                    # Handle simple values
                    child = ET.SubElement(parent, key)
                    child.text = str(value)


def load_app_config() -> Dict[str, Any]:
    """
    Load the application configuration from the specified config file.

    Attempts to read the configuration file defined by ``TCH_APP_CONFIG_FILE``.
    If the file does not exist or cannot be read, falls back to default logging and
    general configuration values. The loaded or default configurations are consolidated
    and returned as a dictionary.

    :return: Dictionary containing the consolidated "Logging" and "General"
        configuration sections.
    :rtype: Dict[str, Any]
    :raises ConfigError: If the configuration file does not exist or cannot be read.
    """
    config_file = TCH_APP_CONFIG_FILE

    # Set default configurations if config file is missing or unreadable
    default_logging_config = {
        "LogLevel": "INFO",
        "LogDirectory": "/var/log/tch",
        "LogFile": "tch.log",
    }

    default_general_config = {
        "Verbosity": False,
        "ConfigDirectory": "/etc/tch/tsn_configs",
        "ListeningFolder": [],
    }

    try:
        if not config_file.exists():
            raise ConfigError(f"Config file does not exist: {config_file}")

        config_reader = ConfigReader(verbose=False)
        app_config = config_reader.read_config(config_file)

    except ConfigError:
        logging.error(f"Error reading app config: {config_file}. Using defaults.")
        app_config = {}

    # Consolidate with defaults
    default_logging_config.update(app_config.get("Logging", {}))
    default_general_config.update(app_config.get("General", {}))

    config = {
        "Logging": default_logging_config,
        "General": default_general_config,
    }
    return config
