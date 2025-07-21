import re
import struct
from datetime import datetime, timezone
from typing import List, Tuple, Optional, Any
from src.core.base_decoder import BaseDecoder, GPSEntry
import logging
import time

# Setup logger for this module
logger = logging.getLogger(__name__)

class OnStarDecoder(BaseDecoder):
    def __init__(self):
        super().__init__()
        # GPS epoch start: January 6, 1980 00:00:00 UTC (first Sunday of 1980)
        self.gps_epoch = datetime(1980, 1, 6, 0, 0, 0, tzinfo=timezone.utc)
        self._logger.info(f"OnStarDecoder initialized with GPS epoch: {self.gps_epoch}")
    
    def get_name(self) -> str:
        return "OnStar Gen 10+"
    
    def get_supported_extensions(self) -> List[str]:
        extensions = ['.CE0', '.bin', '.001', '.USER']
        self._logger.debug(f"Supported extensions: {extensions}")
        return extensions
    
    def get_dropzone_text(self) -> str:
        return "Drop your OnStar NAND binary\nhere or click to browse"

    def get_xlsx_headers(self) -> List[str]:
        headers = ['Latitude', 'Longitude', 'Year (UTC)', 'Month (UTC)', 'Day (UTC)', 'Hour (UTC)', 'Minute (UTC)', 
            'Epoch-Dervived Timestamp (UTC)', '', '', '', '', '', '', 'Latitude (Raw Hex)', 'Longitude (Raw Hex)']
        self._logger.debug(f"XLSX headers: {len(headers)} columns")
        return headers
    
    def format_entry_for_xlsx(self, entry: GPSEntry) -> List[Any]:
        """Format a GPSEntry into a row for the XLSX file"""
        self._logger.debug(f"Formatting entry for XLSX: lat={entry.latitude}, lon={entry.longitude}")
        
        row = [
            entry.latitude if entry.latitude != 0 else 'ERROR',
            entry.longitude if entry.longitude != 0 else 'ERROR',
            entry.extra_data.get('utc_year', 'ERROR'),
            entry.extra_data.get('utc_month', 'ERROR'),
            entry.extra_data.get('utc_day', 'ERROR'),
            entry.extra_data.get('utc_hour', 'ERROR'),
            entry.extra_data.get('utc_min', 'ERROR'),
            entry.timestamp if entry.timestamp else 'ERROR',
            '', '', '', '', '', '',  # Six blank columns
            entry.extra_data.get('lat_hex', ''),
            entry.extra_data.get('lon_hex', '')
        ]
        
        return row
    
    def extract_gps_data(self, file_path: str, progress_callback=None, stop_event=None) -> Tuple[List[GPSEntry], Optional[str]]:
        """Extract GPS data from OnStar binary file, with support for stopping."""
        start_time = time.time()
        self._log_extraction_start(file_path)
        
        try:
            # Check file size
            import os
            file_size = os.path.getsize(file_path)
            self._logger.info(f"Processing OnStar file: {file_path} (Size: {file_size/1024/1024:.2f} MB)")
            
            if progress_callback:
                progress_callback("Reading binary file...", 10)
                self._log_progress("Reading binary file", 10)
                
            if stop_event and stop_event.is_set():
                self._logger.warning("Processing stopped by user before file read")
                return [], "Processing stopped by user."

            self._logger.debug("Opening file for binary read")
            with open(file_path, 'rb') as f:
                data = f.read()
            
            self._logger.info(f"Successfully read {len(data)} bytes from file")

            if progress_callback:
                progress_callback("Finding GPS data blocks...", 30)
                self._log_progress("Finding GPS data blocks", 30)
                
            if stop_event and stop_event.is_set():
                self._logger.warning("Processing stopped by user before GPS block search")
                return [], "Processing stopped by user."

            self._logger.debug("Starting GPS block search")
            gps_blocks = self.find_gps_blocks_binary(data)
            self._logger.info(f"Found {len(gps_blocks)} potential GPS data blocks")

            if progress_callback:
                progress_callback(f"Parsing {len(gps_blocks)} GPS blocks...", 50)
                self._log_progress(f"Parsing {len(gps_blocks)} GPS blocks", 50)
                
            if stop_event and stop_event.is_set():
                self._logger.warning("Processing stopped by user before parsing")
                return [], "Processing stopped by user."

            entries = []
            valid_entries = 0
            invalid_entries = 0
            
            for i, block in enumerate(gps_blocks):
                if stop_event and stop_event.is_set():
                    self._logger.warning(f"Processing stopped by user at block {i}/{len(gps_blocks)}")
                    return entries, "Processing stopped by user."

                self._logger.debug(f"Parsing block {i+1}/{len(gps_blocks)}")
                entry_data = self.parse_gps_block(block)
                
                if entry_data and self.is_valid_entry(entry_data):
                    gps_entry = GPSEntry(
                        latitude=entry_data['lat'] if entry_data['lat'] != 'ERROR' else 0,
                        longitude=entry_data['long'] if entry_data['long'] != 'ERROR' else 0,
                        timestamp=entry_data['timestamp_time'] if entry_data['timestamp_time'] != 'ERROR' else '',
                        extra_data={
                            'utc_year': entry_data.get('utc_year', ''),
                            'utc_month': entry_data.get('utc_month', ''),
                            'utc_day': entry_data.get('utc_day', ''),
                            'utc_hour': entry_data.get('utc_hour', ''),
                            'utc_min': entry_data.get('utc_min', ''),
                            'lat_hex': entry_data.get('lat_hex', ''),
                            'lon_hex': entry_data.get('lon_hex', '')
                        }
                    )
                    entries.append(gps_entry)
                    valid_entries += 1
                else:
                    invalid_entries += 1
                    self._logger.debug(f"Block {i+1} contained invalid or incomplete data")

                if progress_callback and len(gps_blocks) > 0:
                    progress = 50 + (30 * (i + 1) // len(gps_blocks))
                    progress_callback(f"Parsing block {i+1}/{len(gps_blocks)}", progress)
                    
                    # Log progress every 10%
                    if i % max(1, len(gps_blocks) // 10) == 0:
                        self._log_progress(f"Parsing blocks ({i+1}/{len(gps_blocks)})", progress)

            elapsed_time = time.time() - start_time
            self._logger.info(f"Parsing complete. Valid entries: {valid_entries}, Invalid entries: {invalid_entries}")
            
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
    
    def find_gps_blocks_binary(self, data):
        """Find GPS data blocks in binary data"""
        self._logger.debug("Starting binary search for GPS blocks")
        blocks = []
        text_data = data.decode('latin-1', errors='ignore')
        
        gps_patterns = [
            b'gps_tow=',
            b'gps_week=', 
            b'utc_year=',
            b'lat=',
            b'lon='
        ]
        
        self._logger.debug(f"Searching for patterns: {[p.decode('latin-1') for p in gps_patterns]}")
        
        keyword_positions = []
        for pattern in gps_patterns:
            pattern_str = pattern.decode('latin-1')
            matches = list(re.finditer(re.escape(pattern_str), text_data))
            self._logger.debug(f"Found {len(matches)} matches for pattern '{pattern_str}'")
            
            for match in matches:
                keyword_positions.append(match.start())
        
        if not keyword_positions:
            self._logger.warning("No GPS pattern matches found in file")
            return blocks
        
        keyword_positions.sort()
        self._logger.info(f"Found {len(keyword_positions)} total keyword positions")
        
        # Group nearby keywords into blocks
        i = 0
        while i < len(keyword_positions):
            block_start = keyword_positions[i]
            block_end = block_start + 200
            j = i + 1
            
            # Group keywords within 1000 bytes of each other
            while j < len(keyword_positions) and keyword_positions[j] - block_start < 1000:
                block_end = max(block_end, keyword_positions[j] + 200)
                j += 1
            
            start_pos = max(0, block_start - 50)
            end_pos = min(len(text_data), block_end + 50)
            block_text = text_data[start_pos:end_pos]
            blocks.append(block_text)
            
            self._logger.debug(f"Created block {len(blocks)}: positions {start_pos}-{end_pos} "
                             f"(contains {j-i} keywords)")
            i = j
        
        self._logger.info(f"Grouped keywords into {len(blocks)} blocks")
        return blocks
    
    def parse_gps_block(self, block_text):
        """Parse a GPS data block into structured data"""
        self._logger.debug(f"Parsing GPS block of length {len(block_text)}")
        
        entry = {
            'lat': 'ERROR',
            'long': 'ERROR', 
            'utc_year': '',
            'utc_month': '',
            'utc_day': '',
            'utc_hour': '',
            'utc_min': '',
            'timestamp_time': 'ERROR',
            'lat_hex': '',
            'lon_hex': ''
        }
        
        try:
            # Extract various fields
            gps_tow = self.extract_number_flexible(block_text, [r'gps_tow=(\d+)', r'tow=(\d+)'])
            gps_week = self.extract_number_flexible(block_text, [r'gps_week=(\d+)', r'week=(\d+)'])
            utc_year = self.extract_number_flexible(block_text, [r'utc_year=(\d+)', r'year=(\d{4})'])
            utc_month = self.extract_number_flexible(block_text, [r'utc_month=(\d+)', r'month=(\d+)'])
            utc_day = self.extract_number_flexible(block_text, [r'utc_day=(\d+)', r'day=(\d+)'])
            utc_hour = self.extract_number_flexible(block_text, [r'utc_hour=(\d+)', r'hour=(\d+)'])
            utc_min = self.extract_number_flexible(block_text, [r'utc_min=(\d+)', r'min=(\d+)'])
            
            self._logger.debug(f"Extracted time components: year={utc_year}, month={utc_month}, "
                             f"day={utc_day}, hour={utc_hour}, min={utc_min}")
            self._logger.debug(f"GPS time: week={gps_week}, tow={gps_tow}")
            
            entry['utc_year'] = utc_year if utc_year is not None else ''
            entry['utc_month'] = utc_month if utc_month is not None else ''
            entry['utc_day'] = utc_day if utc_day is not None else ''
            entry['utc_hour'] = utc_hour if utc_hour is not None else ''
            entry['utc_min'] = utc_min if utc_min is not None else ''
            
            # Extract hex coordinates
            lat_hex = self.extract_hex_flexible(block_text, [r'lat=([0-9A-Fa-f]{16})', r'lat=([0-9A-Fa-f\s]{16,})'])
            lon_hex = self.extract_hex_flexible(block_text, [r'lon=([0-9A-Fa-f]{16})', r'lon=([0-9A-Fa-f\s]{16,})'])
            
            self._logger.debug(f"Extracted hex values: lat={lat_hex[:16] if lat_hex else 'None'}..., "
                             f"lon={lon_hex[:16] if lon_hex else 'None'}...")
            
            entry['lat_hex'] = lat_hex if lat_hex else ''
            entry['lon_hex'] = lon_hex if lon_hex else ''
            
            # Convert GPS time to timestamp
            if gps_tow is not None and gps_week is not None:
                try:
                    if 0 <= gps_tow <= 604800000 and 0 <= gps_week <= 4000:
                        gps_tow_sec = gps_tow / 1000.0
                        gps_week_sec = gps_week * 604800
                        total_seconds = gps_week_sec + gps_tow_sec
                        gps_timestamp = self.gps_epoch.timestamp() + total_seconds
                        dt = datetime.fromtimestamp(gps_timestamp, tz=timezone.utc)
                        entry['timestamp_time'] = dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                        
                        self._logger.debug(f"Converted GPS time to: {entry['timestamp_time']}")
                        
                        # Check if date is before 2010
                        if dt.year < 2010:
                            self._logger.warning(f"Date before 2010: {dt.year}")
                            entry['timestamp_time'] = 'DATE BEFORE 2010 ERROR'
                except Exception as e:
                    self._logger.error(f"Error converting GPS time: {e}")
                    pass
            
            # Convert hex coordinates to decimal
            if lat_hex:
                try:
                    clean_hex = re.sub(r'[^0-9A-Fa-f]', '', lat_hex)
                    if len(clean_hex) == 16:
                        lat_bytes = bytes.fromhex(clean_hex)
                        lat_raw = struct.unpack('<d', lat_bytes)[0]
                        lat_decimal = lat_raw / 10000000.0
                        if -90 <= lat_decimal <= 90:
                            entry['lat'] = lat_decimal
                            self._logger.debug(f"Converted latitude: {lat_decimal}")
                        else:
                            self._logger.warning(f"Latitude out of range: {lat_decimal}")
                except Exception as e:
                    self._logger.error(f"Error converting latitude hex: {e}")
                    entry['lat'] = 'ERROR'
            
            if lon_hex:
                try:
                    clean_hex = re.sub(r'[^0-9A-Fa-f]', '', lon_hex)
                    if len(clean_hex) == 16:
                        lon_bytes = bytes.fromhex(clean_hex)
                        lon_raw = struct.unpack('<d', lon_bytes)[0]
                        lon_decimal = lon_raw / 10000000.0
                        if -180 <= lon_decimal <= 180:
                            entry['long'] = lon_decimal
                            self._logger.debug(f"Converted longitude: {lon_decimal}")
                        else:
                            self._logger.warning(f"Longitude out of range: {lon_decimal}")
                except Exception as e:
                    self._logger.error(f"Error converting longitude hex: {e}")
                    entry['long'] = 'ERROR'

            # Format hex values for display
            if lat_hex:
                entry['lat_hex'] = format_hex_with_spaces(lat_hex)
            if lon_hex:
                entry['lon_hex'] = format_hex_with_spaces(lon_hex)
            
            self._logger.debug(f"Block parsing complete. Valid coordinates: "
                             f"{entry['lat'] != 'ERROR' and entry['long'] != 'ERROR'}")
            return entry
            
        except Exception as e:
            self._logger.error(f"Unexpected error parsing GPS block: {e}", exc_info=True)
            return None
    
    def extract_number_flexible(self, text, patterns):
        """Extract a number using multiple regex patterns"""
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    value = int(match.group(1))
                    self._logger.debug(f"Pattern '{pattern}' matched: {value}")
                    return value
                except Exception as e:
                    self._logger.debug(f"Failed to parse number from pattern '{pattern}': {e}")
                    continue
        return None
    
    def extract_hex_flexible(self, text, patterns):
        """Extract hex value using multiple regex patterns"""
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                hex_val = match.group(1)
                clean_hex = re.sub(r'[^0-9A-Fa-f]', '', hex_val)
                if len(clean_hex) >= 16:
                    result = clean_hex[:16]
                    self._logger.debug(f"Pattern '{pattern}' matched hex value (first 16 chars)")
                    return result
        return None
    
    def is_valid_entry(self, entry):
        """Check if entry has at least some valid data"""
        if not entry:
            self._logger.debug("Entry is None")
            return False
        
        # Check coordinates
        if entry['lat'] == 'ERROR' or entry['long'] == 'ERROR':
            self._logger.debug("Invalid coordinates detected")
            return False
        
        # Check for null island
        if isinstance(entry['lat'], (int, float)) and isinstance(entry['long'], (int, float)):
            if entry['lat'] == 0 and entry['long'] == 0:
                self._logger.debug("Null island coordinates detected (0,0)")
                return False
        
        # Check time data
        has_utc = all(entry.get(k) not in ('', None) for k in ['utc_year', 'utc_month', 'utc_day', 'utc_hour', 'utc_min'])
        if not has_utc and entry['timestamp_time'] == 'ERROR':
            self._logger.debug("No valid time data found")
            return False
        
        # Filter out dates before 2010
        if entry['timestamp_time'] != 'ERROR':
            try:
                timestamp_year = int(entry['timestamp_time'][:4])
                if timestamp_year < 2010:
                    self._logger.debug(f"Date too old: {timestamp_year}")
                    return False
            except (ValueError, TypeError) as e:
                self._logger.debug(f"Failed to parse year from timestamp: {e}")
                pass
        
        self._logger.debug("Entry passed validation")
        return True

def format_hex_with_spaces(hex_str):
    """Format hex string with spaces between bytes"""
    result = ' '.join(hex_str[i:i+2] for i in range(0, len(hex_str), 2))
    logger.debug(f"Formatted hex string: {len(hex_str)} chars -> {len(result)} chars with spaces")
    return result
