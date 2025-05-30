#!/usr/bin/env python3

from setuptools import setup, find_packages

with open("README.md", "r") as fh:
    long_description = fh.read()

with open("requirements.txt", "r") as f:
    requirements = f.read().splitlines()

setup(
    name="garden-tiller",
    version="0.1.0",
    author="Your Name",
    author_email="your.email@example.com",
    description="A validation suite for OpenShift lab environments",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/garden-tiller",
    packages=find_packages(),
    include_package_data=True,
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
        "Environment :: Console",
        "Intended Audience :: System Administrators",
        "Intended Audience :: Information Technology",
        "Topic :: System :: Systems Administration",
    ],
    python_requires=">=3.9",
    install_requires=requirements,
    scripts=[
        "check-lab.sh",
        "scripts/report_generator.py",
    ],
    entry_points={
        "console_scripts": [
            "garden-tiller=check-lab:main",
        ],
    },
)
