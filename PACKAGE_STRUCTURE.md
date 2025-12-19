# Time Config Hub Package Structure

This document provides technical information for developers and maintainers of the Time Config Hub Python package.

## Repository Structure

```
time-confighub/          # Time Config Hub (Python package)
    ├── setup.py                # Package setup configuration
    ├── install.sh              # Installation script
    ├── requirements.txt         # Production dependencies
    ├── LICENSE                  # BSD License
    ├── MANIFEST.in              # Package manifest for distribution
    ├── .gitignore              # Git ignore rules
    ├── README.md               # User documentation
    ├── PACKAGE_STRUCTURE.md    # Developer documentation (this file)
    ├── src/
    |   └── time_config_hub/     # Main Python package
    |       ├── __init__.py         # Package initialization
    |       ├── cli.py              # Command-line interface
    |       ├── core.py             # Core functionality
    |       ├── config_parser.py    # Configuration parsing
    |       ├── tc_manager.py       # Traffic control management
    |       └── exceptions.py       # Custom exceptions
    ├── tests/
    └── pyproject.toml

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
pytest tests/test_config_parser.py

# Generate HTML coverage report
pytest --cov=time_config_hub --cov-report=html tests/
```

### Code Quality

```bash
# Format code with black
cd src && black time_config_hub/

# Check code style and quality
pylint time_config_hub/
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
        'tch=time_config_hub.cli:main',
    ],
}
```

### Command Structure

Available commands:
- `tch apply` - Apply TSN configuration
- `tch status` - Get interface status
- `tch validate` - Validate configuration files
- `tch watch` - Monitor directory for changes

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

- **cli.py** - Click-based command-line interface implementation
- **core.py** - Main Time Config Hub class and business logic
- **config_parser.py** - XML/YAML configuration file parsing
- **tc_manager.py** - Linux Traffic Control command generation and execution
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
6. Check code quality: `cd src && black . && pylint time_config_hub/`
7. Commit and push changes
8. Create a pull request

### Code Standards

- Follow PEP 8 style guidelines
- Use black for consistent formatting
- Add type hints where appropriate
- Include docstrings for public functions and classes
- Write tests for new functionality
- Maintain backward compatibility when possible
