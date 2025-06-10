# FENDER - Forensic Extraction of Navigational Data & Event Records

FENDER is a powerful tool for extracting GPS location data from vehicle telematics binary files. It supports multiple vehicle manufacturers and provides an easy-to-use interface for forensic investigators and researchers.

## Simple readme

### Quick Start

#### Windows Users
1. Download the latest release from the releases page
2. Double-click `FENDER.exe` to run the application
3. Select your decoder type from the left panel
4. Drag and drop your binary file or click to browse
5. Click "Process File" to extract GPS data
6. Results will be saved as an XLSX file in the same directory

#### Python Users
```bash
# Install dependencies
pip install -r requirements.txt

# Run the GUI
python main_gps_decoder.py

# Run in CLI mode
python main_gps_decoder.py --cli
```

### Supported Vehicles

- **OnStar Gen 10+** - Extracts GPS data from OnStar NAND dumps (.CE0 files)
- **Toyota TL19** - Extracts GPS data from Toyota infotainment systems (.CE0 files)
- **Honda Telematics** - Extracts GPS data from Honda Android eMMC images (.USER files)

### Features

- 🚗 Multi-manufacturer support with modular decoder architecture
- 📍 Extracts latitude, longitude, and timestamps
- 📊 Exports data to XLSX format for analysis
- 🖱️ Drag-and-drop file support
- 💻 Both GUI and command-line interfaces
- 🔌 Plugin architecture for easy decoder additions

### Output Format

The tool generates an XLSX file containing:
- GPS coordinates (latitude/longitude)
- Timestamps (UTC format)
- Additional metadata specific to each decoder type

### System Requirements

- Windows 10/11 (for .exe release)
- Python 3.8+ (for source code)
- 4GB RAM minimum
- 500MB free disk space



## Advanced readme

### Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Technical Details](#technical-details)
3. [Decoder Specifications](#decoder-specifications)
4. [Installation from Source](#installation-from-source)
5. [Building Executables](#building-executables)
6. [Decoder Development](#decoder-development)
7. [Data Formats](#data-formats)
8. [Troubleshooting](#troubleshooting)
9. [Contributing](#contributing)

### Architecture Overview

FENDER uses a modular plugin architecture that allows for easy addition of new decoder types:

```
FENDER/
├── main_gps_decoder.py    # Main application (GUI/CLI)
├── base_decoder.py        # Abstract base class
├── decoders/             # Decoder plugins directory
│   ├── __init__.py
│   ├── onstar_decoder.py
│   ├── toyota_decoder.py
│   └── honda_decoder.py
└── requirements.txt
```

#### Core Components

1. **DecoderRegistry**: Auto-discovers and manages available decoders
2. **BaseDecoder**: Abstract class defining the decoder interface
3. **VehicleGPSDecoder**: Main GUI application using tkinter
4. **GPSEntry**: Standard data structure for GPS points

### Technical Details

#### Plugin Architecture

The application automatically discovers decoders at runtime:

1. Scans the `decoders/` directory for `*_decoder.py` files
2. Imports modules and finds classes inheriting from `BaseDecoder`
3. Registers decoders in the registry
4. Makes them available in the GUI/CLI

### Decoder Specifications

#### OnStar Decoder

**File Format**: OnStar NAND dumps (.CE0 files)  
**Data Location**: GPS data stored as text within binary  
**Extraction Method**: Pattern matching for GPS keywords

Key patterns:
- `gps_tow=` - GPS time of week (milliseconds)
- `gps_week=` - GPS week number
- `lat=` - Latitude in hex format
- `lon=` - Longitude in hex format
- `utc_year=`, `utc_month=`, etc. - UTC timestamp components

**Coordinate Format**: 
- Stored as 16-byte hex strings
- Decoded as little-endian doubles
- Divided by 10,000,000 for decimal degrees

#### Toyota Decoder

**File Format**: Toyota TL19 NAND dumps (.CE0 files)  
**Data Location**: Structured binary format with markers  
**Extraction Method**: Binary pattern matching with offsets

Key markers:
- `loc.position` - Base location marker
- Various longitude markers (e.g., `ong6`, `ongi5`)
- Latitude marker: `latitud,`
- Multiple timestamp markers

**Data Structure**:
- Fixed offsets from markers
- Timestamps stored as Unix milliseconds
- Coordinates as ASCII strings in binary

#### Honda Decoder

**File Format**: Honda Android eMMC images (.USER files)  
**Data Location**: SQLite database in Android userdata partition  
**Extraction Method**: Filesystem extraction using pytsk3

Process:
1. Find userdata partition (GPT or ext4)
2. Extract filesystem using TSK
3. Locate `crm.db` in Honda telematics app data
4. Query `eco_logs` table for GPS data

**Database Schema**:
- `start_pos_lat`, `start_pos_lon` - Starting coordinates
- `finish_pos_lat`, `finish_pos_lon` - Ending coordinates
- `start_pos_time`, `finish_pos_time` - Timestamps

### Installation from Source

#### Windows
```bash
# Clone repository
git clone https://github.com/BitEU/fender.git
cd fender

# Install dependencies
pip install -r requirements.txt

# Run application
python main_gps_decoder.py
```

#### Linux/macOS
```bash
# Clone repository
git clone https://github.com/BitEU/fender.git
cd fender

# Install dependencies
pip install -r requirements.txt

# Install system dependencies for pytsk3
# Ubuntu/Debian:
sudo apt-get install libtsk-dev

# macOS:
brew install sleuthkit

# Install pytsk3
pip install pytsk3

# Run application
python main_gps_decoder.py
```

### Building Executables

#### Windows Executable with PyInstaller

```bash
# Install PyInstaller
pip install pyinstaller

# Build single-file executable
python -m PyInstaller --onefile --windowed \
  --icon=car.ico \
  --add-data "decoders;decoders" \
  --add-data "base_decoder.py;." \
  --add-data "car.ico;." \
  --hidden-import="tkinterdnd2" \
  --hidden-import="decoders.honda_decoder" \
  --hidden-import="decoders.onstar_decoder" \
  --hidden-import="decoders.toyota_decoder" \
  main_gps_decoder.py

# Output will be in dist/main_gps_decoder.exe
```

### Decoder Development

See the Development Tutorial for detailed instructions on creating new decoders.

#### Key Methods to Implement

1. `get_name()` - Decoder display name
2. `get_supported_extensions()` - File extensions list
3. `extract_gps_data()` - Main extraction logic
4. `get_xlsx_headers()` - Column headers for output
5. `format_entry_for_xlsx()` - Format GPS data for Excel

### Data Formats

#### GPSEntry Structure
```python
@dataclass
class GPSEntry:
    lat: float              # Latitude in decimal degrees
    long: float             # Longitude in decimal degrees
    timestamp: str          # ISO format timestamp
    extra_data: Dict[str, Any]  # Decoder-specific metadata
```

#### XLSX Output Format

Each decoder can define custom columns, but typically includes:
- Latitude/Longitude coordinates
- Timestamp information
- Decoder-specific metadata
- Hex representations (for debugging and data verification)

### Troubleshooting

#### Common Issues

**"No decoders found" error**
- Ensure `decoders/` directory exists
- Check that decoder files end with `_decoder.py`
- Verify Python path includes the application directory

**Honda decoder not working**
- Install pytsk3 library
- Ensure you have a valid Android eMMC image
- Check that the image contains a userdata partition

**Large file processing**
- Files over 4GB may require 64-bit Python
- Ensure sufficient RAM (8GB+ recommended for large files)
- Consider using CLI mode for better performance

**Windows Defender warnings**
- Add exception for FENDER.exe
- Or build from source yourself

#### Debug Mode

Run with verbose output:
```python
# Add to main_gps_decoder.py
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Contributing

1. Fork the repository
2. Create a feature branch
3. Add your decoder to `decoders/`
4. Include test files if possible
5. Submit a pull request

### Credits

1. This project includes images created by Iconoir. Copyright 2025 [Iconoir](https://iconoir.com/)
2. This project includes software developed by [qnx6-extractor](https://github.com/ReFirmLabs/qnx6-extractor). Copyright 2020  ReFirm Labs
