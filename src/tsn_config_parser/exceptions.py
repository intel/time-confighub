"""Custom exceptions for tsn_config_parser parsing and validation."""


class UniversalParserError(Exception):
    """Raised when parsing or validation of TSN configuration data fails."""


class InvalidFileError(UniversalParserError):
    """Raised when the input data is invalid or malformed."""
