import re
from datetime import datetime, timezone
from typing import List, Tuple, Optional, Any
from dataclasses import dataclass
from base_decoder import BaseDecoder, GPSEntry

@dataclass
class LocationData:
    """Stores extracted location and time data."""
    longitude: str
    latitude: str
    timestamp: str
    offset: int

class ToyotaDecoder(BaseDecoder):
    def __init__(self):
        # Data offsets (from original script)
        self.LONGITUDE_OFFSET = 9
        self.LATITUDE_OFFSET = 15
        self.TIMESTAMP_OFFSET = 15
        
        # Maximum distance thresholds for data validation
        self.MAX_LOCATION_DISTANCE = 150
        self.MAX_TIMESTAMP_DISTANCE = 250
        self.MIN_MARKER_SEPARATION = 550
        
        # Byte patterns for data markers
        self.MARKERS = {
            'location_base': b'\x6C\x6F\x63\x2E\x70\x6F\x73\x69\x74\x69\x6F\x6E',  # loc.position
            'longitude': [
                b'\x6F\x6E\x67\x36\x00\x02',  # ong6
                b'\x6F\x6E\x67\x69\x35'        # ongi5
            ],
            'latitude': [
                b'\x6C\x61\x74\x69\x74\x75\x64\x2C\xE0\x01'  # latitud,
            ],
            'timestamp': [
                b'\x74\x69\x6D\x65\x73\x74\x61\x6D\x70\x31',          # timestamp1
                b'\x74\x69\x6D\x65\x73\x74\x61\x6D\x70\x2B\xe4',      # timestamp+
                b'\x74\x69\x6D\x65\x73\x74\x61\x6D\x70\x29\xDC',      # timestamp)
                b'\x74\x69\x6D\x65\x73\x74\x61\x6D\x70\x2E\xF3\x01',  # timestamp.
                b'\x74\x69\x6D\x65\x73\x74\x61\x6D\x70\xF0\x0E',      # timestamp
                b'\x74\x69\x6D\x65\x73\x74\x61\x6D\x70\x2A\xE0',      # timestamp*
                b'\x74\x69\x6D\x65\x73\x74\x61\x6D\x70\x2C\xE8',      # timestamp,
                b'\x74\x69\x6D\x65\x73\x74\x61\x6D\x70\xF0\x02\x29',  # timestamp..)
                b'\x74\x69\x6D\x65\x73\x74\x61\x6D\x70\x2D\xEC\x01'   # timestamp-
            ]
        }
        
        self.data: bytes = b''
        self.locations: List[LocationData] = []
    
    def get_name(self) -> str:
        return "Toyota TL19"
    
    def get_supported_extensions(self) -> List[str]:
        return ['.CE0']
    
    def get_dropzone_text(self) -> str:
        return "Drop your Toyota NAND binary here\nor click to browse"

    def get_xlsx_headers(self) -> List[str]:
        # Toyota format has fewer columns than OnStar
        return ['lat', 'long', 'timestamp_time'] + [''] * 11  # 11 blank columns
    
    def format_entry_for_xlsx(self, entry: GPSEntry) -> List[Any]:
        """Format a GPSEntry into a row for the XLSX file"""
        return [
            entry.lat if entry.lat != 0 else 'ERROR',
            entry.long if entry.long != 0 else 'ERROR',
            entry.timestamp if entry.timestamp else 'ERROR',
            '', '', '', '', '', '', '', '', '', '', ''  # Eleven blank columns
        ]
    
    def extract_gps_data(self, file_path: str, progress_callback=None) -> Tuple[List[GPSEntry], Optional[str]]:
        """Extract GPS data from Toyota binary file"""
        try:
            if progress_callback:
                progress_callback("Reading binary file...", 10)
            
            with open(file_path, 'rb') as f:
                self.data = f.read()
            
            if progress_callback:
                progress_callback("Finding GPS data blocks...", 30)
            
            # Find base location markers
            base_positions = self.find_pattern_positions([self.MARKERS['location_base']])
            
            if progress_callback:
                progress_callback(f"Found {len(base_positions)} location markers", 40)
            
            # Find all data markers
            longitude_positions = self.find_pattern_positions(self.MARKERS['longitude'])
            latitude_positions = self.find_pattern_positions(self.MARKERS['latitude'])
            timestamp_positions = self.find_pattern_positions(self.MARKERS['timestamp'])
            
            if progress_callback:
                progress_callback("Extracting GPS data...", 50)
            
            # Clear previous locations
            self.locations = []
            entries = []
            
            # Extract data for each base position
            for i, base_pos in enumerate(base_positions):
                # Find longitude
                long_pos = self.find_valid_marker(
                    base_pos, longitude_positions, 
                    self.MAX_LOCATION_DISTANCE, self.MIN_MARKER_SEPARATION
                )
                longitude = self.clean_value(
                    self.extract_data_at_offset(long_pos, self.LONGITUDE_OFFSET) 
                    if long_pos else b''
                )
                
                # Find latitude
                lat_pos = self.find_valid_marker(
                    base_pos, latitude_positions,
                    self.MAX_LOCATION_DISTANCE, self.MIN_MARKER_SEPARATION
                )
                latitude = self.clean_value(
                    self.extract_data_at_offset(lat_pos, self.LATITUDE_OFFSET)
                    if lat_pos else b''
                )
                
                # Find timestamp
                time_pos = self.find_valid_marker(
                    base_pos, timestamp_positions,
                    self.MAX_TIMESTAMP_DISTANCE, self.MIN_MARKER_SEPARATION
                )
                timestamp = self.clean_value(
                    self.extract_data_at_offset(time_pos, self.TIMESTAMP_OFFSET)
                    if time_pos else b''
                )
                
                # Store the extracted data
                location_data = LocationData(
                    longitude=longitude,
                    latitude=latitude,
                    timestamp=timestamp,
                    offset=base_pos
                )
                self.locations.append(location_data)
                
                # Validate and create GPSEntry
                if self.validate_coordinates(location_data):
                    timestamp_str = self.format_timestamp(location_data.timestamp)
                    if timestamp_str and 'ERROR' not in timestamp_str:
                        entry = GPSEntry(
                            lat=float(location_data.latitude),
                            long=float(location_data.longitude),
                            timestamp=timestamp_str,
                            extra_data={'offset': base_pos}
                        )
                        entries.append(entry)
                
                if progress_callback and len(base_positions) > 0:
                    progress = 50 + (30 * (i + 1) // len(base_positions))
                    progress_callback(f"Processing location {i+1}/{len(base_positions)}", progress)
            
            if progress_callback:
                progress_callback("Processing complete!", 90)
            
            return entries, None
            
        except FileNotFoundError:
            return [], f"File not found: {file_path}"
        except Exception as e:
            return [], f"Error processing file: {str(e)}"
    
    def find_pattern_positions(self, patterns: List[bytes]) -> List[int]:
        """Find all positions of given byte patterns in the data."""
        positions = []
        for pattern in patterns:
            positions.extend([m.start() for m in re.finditer(re.escape(pattern), self.data)])
        return sorted(positions)
    
    def extract_data_at_offset(self, position: int, offset: int, length: int = 12) -> bytes:
        """Extract data at a specific position with given offset."""
        if position is None:
            return b''
        start = position + offset
        end = start + length
        if end <= len(self.data):
            return self.data[start:end]
        return b''
    
    def find_valid_marker(self, base_position: int, marker_positions: List[int], 
                         max_distance: int, min_separation: int) -> Optional[int]:
        """Find a valid marker position based on distance and separation criteria."""
        for i, marker_pos in enumerate(marker_positions):
            distance = abs(marker_pos - base_position)
            
            # Check if marker is within acceptable distance
            if distance < max_distance:
                # Check minimum separation from previous marker
                if i > 0 and (marker_pos - marker_positions[i-1]) < min_separation:
                    continue
                return marker_pos
        return None
    
    def clean_value(self, value: bytes) -> str:
        """Clean and format extracted byte values."""
        if not value or value == b'':
            return "0"
        
        # Convert to string and clean
        str_value = value.decode('utf-8', errors='ignore')
        
        # Remove everything after '' delimiter if present
        if "''" in str_value:
            str_value = str_value.split("''")[0]
        
        # Keep only numbers, dots, and minus signs
        cleaned = re.sub(r'[^\d.-]+', '', str_value)
        
        return cleaned if cleaned else "0"
    
    def validate_coordinates(self, location: LocationData) -> bool:
        """Validate if coordinates are reasonable GPS values."""
        try:
            if location.longitude == "0" or location.latitude == "0":
                return False
            
            lon = float(location.longitude)
            lat = float(location.latitude)
            
            # Basic GPS coordinate validation
            if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                return False
            
            # Also validate timestamp is within reasonable range
            timestamp_str = self.format_timestamp(location.timestamp)
            if 'ERROR' in timestamp_str:
                return False
                
            return True
        except ValueError:
            pass
        
        return False
    
    def format_timestamp(self, timestamp: str) -> str:
        """Format timestamp as datetime string."""
        try:
            if timestamp and timestamp != "0":
                # Pad timestamp to 13 characters (milliseconds)
                ts_str = timestamp.ljust(13, '0')
                # Convert to float (seconds with milliseconds)
                ts = int(ts_str) / 1000.0
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                
                # Check if date is after 2060
                if dt.year > 2060:
                    # Try to fix by removing last char and prepending '1'
                    if len(timestamp) >= 2:
                        fixed_timestamp = '1' + timestamp[:-1]
                        # Ensure it's 13 characters
                        if len(fixed_timestamp) < 13:
                            fixed_timestamp = fixed_timestamp.ljust(13, '0')
                        elif len(fixed_timestamp) > 13:
                            fixed_timestamp = fixed_timestamp[:13]
                        
                        # Try again with fixed timestamp
                        ts_fixed = int(fixed_timestamp) / 1000.0
                        dt_fixed = datetime.fromtimestamp(ts_fixed, tz=timezone.utc)
                        
                        # Check if fixed date is valid
                        if dt_fixed.year < 2010:
                            return 'DATE BEFORE 2010 ERROR'
                        elif dt_fixed.year > 2060:
                            return 'DATE AFTER 2060 ERROR'
                        else:
                            # Fixed successfully
                            return dt_fixed.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                    else:
                        return 'DATE AFTER 2060 ERROR'
                
                # Check if date is before 2010
                elif dt.year < 2010:
                    return 'DATE BEFORE 2010 ERROR'
                
                # Date is valid
                return dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        except (ValueError, OSError):
            pass
        return ''