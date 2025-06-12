# **FENDER \- Forensic Extraction of Navigational Data & Event Records**

FENDER is a powerful tool for extracting GPS location data from vehicle telematics binary files. It supports multiple vehicle manufacturers and provides an easy-to-use interface for forensic investigators and researchers.

## Feedback
Your input helps make FENDER better! Please share bugs, feature requests, or suggestions by [creating a GitHub Issue](https://github.com/BitEU/FENDER/issues/new). Include details like your OS, file type, test file, and steps to reproduce any issues.

## **Table of Contents**

* [Simple Guide](#simple-guide)  
  * [Quick Start](#quick-start)  
    * [Windows Users](#windows-users)  
    * [Python Users](#python-users)  
  * [Supported Vehicles](#supported-vehicles)  
  * [Features](#features)  
  * [Output Format](#output-format)  
  * [System Requirements](#system-requirements)  
* [Advanced Guide](#advanced-guide)  
  * [Architecture Overview](#architecture-overview)  
    * [Core Components](#core-components)  
  * [Technical Details](#technical-details)  
    * [Plugin Architecture](#plugin-architecture)  
  * [Decoder Specifications](#decoder-specifications)  
    * [OnStar Decoder](#onstar-decoder)  
    * [Toyota Decoder](#toyota-decoder)  
    * [Honda Decoder](#honda-decoder)  
  * [Installation from Source](#installation-from-source)  
    * [Windows](#windows)  
    * [Linux/macOS](#linuxmacos)  
  * [Building Executables](#building-executables)  
    * [Windows Executable with PyInstaller](#windows-executable-with-pyinstaller)  
  * [Decoder Development](#decoder-development)  
    * [Key Methods to Implement](#key-methods-to-implement)  
  * [Data Formats](#data-formats)  
    * [GPSEntry Structure](#gpsentry-structure)  
    * [XLSX Output Format](#xlsx-output-format)  
  * [Troubleshooting](#troubleshooting)  
    * [Common Issues](#common-issues)  
    * [Debug Mode](#debug-mode)  
* [Todo](#todo)  
* [Contributing](#contributing)  
* [Credits](#credits)  

## **Simple Guide**

### **Quick Start**

#### **Windows Users**

1. Download the latest release from the releases page.  
2. Double-click FENDER.exe to run the application.  
3. Select your decoder type from the left panel.  
4. Drag and drop your binary file or click to browse.  
5. Click "Process File" to extract GPS data.  
6. Results will be saved as an XLSX file in the same directory.

#### **Python Users**

\# Install dependencies  
pip install \-r requirements.txt

\# Run the GUI  
python main\_gps\_decoder.py

\# Run in CLI mode  
python main\_gps\_decoder.py \--cli

### **Supported Vehicles**

* **OnStar Gen 10+** \- Extracts GPS data from OnStar NAND dumps (.CE0 files)  
* **Toyota TL19** \- Extracts GPS data from Toyota infotainment systems (.CE0 files)  
* **Honda Telematics** \- Extracts GPS data from Honda Android eMMC images (.USER files)

### **Features**

* 🚗 Multi-manufacturer support with modular decoder architecture  
* 📍 Extracts latitude, longitude, and timestamps  
* 📊 Exports data to XLSX format for analysis  
* 🖱️ Drag-and-drop file support  
* 💻 Both GUI and command-line interfaces  
* 🔌 Plugin architecture for easy decoder additions

### **Output Format**

The tool generates an XLSX file containing:

* GPS coordinates (latitude/longitude)  
* Timestamps (UTC format)  
* Additional metadata specific to each decoder type

### **System Requirements**

* Windows 10/11 (for .exe release)  
* Python 3.8+ (for source code)  
* 4GB RAM minimum  
* 500MB free disk space

## **Advanced Guide**

### **Architecture Overview**

FENDER uses a modular plugin architecture that allows for easy addition of new decoder types:  
FENDER/  
├── main\_gps\_decoder.py    \# Main application (GUI/CLI)  
├── base\_decoder.py        \# Abstract base class  
├── decoders/             \# Decoder plugins directory  
│   ├── \_\_init\_\_.py  
│   ├── onstar\_decoder.py  
│   ├── toyota\_decoder.py  
│   └── honda\_decoder.py  
└── requirements.txt

#### **Core Components**

1. **DecoderRegistry**: Auto-discovers and manages available decoders  
2. **BaseDecoder**: Abstract class defining the decoder interface  
3. **VehicleGPSDecoder**: Main GUI application using tkinter  
4. **GPSEntry**: Standard data structure for GPS points

### **Technical Details**

#### **Plugin Architecture**

The application automatically discovers decoders at runtime:

1. Scans the decoders/ directory for \*\_decoder.py files  
2. Imports modules and finds classes inheriting from BaseDecoder  
3. Registers decoders in the registry  
4. Makes them available in the GUI/CLI

### **Decoder Specifications**

#### **OnStar Decoder**

File Format: OnStar NAND dumps (.CE0 files)  
Data Location: GPS data stored as text within binary  
Extraction Method: Pattern matching for GPS keywords  
Key patterns:

* gps\_tow= \- GPS time of week (milliseconds)  
* gps\_week= \- GPS week number  
* lat= \- Latitude in hex format  
* lon= \- Longitude in hex format  
* utc\_year=, utc\_month=, etc. \- UTC timestamp components

**Coordinate Format**:

* Stored as 16-byte hex strings  
* Decoded as little-endian doubles  
* Divided by 10,000,000 for decimal degrees

#### **Toyota Decoder**

File Format: Toyota TL19 NAND dumps (.CE0 files)  
Data Location: Structured binary format with markers  
Extraction Method: Binary pattern matching with offsets  
Key markers:

* loc.position \- Base location marker  
* Various longitude markers (e.g., ong6, ongi5)  
* Latitude marker: latitud,  
* Multiple timestamp markers

**Data Structure**:

* Fixed offsets from markers  
* Timestamps stored as Unix milliseconds  
* Coordinates as ASCII strings in binary

#### **Honda Decoder**

File Format: Honda Android eMMC images (.USER files)  
Data Location: SQLite database in Android userdata partition  
Extraction Method: Filesystem extraction using pytsk3  
Process:

1. Find userdata partition (GPT or ext4)  
2. Extract filesystem using TSK  
3. Locate crm.db in Honda telematics app data  
4. Query eco\_logs table for GPS data

**Database Schema**:

* start\_pos\_lat, start\_pos\_lon \- Starting coordinates  
* finish\_pos\_lat, finish\_pos\_lon \- Ending coordinates  
* start\_pos\_time, finish\_pos\_time \- Timestamps

### **Installation from Source**

#### **Windows**

\# Clone repository  
git clone https://github.com/BitEU/fender.git  
cd fender

\# Install dependencies  
pip install \-r requirements.txt

\# Run application  
python main\_gps\_decoder.py

#### **Linux/macOS**

\# Clone repository  
git clone https://github.com/BitEU/fender.git  
cd fender

\# Install dependencies  
pip install \-r requirements.txt

\# Install system dependencies for pytsk3  
\# Ubuntu/Debian:  
sudo apt-get install libtsk-dev

\# macOS:  
brew install sleuthkit

\# Install pytsk3  
pip install pytsk3

\# Run application  
python main\_gps\_decoder.py

### **Building Executables**

#### **Windows Executable with PyInstaller**

\# Install PyInstaller  
pip install pyinstaller

\# Build single-file executable  
python \-m PyInstaller \--onefile \--windowed \\  
  \--icon=car.ico \\  
  \--add-data "decoders;decoders" \\  
  \--add-data "base\_decoder.py;." \\  
  \--add-data "car.ico;." \\  
  \--hidden-import="tkinterdnd2" \\  
  \--hidden-import="decoders.honda\_decoder" \\  
  \--hidden-import="decoders.onstar\_decoder" \\  
  \--hidden-import="decoders.toyota\_decoder" \\  
  main\_gps\_decoder.py

\# Output will be in dist/main\_gps\_decoder.exe

### **Decoder Development**

See the Development Tutorial for detailed instructions on creating new decoders.

#### **Key Methods to Implement**

1. get\_name() \- Decoder display name  
2. get\_supported\_extensions() \- File extensions list  
3. extract\_gps\_data() \- Main extraction logic  
4. get\_xlsx\_headers() \- Column headers for output  
5. format\_entry\_for\_xlsx() \- Format GPS data for Excel

### **Data Formats**

#### **GPSEntry Structure**

@dataclass  
class GPSEntry:  
    lat: float              \# Latitude in decimal degrees  
    long: float             \# Longitude in decimal degrees  
    timestamp: str          \# ISO format timestamp  
    extra\_data: Dict\[str, Any\]  \# Decoder-specific metadata

#### **XLSX Output Format**

Each decoder can define custom columns, but typically includes:

* Latitude/Longitude coordinates  
* Timestamp information  
* Decoder-specific metadata  
* Hex representations (for debugging and data verification)

### **Troubleshooting**

#### **Common Issues**

**"No decoders found" error**

* Ensure decoders/ directory exists  
* Check that decoder files end with \_decoder.py  
* Verify Python path includes the application directory

**Honda decoder not working**

* Install pytsk3 library  
* Ensure you have a valid Android eMMC image  
* Check that the image contains a userdata partition

**Large file processing**

* Files over 4GB may require 64-bit Python  
* Ensure sufficient RAM (8GB+ recommended for large files)  
* Consider using CLI mode for better performance

**Windows Defender warnings**

* Add exception for FENDER.exe  
* Or build from source yourself

#### **Debug Mode**

Run with verbose output:  
\# Add to main\_gps\_decoder.py  
import logging  
logging.basicConfig(level=logging.DEBUG)

#### **Unit Testing**

Run the following script to test both the base decoder and main python file:
pytest test_main.py -v --log-cli-level=DEBUG

## **Todo**

* Optimizing speed and efficiency
* Plotting points on an interactive map
* Include more data than just timestamps and geolocation
* Batch processing
* Permit users to export to CSV or JSON, not just XLSX
* Use SHA256 to hash disk images as well as the reports
* Include timestamp of report generation in filename
* Include details of extraction, device configuration, python configuration in reports in seperste worksheet
* Implement anomoly detection to flag any rows that arent in line eith the rest of the data
* Use tempfile and shutil for more secure file handling
* Make this program compliant with leading guidelines (ISO 27037? NIST 800-86?)
* Export data to GeoJSON
* Improve unit testing
* Make test files publically available

## **Contributing**

1. Fork the repository  
2. Create a feature branch  
3. Add your decoder to decoders/  
4. Include test files for validation, otherwise contact sschiavone@pace.edu if they contain sensitive data
5. Submit a pull request

## **Credits**

1. This project includes images created by [Iconoir](https://iconoir.com/). Copyright 2025 Iconoir