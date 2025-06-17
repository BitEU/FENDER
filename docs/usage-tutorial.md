# FENDER Usage Tutorial

This tutorial will walk you through using FENDER to extract GPS data from vehicle telematics files. The modern iteration of FENDER leverages a modular plugin architecture, supports multiple export formats, improved performance for large files, and enhanced command-line batch processing.

## Table of Contents
1. [Getting Started](#getting-started)
2. [GUI Mode Tutorial](#gui-mode-tutorial)
3. [CLI Mode Tutorial](#cli-mode-tutorial)
4. [Understanding the Output](#understanding-the-output)
5. [Real-World Examples](#real-world-examples)

## Getting Started

### What You'll Need
- The FENDER application (executable or Python source)
- A vehicle telematics binary file (e.g., `.CE0`, `.USER`, or folder-based log data)
- Approximately 5–10 minutes to process each file (batch processing is available for automation)

### Supported File Types
- **OnStar**: `.CE0` files from OnStar NAND dumps
- **Toyota**: `.CE0` files from Toyota TL19 systems
- **Honda**: `.USER` files from Honda Android eMMC images
- **Mercedes-Benz & Stellantis**: Files and folders containing log data

## GUI Mode Tutorial

### Step 1: Launch FENDER
**Windows Users:**
- Double-click `FENDER.exe`
- If Windows Defender displays a warning, click "More info" and then "Run anyway"

**Python Users:**
```bash
python main.py
```

### Step 2: Select Your Decoder

![Decoder Selection](docs/images/decoder-selection.png)

1. Look at the left panel labeled "Select Decoder"
2. Click the button for your vehicle type:
   - **OnStar Gen 10+** for GM vehicles with OnStar
   - **Toyota TL19** for Toyota vehicles
   - **Honda Telematics** for Honda vehicles
   - **Mercedes-Benz** for Mercedes vehicles
   - **Stellantis** for Stellantis vehicles

The selected decoder will be highlighted in blue.

### Step 3: Load Your File

You have three options:

**Option A: Drag and Drop**
1. Open your file explorer
2. Find your file/folder
3. Drag it onto the gray drop zone
4. Release when you see the drop indicator

**Option B: Click to Browse**
1. Click anywhere in the gray drop zone
2. Navigate to your file in the dialog
3. Select your file/folder and click "Open"

**Option C: Browse Button**
1. Click the "Browse Files" button
2. Select your file from the dialog

### Step 4: Verify File Information

Once loaded, you'll see:
- Filename displayed in the drop zone
- File size in MB
- "Process File" button becomes active (blue)

Example:
```
Selected: onstar_dump_2024.CE0
Size: 245.67 MB
```

### Step 5: Process the File

1. Click the blue "Process File" button
2. Watch the progress bar and status messages:
   - "Reading binary file..." (10%)
   - "Finding GPS data blocks..." (30%)
   - "Parsing blocks..." (50-80%)
   - "Writing XLSX file..." (85%)
   - "Processing complete!" (100%)

### Step 6: Find Your Results

The output file will be saved in the same directory as your input file with the decoder name appended:

- Input: `vehicle_dump.CE0`
- Output: `vehicle_dump_OnStar Gen 10+.xlsx`

The results section will show:
```
Successfully extracted 1,234 GPS entries to:
vehicle_dump_OnStar Gen 10+.xlsx
```

### Step 7: Clear and Process Another File

1. Click the "Clear" button to reset
2. Select a different decoder if needed
3. Load your next file

## CLI Mode Tutorial

The command-line interface is perfect for batch processing or automation.

### Basic Usage

```bash
python main.py --cli
```

### Step-by-Step CLI Process

1. **Run the CLI**
   ```bash
   $ python main.py --cli
   Vehicle GPS Decoder - CLI Mode
   ========================================
   ```

2. **Select Decoder**
   ```
   Available decoders:
   1. Honda Telematics
   2. OnStar Gen 10+
   3. Toyota TL19
   
   Select decoder (enter number): 2
   ```

3. **Enter File Path**
   ```
   Enter the path to the OnStar Gen 10+ file: /path/to/onstar_dump.CE0
   ```

4. **Monitor Progress**
   ```
   Processing OnStar Gen 10+ file...
   Reading binary file... (10%)
   Finding GPS data blocks... (30%)
   Parsing block 145/289 (65%)
   Writing XLSX file... (85%)
   Processing complete! (100%)
   
   Successfully extracted 289 GPS entries.
   Results written to: /path/to/onstar_dump_OnStar Gen 10+.xlsx
   ```

### Batch Processing Script

Create a batch processing script:

```python
#!/usr/bin/env python
import os
import glob
from main import DecoderRegistry
from openpyxl import Workbook

# Initialize registry
registry = DecoderRegistry()

# Process all CE0 files in directory
for file_path in glob.glob("*.CE0"):
    print(f"Processing {file_path}...")
    
    # Auto-detect decoder based on file content
    # For this example, we'll use OnStar
    decoder_class = registry.get_decoder("OnStar Gen 10+")
    decoder = decoder_class()
    
    # Extract data
    entries, error = decoder.extract_gps_data(file_path)
    
    if error:
        print(f"Error: {error}")
        continue
    
    # Save results
    output_path = f"{os.path.splitext(file_path)[0]}_GPS.xlsx"
    # ... (write XLSX code)
    
    print(f"Extracted {len(entries)} entries to {output_path}")
```

## Understanding the Output

### XLSX File Structure

The output Excel file contains one worksheet named "GPS Data" with the following structure:

#### OnStar Output Columns:
| Column | Description | Example |
|--------|-------------|---------|
| lat | Latitude in decimal degrees | 42.331427 |
| long | Longitude in decimal degrees | -83.045754 |
| utc_year | Year | 2024 |
| utc_month | Month (1-12) | 3 |
| utc_day | Day of month | 15 |
| utc_hour | Hour (0-23) | 14 |
| utc_min | Minute (0-59) | 32 |
| timestamp_time | Full timestamp | 2024-03-15 14:32:45.123 |
| lat_hex | Raw hex data | 40A5B3C2... |
| lon_hex | Raw hex data | C05C1A7F... |

#### Toyota Output Columns:
| Column | Description | Example |
|--------|-------------|---------|
| lat | Latitude | 35.689722 |
| long | Longitude | 139.691667 |
| timestamp_time | Unix timestamp | 2024-03-15 09:45:23.000 |

#### Honda Output Columns:
| Column | Description | Example |
|--------|-------------|---------|
| start_pos_lat | Trip start latitude | 37.774929 |
| start_pos_lon | Trip start longitude | -122.419418 |
| start_pos_time | Start timestamp | 2024-03-15 08:00:00.000 |
| finish_pos_time | End timestamp | 2024-03-15 08:45:00.000 |
| finish_pos_lat | Trip end latitude | 37.795210 |
| finish_pos_lon | Trip end longitude | -122.394012 |

### Data Quality Indicators

- **ERROR** - Indicates extraction or parsing failure
- **DATE BEFORE 2010 ERROR** - Likely invalid timestamp
- **DATE AFTER 2060 ERROR** - Timestamp parsing issue
- **0** or blank - Missing data

### Viewing in Excel

1. Open the XLSX file in Excel
2. Select all data (Ctrl+A)
3. Format as Table for easier viewing
4. Use filters to find specific dates/locations
5. Create charts/maps from the coordinates

## Real-World Examples

### Example 1: Analyzing Vehicle Routes

**Scenario**: Investigating a vehicle's movements on a specific date

1. Open the XLSX file in Excel
2. Filter by date columns (utc_year, utc_month, utc_day)
3. Sort by timestamp_time
4. Plot coordinates on a map

### Example 2: Finding Frequent Locations

**Scenario**: Identifying commonly visited places

1. Export lat/long columns to mapping software
2. Use clustering analysis to find frequent stops
3. Cross-reference with known locations

### Example 3: Timeline Analysis

**Scenario**: Creating a movement timeline

1. Sort by timestamp
2. Calculate time gaps between entries
3. Identify periods of movement vs. stationary

### Example 4: Data Validation

**Scenario**: Checking data integrity

1. Look for ERROR entries
2. Check for unrealistic coordinates (0,0)
3. Verify timestamps are within expected range
4. Look for duplicate entries