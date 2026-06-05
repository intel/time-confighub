[comment]: # (SPDX-FileCopyrightText: 2025 Intel Corporation)
[comment]: # (SPDX-License-Identifier: BSD-3-Clause)

# Time Config Hub Package Structure

This document provides technical information for developers and maintainers of the Time Config Hub Python package.

## Repository Structure

```
time-confighub/          # Time Config Hub (Python package)
    ├── setup.py                # Package setup configuration
    ├── install.sh              # Installation script
    ├── pyproject.toml          # Project metadata and dependencies
    ├── black_config.toml       # Black formatter configuration
    ├── LICENSE                  # BSD License
    ├── MANIFEST.in              # Package manifest for distribution
    ├── .gitignore              # Git ignore rules
    ├── README.md               # User documentation
    ├── PACKAGE_STRUCTURE.md    # Developer documentation (this file)
    ├── src/
    |   └── time_config_hub/     # Main Python package
    |       ├── __init__.py         # Package initialization
    |       ├── cli/                # CLI commands and exit codes
    |       ├── config/             # App config and logging setup
    |       ├── daemon/             # Filesystem watch and runtime daemon
    |       ├── infra/              # Linux/device command adapters
    |       ├── orchestrator/       # Service orchestration layer
    |       ├── services/           # TSN/TCC domain services
    |       ├── resources/          # YANG modules and resources
    |       ├── templates/          # Internal templates
    |       ├── utils/              # Shared utilities
    |       └── exceptions.py       # Custom exceptions
    ├── tests/
    ├── functionality_tests/
    └── docs/

```

## Development Setup

### Environment Preparation

```bash
# Clone and navigate to repository
git clone <repository-url>
cd time-confighub

# Install in development mode with dev dependencies
pip install -e .[dev]

# Verify installation
tch --version
```

### Testing

NOTE: pytest are work-in-progress now.
Below testing commands are not working.

```bash
# Run all tests
pytest tests/

# Run tests with coverage reporting
pytest --cov=time_config_hub tests/

# Run specific test files
pytest tests/time_config_hub/

# Generate HTML coverage report
pytest --cov=time_config_hub --cov-report=html tests/
```

### Code Quality

```bash
# Lint with Ruff
ruff check .

# Format code with Black
black --config black_config.toml .
```

## Package Distribution

### What Gets Installed

The Python package installation includes:
- **time_config_hub** Python module
- **tch** command-line tool entry point
- Production dependencies (PyYAML, lxml, click, netifaces)
- Package metadata and documentation

### What Stays in Repository

Development-only files not included in distribution:
- Test files and test data
- Development dependencies
- Build scripts and CI configuration
- Repository-specific files (.gitignore, etc.)

## CLI Architecture

### Entry Points

The `tch` command is defined in `setup.py` as a console script entry point:

```python
entry_points={
    'console_scripts': [
        'tch=time_config_hub.cli.root:main',
    ],
}
```

### Command Structure

Available commands:
- `tch tsn apply|status|reset|validate` - Manage TSN configurations
- `tch tcc apply|status|reset|validate` - Manage TCC configurations
- `tch daemon-status|daemon-start|daemon-stop|daemon-restart` - Manage daemon service
- `tch config-show` - Show active application configuration

## Publishing and Release

### Building Distribution Packages

```bash
# Clean previous builds
rm -rf build/ dist/ *.egg-info/

# Build source and wheel distributions
python setup.py sdist bdist_wheel

# Verify package contents
twine check dist/*
```

### Publishing to PyPI

```bash
# Test upload to TestPyPI first
twine upload --repository testpypi dist/*

# Upload to production PyPI
twine upload dist/*
```

### Version Management

Version information should be maintained in:
- `setup.py` - Package version
- `time_config_hub/__init__.py` - Module version
- Git tags for release tracking

## Module Structure

### Core Components

- **cli/root.py** - Click-based CLI entry point and command groups
- **orchestrator/time_hub_service.py** - Main orchestration service for TSN/TCC operations
- **services/tsn/service.py** - TSN domain service logic
- **services/tcc/service.py** - TCC domain service logic
- **infra/linux/** - Linux command wrappers and service management
- **exceptions.py** - Custom exception classes for error handling

### Configuration Management

The package uses a layered configuration approach:
1. Default configuration embedded in the package
2. System-wide configuration in `/etc/tch/`
3. User-specified configuration files
4. Command-line parameter overrides

## Contributing

### Development Workflow

1. Fork and clone the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Install development dependencies: `pip install -e .[dev]`
4. Make changes and add tests
5. Run test suite: `pytest tests/`
6. Check code quality: `ruff check . && black --config black_config.toml .`
7. Commit and push changes
8. Create a pull request

### Code Standards

- Follow PEP 8 style guidelines
- Use black for consistent formatting
- Use ruff for linting
- Add type hints where appropriate
- Include docstrings for public functions and classes
- Write tests for new functionality
- Maintain backward compatibility when possible
