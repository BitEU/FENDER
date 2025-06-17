"""
FENDER Setup Script
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read the requirements from requirements.txt
requirements_path = Path(__file__).parent / "requirements.txt"
with open(requirements_path, 'r', encoding='utf-8') as f:
    requirements = [line.strip() for line in f if line.strip() and not line.startswith('#')]

# Read the README for long description
readme_path = Path(__file__).parent / "readme.md"
with open(readme_path, 'r', encoding='utf-8') as f:
    long_description = f.read()

setup(
    name="fender",
    version="0.2.2",
    author="FENDER Team",
    description="Forensic Extraction of Navigational Data & Event Records",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    package_data={
        "": ["*.py"],
        "fender": ["assets/*"],
    },
    include_package_data=True,
    install_requires=requirements,
    python_requires=">=3.8",
    entry_points={
        "console_scripts": [
            "fender=main:main",
            "fender-cli=main:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "Intended Audience :: Legal Industry",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Scientific/Engineering :: Information Analysis",
        "Topic :: System :: Forensics",
    ],
    keywords="forensics gps navigation telematics vehicle",
)
