#!/usr/bin/env python3
"""Legacy setuptools shim.

This project is primarily configured via :file:`pyproject.toml` (PEP 621).
This :file:`setup.py` is kept for legacy workflows that still invoke
``python setup.py ...``.
"""

import os

from setuptools import find_packages, setup


# Read the README file for long description
def read_readme():
    """
    Read the contents of the README.md file located in the same directory as this script.

    :return: The contents of the README.md file if it exists, otherwise a default description string
    :rtype: str
    """
    readme_path = os.path.join(os.path.dirname(__file__), "README.md")
    try:
        with open(readme_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "Time Config Hub"


setup(
    name="time_config_hub",
    version="1.0.0",
    author="Intel",
    author_email="noor.azura.ahmad.tarmizi@intel.com, eng.keong.koay@intel.com, "
    + "shi.jie.donavan.liow@intel.com",
    description="Time Config Hub for Intel TSN-capable hardware",
    long_description=read_readme(),
    long_description_content_type="text/markdown",
    url="https://github.com/intel/time-confighub",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: System :: Networking",
        "License :: OSI Approved :: BSD License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: POSIX :: Linux",
    ],
    python_requires=">=3.9",
    install_requires=[
        "pyyaml>=6.0",
        "lxml>=6.0",
        "click>=8.2",
        "netifaces>=0.11",
        "watchdog>=6.0",
        "colorama>=0.4.6",
    ],
    extras_require={
        "dev": [
            "pytest>=8.4",
            "black==25.12.0",
            "ruff==0.14.8",
            "pylint==3.3",
        ]
    },
    entry_points={
        "console_scripts": [
            "tch=time_config_hub.cli:main",
        ],
    },
    include_package_data=True,
    package_data={
        "time_config_hub": ["templates/tch.service"],
    },
    zip_safe=False,
)
