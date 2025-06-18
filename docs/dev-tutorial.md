# FENDER Development Tutorial - Creating New Decoders

This tutorial will guide you through creating a new decoder for FENDER to support additional vehicle telematics systems.

## Table of Contents
1. [Understanding the Architecture](#understanding-the-architecture)
2. [Setting Up Development Environment](#setting-up-development-environment)
3. [Creating Your First Decoder](#creating-your-first-decoder)
4. [Advanced Decoder Techniques](#advanced-decoder-techniques)
5. [Testing Your Decoder](#testing-your-decoder)
6. [Summary](#summary)

## Understanding the Architecture

### Core Concepts

FENDER uses a plugin-based architecture where each decoder:
1. Inherits from `BaseDecoder` abstract class
2. Implements required methods
3. Is automatically discovered at runtime
4. Processes binary files to extract GPS data

### BaseDecoder Interface

```python
from abc import ABC, abstractmethod
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass

@dataclass
class GPSEntry:
    lat: float
    long: float
    timestamp: str
    extra_data: Dict[str, Any] = None

class BaseDecoder(ABC):
    @abstractmethod
    def get_name(self) -> str:
        """Return the display name"""
        pass
    
    @abstractmethod
    def get_supported_extensions(self) -> List[str]:
        """Return list of file extensions"""
        pass
    
    @abstractmethod
    def extract_gps_data(self, file_path: str, progress_callback=None) -> Tuple[List[GPSEntry], Optional[str]]:
        """Extract GPS data from file"""
        pass
    
    @abstractmethod
    def get_xlsx_headers(self) -> List[str]:
        """Return Excel column headers"""
        pass
    
    @abstractmethod
    def format_entry_for_xlsx(self, entry: GPSEntry) -> List[Any]:
        """Format entry for Excel output"""
        pass
    
    @abstractmethod
    def get_dropzone_text(self) -> str:
        """Return drag-drop zone text"""
        pass
```

## Setting Up Development Environment

### 1. Clone the Repository
```bash
git clone https://github.com/BitEU/fender.git
cd fender
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Create Decoder File
```bash
# Create new decoder in decoders directory
touch decoders/mycar_decoder.py
```

## Creating Your First Decoder

Let's create a decoder for a fictional "MyCar" telematics system.

### Step 1: Basic Structure

Create `decoders/mycar_decoder.py`:

```python
import struct
from datetime import datetime, timezone
from typing import List, Tuple, Optional, Any
from src.core.base_decoder import BaseDecoder, GPSEntry

class MyCarDecoder(BaseDecoder):
    """Decoder for MyCar telematics system"""
    
    def __init__(self):
        # Initialize any instance variables
        self.magic_bytes = b'MYCAR'
        
    def get_name(self) -> str:
        return "MyCar Telematics"
    
    def get_supported_extensions(self) -> List[str]:
        return ['.MCR', '.MYCAR']
    
    def get_dropzone_text(self) -> str:
        return "Drop your MyCar binary file here\nor click to browse"
    
    def get_xlsx_headers(self) -> List[str]:
        return ['latitude', 'longitude', 'timestamp', 'speed_kmh', 'heading']
    
    def format_entry_for_xlsx(self, entry: GPSEntry) -> List[Any]:
        return [
            entry.lat,
            entry.long,
            entry.timestamp,
            entry.extra_data.get('speed', ''),
            entry.extra_data.get('heading', '')
        ]
    
    def extract_gps_data(self, file_path: str, progress_callback=None) -> Tuple[List[GPSEntry], Optional[str]]:
        """Main extraction logic"""
        entries = []
        
        try:
            if progress_callback:
                progress_callback("Opening file...", 10)
            
            with open(file_path, 'rb') as f:
                data = f.read()
            
            # Verify file format
            if not data.startswith(self.magic_bytes):
                return [], "Invalid MyCar file format"
            
            if progress_callback:
                progress_callback("Parsing GPS records...", 30)
            
            # Parse the data (implementation depends on format)
            entries = self._parse_records(data, progress_callback)
            
            if progress_callback:
                progress_callback("Processing complete!", 100)
            
            return entries, None
            
        except Exception as e:
            return [], f"Error processing file: {str(e)}"
    
    def _parse_records(self, data: bytes, progress_callback=None) -> List[GPSEntry]:
        """Parse GPS records from binary data"""
        entries = []
        
        # Example: Fixed-size records after header
        header_size = 64
        record_size = 32
        
        # Skip header
        offset = header_size
        
        total_records = (len(data) - header_size) // record_size
        
        while offset + record_size <= len(data):
            # Extract record (example format)
            record = data[offset:offset + record_size]
            
            # Parse fields (adjust based on actual format)
            lat = struct.unpack('<d', record[0:8])[0]
            lon = struct.unpack('<d', record[8:16])[0]
            timestamp = struct.unpack('<Q', record[16:24])[0]
            speed = struct.unpack('<H', record[24:26])[0]
            heading = struct.unpack('<H', record[26:28])[0]
            
            # Convert timestamp to string
            dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            timestamp_str = dt.strftime('%Y-%m-%d %H:%M:%S')
            
            # Create GPS entry
            entry = GPSEntry(
                lat=lat,
                long=lon,
                timestamp=timestamp_str,
                extra_data={
                    'speed': speed,
                    'heading': heading
                }
            )
            
            entries.append(entry)
            offset += record_size
            
            # Update progress
            if progress_callback and total_records > 0:
                progress = 30 + (60 * len(entries) // total_records)
                progress_callback(f"Parsed {len(entries)}/{total_records} records", progress)
        
        return entries
```

### Step 2: Handling Different Binary Formats

#### Pattern-Based Extraction (like OnStar)

```python
import re

def find_gps_patterns(self, data: bytes) -> List[Dict]:
    """Find GPS data using regex patterns"""
    results = []
    
    # Convert to text for pattern matching
    text = data.decode('latin-1', errors='ignore')
    
    # Define patterns
    patterns = {
        'lat': r'LAT:(-?\d+\.\d+)',
        'lon': r'LON:(-?\d+\.\d+)',
        'time': r'TIME:(\d{10})'
    }
    
    # Find all matches
    lat_matches = re.finditer(patterns['lat'], text)
    
    for match in lat_matches:
        pos = match.start()
        
        # Look for nearby lon and time
        window = text[pos:pos+200]
        
        lon_match = re.search(patterns['lon'], window)
        time_match = re.search(patterns['time'], window)
        
        if lon_match and time_match:
            results.append({
                'lat': float(match.group(1)),
                'lon': float(lon_match.group(1)),
                'timestamp': int(time_match.group(1))
            })
    
    return results
```

#### Structured Binary Parsing

```python
def parse_structured_data(self, data: bytes) -> List[Dict]:
    """Parse fixed structure binary data"""
    results = []
    
    # Read file header
    if len(data) < 32:
        return results
    
    # Parse header
    magic = data[0:4]
    version = struct.unpack('<H', data[4:6])[0]
    record_count = struct.unpack('<I', data[6:10])[0]
    record_offset = struct.unpack('<I', data[10:14])[0]
    
    # Validate header
    if magic != b'MCAR':
        raise ValueError("Invalid file magic")
    
    # Parse records
    offset = record_offset
    
    for i in range(record_count):
        if offset + 28 > len(data):
            break
        
        # Record format:
        # 0-7:   latitude (double)
        # 8-15:  longitude (double)
        # 16-23: timestamp (uint64)
        # 24-25: speed (uint16)
        # 26-27: heading (uint16)
        
        record_data = struct.unpack('<ddQHH', data[offset:offset+28])
        
        results.append({
            'lat': record_data[0],
            'lon': record_data[1],
            'timestamp': record_data[2],
            'speed': record_data[3],
            'heading': record_data[4]
        })
        
        offset += 28
    
    return results
```

#### Database Extraction (like Honda)

```python
import sqlite3
import tempfile

def extract_from_database(self, file_path: str) -> List[Dict]:
    """Extract GPS data from embedded SQLite database"""
    results = []
    
    # First, extract the database from the binary
    with open(file_path, 'rb') as f:
        data = f.read()
    
    # Find SQLite header
    sqlite_header = b'SQLite format 3\x00'
    db_start = data.find(sqlite_header)
    
    if db_start == -1:
        raise ValueError("No SQLite database found")
    
    # Extract database to temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as tmp:
        tmp.write(data[db_start:])
        tmp_path = tmp.name
    
    # Query the database
    try:
        conn = sqlite3.connect(tmp_path)
        cursor = conn.cursor()
        
        # Find GPS table
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name LIKE '%gps%'
        """)
        
        table_name = cursor.fetchone()
        if not table_name:
            raise ValueError("No GPS table found")
        
        # Extract GPS data
        cursor.execute(f"""
            SELECT latitude, longitude, timestamp, speed, heading
            FROM {table_name[0]}
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
        """)
        
        for row in cursor.fetchall():
            results.append({
                'lat': row[0],
                'lon': row[1],
                'timestamp': row[2],
                'speed': row[3] or 0,
                'heading': row[4] or 0
            })
        
        conn.close()
        
    finally:
        # Clean up temp file
        import os
        os.unlink(tmp_path)
    
    return results
```

## Advanced Decoder Techniques

### Multi-Format Support

```python
class MultiFormatDecoder(BaseDecoder):
    """Decoder supporting multiple file format versions"""
    
    def extract_gps_data(self, file_path: str, progress_callback=None):
        # Detect format version
        version = self._detect_format_version(file_path)
        
        if version == 1:
            return self._extract_v1(file_path, progress_callback)
        elif version == 2:
            return self._extract_v2(file_path, progress_callback)
        else:
            return [], f"Unsupported format version: {version}"
    
    def _detect_format_version(self, file_path: str) -> int:
        """Detect file format version"""
        with open(file_path, 'rb') as f:
            header = f.read(32)
            
            # Check different version signatures
            if header.startswith(b'MCARv1'):
                return 1
            elif header.startswith(b'MCARv2'):
                return 2
            elif header[4:8] == b'\x01\x00\x00\x00':
                return 1  # Legacy format
            
        return 0  # Unknown
```

### Compressed Data Handling

```python
import zlib
import gzip

def extract_compressed_data(self, file_path: str):
    """Handle compressed GPS data"""
    
    with open(file_path, 'rb') as f:
        data = f.read()
    
    # Try different compression methods
    decompressed = None
    
    # Check for gzip
    if data[:2] == b'\x1f\x8b':
        try:
            decompressed = gzip.decompress(data)
        except Exception:
            pass
    
    # Check for zlib
    if not decompressed and data[:2] == b'\x78\x9c':
        try:
            decompressed = zlib.decompress(data)
        except Exception:
            pass
    
    # Check for embedded compressed sections
    if not decompressed:
        # Look for compression markers
        marker = b'COMPRESSED_DATA'
        pos = data.find(marker)
        
        if pos != -1:
            # Read compression info
            pos += len(marker)
            comp_type = data[pos]
            comp_size = struct.unpack('<I', data[pos+1:pos+5])[0]
            comp_data = data[pos+5:pos+5+comp_size]
            
            if comp_type == 1:  # zlib
                decompressed = zlib.decompress(comp_data)
    
    return decompressed or data
```

### Encryption Support

```python
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

def decrypt_data(self, encrypted_data: bytes, key: bytes = None) -> bytes:
    """Decrypt encrypted GPS data"""
    
    # Default key (for demonstration - real keys would be discovered/provided)
    if not key:
        key = b'MyCarDefaultKey!' * 2  # 32 bytes for AES-256
    
    # Extract IV from data (first 16 bytes)
    iv = encrypted_data[:16]
    ciphertext = encrypted_data[16:]
    
    # Decrypt using AES-CBC
    cipher = Cipher(
        algorithms.AES(key[:32]),
        modes.CBC(iv),
        backend=default_backend()
    )
    
    decryptor = cipher.decryptor()
    decrypted = decryptor.update(ciphertext) + decryptor.finalize()
    
    # Remove padding
    padding_length = decrypted[-1]
    return decrypted[:-padding_length]
```

## Testing Your Decoder

### Unit Tests

Create `tests/test_mycar_decoder.py`:

```python
import unittest
import tempfile
import struct
from decoders.mycar_decoder import MyCarDecoder

class TestMyCarDecoder(unittest.TestCase):
    def setUp(self):
        self.decoder = MyCarDecoder()
    
    def test_decoder_name(self):
        self.assertEqual(self.decoder.get_name(), "MyCar Telematics")
    
    def test_supported_extensions(self):
        extensions = self.decoder.get_supported_extensions()
        self.assertIn('.MCR', extensions)
        self.assertIn('.MYCAR', extensions)
    
    def test_valid_file_parsing(self):
        """Test parsing valid MyCar file"""
        # Create test file
        with tempfile.NamedTemporaryFile(suffix='.MCR', delete=False) as f:
            # Write header
            f.write(b'MYCAR\x00\x00\x00')  # Magic
            f.write(struct.pack('<I', 1))   # Version
            f.write(struct.pack('<I', 2))   # Record count
            f.write(struct.pack('<I', 64))  # Data offset
            f.write(b'\x00' * 44)           # Padding
            
            # Write records
            # Record 1: 37.7749, -122.4194, timestamp, speed, heading
            f.write(struct.pack('<d', 37.7749))    # lat
            f.write(struct.pack('<d', -122.4194))  # lon
            f.write(struct.pack('<Q', 1609459200)) # 2021-01-01 00:00:00
            f.write(struct.pack('<H', 50))         # speed
            f.write(struct.pack('<H', 180))        # heading
            f.write(b'\x00' * 4)                   # padding
            
            # Record 2
            f.write(struct.pack('<d', 37.7849))
            f.write(struct.pack('<d', -122.4094))
            f.write(struct.pack('<Q', 1609459260))
            f.write(struct.pack('<H', 45))
            f.write(struct.pack('<H', 185))
            f.write(b'\x00' * 4)
            
            test_file = f.name
        
        # Test extraction
        entries, error = self.decoder.extract_gps_data(test_file)
        
        # Verify results
        self.assertIsNone(error)
        self.assertEqual(len(entries), 2)
        
        # Check first entry
        self.assertAlmostEqual(entries[0].lat, 37.7749, places=4)
        self.assertAlmostEqual(entries[0].long, -122.4194, places=4)
        self.assertEqual(entries[0].timestamp, '2021-01-01 00:00:00')
        self.assertEqual(entries[0].extra_data['speed'], 50)
        
        # Cleanup
        import os
        os.unlink(test_file)
    
    def test_invalid_file_handling(self):
        """Test handling of invalid files"""
        with tempfile.NamedTemporaryFile(suffix='.MCR') as f:
            f.write(b'INVALID_DATA')
            f.flush()
            
            entries, error = self.decoder.extract_gps_data(f.name)
            
            self.assertEqual(len(entries), 0)
            self.assertIsNotNone(error)
            self.assertIn("Invalid", error)
    
    def test_xlsx_formatting(self):
        """Test Excel output formatting"""
        entry = GPSEntry(
            lat=37.7749,
            long=-122.4194,
            timestamp='2021-01-01 00:00:00',
            extra_data={'speed': 50, 'heading': 180}
        )
        
        headers = self.decoder.get_xlsx_headers()
        row = self.decoder.format_entry_for_xlsx(entry)
        
        self.assertEqual(len(headers), len(row))
        self.assertEqual(row[0], 37.7749)
        self.assertEqual(row[1], -122.4194)
        self.assertEqual(row[3], 50)

if __name__ == '__main__':
    unittest.main()
```

### Integration Testing

```python
def test_integration():
    """Test decoder integration with main app"""
    from src.cli.cli_interface import DecoderRegistry
    
    # Verify decoder is discovered
    registry = DecoderRegistry()
    decoder_names = registry.get_decoder_names()
    
    assert "MyCar Telematics" in decoder_names
    
    # Test decoder instantiation
    decoder_class = registry.get_decoder("MyCar Telematics")
    decoder = decoder_class()
    
    assert decoder is not None
    assert decoder.get_name() == "MyCar Telematics"
    
    print("Integration test passed!")

if __name__ == "__main__":
    test_integration()
```

## Summary

Creating a new decoder for FENDER involves:

1. **Understanding** the binary file format
2. **Implementing** the BaseDecoder interface
3. **Parsing** GPS data from the binary format
4. **Exporting** results to XLSX format
5. **Testing** thoroughly with real and synthetic data

Your decoder will automatically be discovered and available in FENDER once properly implemented!