"""
Copyright (c) Brand.Me, Inc. All rights reserved.

Setup script for Brand.Me Agentic System
"""

from setuptools import setup, find_packages

with open("requirements.txt") as f:
    requirements = f.read().splitlines()

setup(
    name="brandme-agentic",
    version="1.0.0",
    description="AI-native agent framework for Brand.Me platform",
    author="Brand.Me, Inc.",
    packages=find_packages(),
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "brandme=cli.main:main",
        ],
    },
    python_requires=">=3.11",
)
