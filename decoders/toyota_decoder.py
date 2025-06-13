import re
from datetime import datetime, timezone
from typing import List, Tuple, Optional, Any
from dataclasses import dataclass
from base_decoder import BaseDecoder, GPSEntry
import logging
import time
import os

# Setup logger for this module
logger = logging.getLogger(__name__)

@dataclass
class LocationData:
    """Stores extracted location and time data."""
    longitude: str
    latitude: str
    timestamp: str
    offset: int

class ToyotaDecoder(BaseDecoder):
    def __init__(self):
        super().__init__()
        
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
        
        self._logger.info("ToyotaDecoder initialized with configuration:")
        self._logger.debug(f"  Longitude offset: {self.LONGITUDE_OFFSET}")
        self._logger.debug(f"  Latitude offset: {self.LATITUDE_OFFSET}")
        self._logger.debug(f"  Timestamp offset: {self.TIMESTAMP_OFFSET}")
        self._logger.debug(f"  Max location distance: {self.MAX_LOCATION_DISTANCE}")
        self._logger.debug(f"  Max timestamp distance: {self.MAX_TIMESTAMP_DISTANCE}")
        self._logger.debug(f"  Min marker separation: {self.MIN_MARKER_SEPARATION}")
        self._logger.debug(f"  Number of timestamp patterns: {len(self.MARKERS['timestamp'])}")
    
    def get_name(self) -> str:
        return "Toyota TL19"
    
    def get_supported_extensions(self) -> List[str]:
        extensions = ['.CE0', '.bin']
        self._logger.debug(f"Supported extensions: {extensions}")
        return extensions
    
    def get_dropzone_text(self) -> str:
        return "Drop your Toyota NAND binary\nhere or click to browse"

    def get_xlsx_headers(self) -> List[str]:
        # Toyota format has fewer columns than OnStar
        headers = ['Latitude', 'Longitude', 'Timestamp (UTC)'] + [''] * 11  # 11 blank columns
        self._logger.debug(f"XLSX headers: {len(headers)} columns (3 data + 11 blank)")
        return headers
    
    def format_entry_for_xlsx(self, entry: GPSEntry) -> List[Any]:
        """Format a GPSEntry into a row for the XLSX file"""
        self._logger.debug(f"Formatting entry for XLSX: lat={entry.latitude}, lon={entry.longitude}")
        
        row = [
            entry.latitude if entry.latitude != 0 else 'ERROR',
            entry.longitude if entry.longitude != 0 else 'ERROR',
            entry.timestamp if entry.timestamp else 'ERROR',
            '', '', '', '', '', '', '', '', '', '', ''  # Eleven blank columns
        ]
        
        return row
    
    def extract_gps_data(self, file_path: str, progress_callback=None, stop_event=None) -> Tuple[List[GPSEntry], Optional[str]]:
        """Extract GPS data from Toyota binary file, with support for stopping."""
        start_time = time.time()
        self._log_extraction_start(file_path)
        
        try:
            # Check file size
            file_size = os.path.getsize(file_path)
            self._logger.info(f"Processing Toyota file: {file_path} (Size: {file_size/1024/1024:.2f} MB)")
            
            if progress_callback:
                progress_callback("Reading binary file...", 10)
                self._log_progress("Reading binary file", 10)
                
            if stop_event and stop_event.is_set():
                self._logger.warning("Processing stopped by user before file read")
                return [], "Processing stopped by user."

            self._logger.debug("Opening file for binary read")
            with open(file_path, 'rb') as f:
                self.data = f.read()
            
            self._logger.info(f"Successfully read {len(self.data)} bytes from file")

            if progress_callback:
                progress_callback("Finding GPS data blocks...", 30)
                self._log_progress("Finding GPS data blocks", 30)
                
            if stop_event and stop_event.is_set():
                self._logger.warning("Processing stopped by user before marker search")
                return [], "Processing stopped by user."

            # Find all marker positions
            self._logger.debug("Searching for location base markers")
            base_positions = self.find_pattern_positions([self.MARKERS['location_base']])
            self._logger.info(f"Found {len(base_positions)} location base markers")

            if progress_callback:
                progress_callback(f"Found {len(base_positions)} location markers", 40)
                self._log_progress(f"Found {len(base_positions)} location markers", 40)
                
            if stop_event and stop_event.is_set():
                self._logger.warning("Processing stopped by user before coordinate search")
                return [], "Processing stopped by user."

            # Find all coordinate and timestamp markers
            self._logger.debug("Searching for longitude markers")
            longitude_positions = self.find_pattern_positions(self.MARKERS['longitude'])
            self._logger.info(f"Found {len(longitude_positions)} longitude markers")
            
            self._logger.debug("Searching for latitude markers")
            latitude_positions = self.find_pattern_positions(self.MARKERS['latitude'])
            self._logger.info(f"Found {len(latitude_positions)} latitude markers")
            
            self._logger.debug("Searching for timestamp markers")
            timestamp_positions = self.find_pattern_positions(self.MARKERS['timestamp'])
            self._logger.info(f"Found {len(timestamp_positions)} timestamp markers")

            if progress_callback:
                progress_callback("Extracting GPS data...", 50)
                self._log_progress("Extracting GPS data", 50)
                
            if stop_event and stop_event.is_set():
                self._logger.warning("Processing stopped by user before data extraction")
                return [], "Processing stopped by user."

            self.locations = []
            entries = []
            valid_entries = 0
            invalid_entries = 0

            for i, base_pos in enumerate(base_positions):
                if stop_event and stop_event.is_set():
                    self._logger.warning(f"Processing stopped by user at location {i}/{len(base_positions)}")
                    return entries, "Processing stopped by user."

                self._logger.debug(f"Processing location marker {i+1}/{len(base_positions)} at offset {base_pos}")
                
                # Find longitude
                long_pos = self.find_valid_marker(
                    base_pos, longitude_positions, 
                    self.MAX_LOCATION_DISTANCE, self.MIN_MARKER_SEPARATION
                )
                if long_pos:
                    self._logger.debug(f"  Found longitude marker at offset {long_pos} (distance: {abs(long_pos - base_pos)})")
                else:
                    self._logger.debug(f"  No valid longitude marker found")
                    
                longitude = self.clean_value(
                    self.extract_data_at_offset(long_pos, self.LONGITUDE_OFFSET) 
                    if long_pos else b''
                )
                
                # Find latitude
                lat_pos = self.find_valid_marker(
                    base_pos, latitude_positions,
                    self.MAX_LOCATION_DISTANCE, self.MIN_MARKER_SEPARATION
                )
                if lat_pos:
                    self._logger.debug(f"  Found latitude marker at offset {lat_pos} (distance: {abs(lat_pos - base_pos)})")
                else:
                    self._logger.debug(f"  No valid latitude marker found")
                    
                latitude = self.clean_value(
                    self.extract_data_at_offset(lat_pos, self.LATITUDE_OFFSET)
                    if lat_pos else b''
                )
                
                # Find timestamp
                time_pos = self.find_valid_marker(
                    base_pos, timestamp_positions,
                    self.MAX_TIMESTAMP_DISTANCE, self.MIN_MARKER_SEPARATION
                )
                if time_pos:
                    self._logger.debug(f"  Found timestamp marker at offset {time_pos} (distance: {abs(time_pos - base_pos)})")
                else:
                    self._logger.debug(f"  No valid timestamp marker found")
                    
                timestamp = self.clean_value(
                    self.extract_data_at_offset(time_pos, self.TIMESTAMP_OFFSET)
                    if time_pos else b''
                )
                
                self._logger.debug(f"  Extracted values - lon: {longitude}, lat: {latitude}, time: {timestamp}")
                
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
                            latitude=float(location_data.latitude),
                            longitude=float(location_data.longitude),
                            timestamp=timestamp_str,
                            extra_data={'offset': base_pos}
                        )
                        entries.append(entry)
                        valid_entries += 1
                        self._logger.debug(f"  Created valid GPS entry #{valid_entries}")
                    else:
                        invalid_entries += 1
                        self._logger.debug(f"  Invalid timestamp: {timestamp_str}")
                else:
                    invalid_entries += 1
                    self._logger.debug(f"  Invalid coordinates")
                
                if progress_callback and len(base_positions) > 0:
                    progress = 50 + (30 * (i + 1) // len(base_positions))
                    progress_callback(f"Processing location {i+1}/{len(base_positions)}", progress)
                    
                    # Log progress every 10%
                    if i % max(1, len(base_positions) // 10) == 0:
                        self._log_progress(f"Processing locations ({i+1}/{len(base_positions)})", progress)

            elapsed_time = time.time() - start_time
            self._logger.info(f"Extraction complete. Valid entries: {valid_entries}, Invalid entries: {invalid_entries}")
            
            if progress_callback:
                progress_callback("Processing complete!", 90)
                self._log_progress("Processing complete", 90)

            self._log_extraction_complete(len(entries), elapsed_time)
            return entries, None

        except FileNotFoundError:
            error_msg = f"File not found: {file_path}"
            self._log_extraction_error(error_msg)
            return [], error_msg
        except PermissionError:
            error_msg = f"Permission denied accessing file: {file_path}"
            self._log_extraction_error(error_msg)
            return [], error_msg
        except Exception as e:
            error_msg = f"Error processing file: {str(e)}"
            self._logger.error(f"Unexpected error during extraction: {e}", exc_info=True)
            self._log_extraction_error(error_msg)
            return [], error_msg
    
    def find_pattern_positions(self, patterns: List[bytes]) -> List[int]:
        """Find all positions of given byte patterns in the data."""
        self._logger.debug(f"Searching for {len(patterns)} patterns in {len(self.data)} bytes")
        
        positions = []
        for pattern in patterns:
            pattern_positions = [m.start() for m in re.finditer(re.escape(pattern), self.data)]
            self._logger.debug(f"  Pattern {pattern.hex()}: found {len(pattern_positions)} matches")
            positions.extend(pattern_positions)
            
        positions_sorted = sorted(positions)
        self._logger.debug(f"Total positions found: {len(positions_sorted)}")
        return positions_sorted
    
    def extract_data_at_offset(self, position: int, offset: int, length: int = 12) -> bytes:
        """Extract data at a specific position with given offset."""
        if position is None:
            return b''
            
        start = position + offset
        end = start + length
        
        if end <= len(self.data):
            extracted = self.data[start:end]
            self._logger.debug(f"Extracted {len(extracted)} bytes from position {position} + offset {offset}")
            return extracted
        else:
            self._logger.warning(f"Attempted to read beyond data bounds: {end} > {len(self.data)}")
            return b''
    
    def find_valid_marker(self, base_position: int, marker_positions: List[int], 
                         max_distance: int, min_separation: int) -> Optional[int]:
        """Find a valid marker position based on distance and separation criteria."""
        self._logger.debug(f"Finding valid marker near position {base_position} "
                         f"(max_distance={max_distance}, min_separation={min_separation})")
        
        valid_candidates = 0
        
        for i, marker_pos in enumerate(marker_positions):
            distance = abs(marker_pos - base_position)
            
            # Check if marker is within acceptable distance
            if distance < max_distance:
                # Check minimum separation from previous marker
                if i > 0 and (marker_pos - marker_positions[i-1]) < min_separation:
                    self._logger.debug(f"  Marker at {marker_pos} rejected: too close to previous "
                                     f"(separation: {marker_pos - marker_positions[i-1]})")
                    continue
                    
                valid_candidates += 1
                self._logger.debug(f"  Valid marker found at {marker_pos} (distance: {distance})")
                return marker_pos
                
        if valid_candidates == 0:
            self._logger.debug(f"  No valid markers found within distance {max_distance}")
            
        return None
    
    def clean_value(self, value: bytes) -> str:
        """Clean and format extracted byte values."""
        if not value or value == b'':
            return "0"
        
        # Convert to string and clean
        try:
            str_value = value.decode('utf-8', errors='ignore')
        except Exception as e:
            self._logger.error(f"Error decoding value: {e}")
            return "0"
        
        original_value = str_value
        
        # Remove everything after '' delimiter if present
        if "''" in str_value:
            str_value = str_value.split("''")[0]
        
        # Keep only numbers, dots, and minus signs
        cleaned = re.sub(r'[^\d.-]+', '', str_value)
        
        if cleaned != original_value:
            self._logger.debug(f"Cleaned value: '{original_value}' -> '{cleaned}'")
        
        return cleaned if cleaned else "0"
    
    def validate_coordinates(self, location: LocationData) -> bool:
        """Validate if coordinates are reasonable GPS values."""
        try:
            if location.longitude == "0" or location.latitude == "0":
                self._logger.debug(f"Invalid coordinates: zero values detected")
                return False
            
            lon = float(location.longitude)
            lat = float(location.latitude)
            
            # Basic GPS coordinate validation
            if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                self._logger.debug(f"Coordinates out of valid range: lat={lat}, lon={lon}")
                return False
            
            # Check for null island
            if lat == 0.0 and lon == 0.0:
                self._logger.debug(f"Null island coordinates detected (0.0, 0.0)")
                return False
            
            # Also validate timestamp is within reasonable range
            timestamp_str = self.format_timestamp(location.timestamp)
            if 'ERROR' in timestamp_str:
                self._logger.debug(f"Invalid timestamp: {timestamp_str}")
                return False
                
            self._logger.debug(f"Coordinates validated successfully: lat={lat}, lon={lon}")
            return True
            
        except ValueError as e:
            self._logger.debug(f"Failed to parse coordinates as floats: {e}")
        
        return False
    
    def format_timestamp(self, timestamp: str) -> str:
        """Format timestamp as datetime string."""
        self._logger.debug(f"Formatting timestamp: '{timestamp}'")
        
        try:
            if timestamp and timestamp != "0":
                # Pad timestamp to 13 characters (milliseconds)
                ts_str = timestamp.ljust(13, '0')
                # Convert to float (seconds with milliseconds)
                ts = int(ts_str) / 1000.0
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                
                self._logger.debug(f"Parsed timestamp: {ts} -> {dt}")
                
                # Check if date is after 2060
                if dt.year > 2060:
                    self._logger.warning(f"Date after 2060: {dt.year}")
                    
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
                        
                        self._logger.debug(f"Attempted fix: {fixed_timestamp} -> {dt_fixed}")
                        
                        # Check if fixed date is valid
                        if dt_fixed.year < 2010:
                            self._logger.warning(f"Fixed date still invalid (before 2010): {dt_fixed.year}")
                            return 'DATE BEFORE 2010 ERROR'
                        elif dt_fixed.year > 2060:
                            self._logger.warning(f"Fixed date still invalid (after 2060): {dt_fixed.year}")
                            return 'DATE AFTER 2060 ERROR'
                        else:
                            # Fixed successfully
                            self._logger.info(f"Successfully fixed timestamp: {dt} -> {dt_fixed}")
                            return dt_fixed.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                    else:
                        return 'DATE AFTER 2060 ERROR'
                
                # Check if date is before 2010
                elif dt.year < 2010:
                    self._logger.warning(f"Date before 2010: {dt.year}")
                    return 'DATE BEFORE 2010 ERROR'
                
                # Date is valid
                formatted = dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                self._logger.debug(f"Successfully formatted timestamp: {formatted}")
                return formatted
                
        except (ValueError, OSError) as e:
            self._logger.error(f"Error formatting timestamp '{timestamp}': {e}")
            
        return ''