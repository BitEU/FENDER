import re
import struct
from datetime import datetime, timezone
from typing import List, Tuple, Optional, Any
from base_decoder import BaseDecoder, GPSEntry

class OnStarDecoder(BaseDecoder):
    def __init__(self):
        # GPS epoch start: January 6, 1980 00:00:00 UTC (first Sunday of 1980)
        self.gps_epoch = datetime(1980, 1, 6, 0, 0, 0, tzinfo=timezone.utc)
    
    def get_name(self) -> str:
        return "OnStar v10, v11"
    
    def get_supported_extensions(self) -> List[str]:
        return ['.CE0']  # Support numbered CE0 files
    
    def get_xlsx_headers(self) -> List[str]:
        return ['lat', 'long', 'utc_year', 'utc_month', 'utc_day', 'utc_hour', 'utc_min', 
                'timestamp_time', '', '', '', '', '', '', 'lat_hex', 'lon_hex']
    
    def format_entry_for_xlsx(self, entry: GPSEntry) -> List[Any]:
        """Format a GPSEntry into a row for the XLSX file"""
        return [
            entry.lat if entry.lat != 0 else 'ERROR',
            entry.long if entry.long != 0 else 'ERROR',
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
    
    def extract_gps_data(self, file_path: str, progress_callback=None) -> Tuple[List[GPSEntry], Optional[str]]:
        """Extract GPS data from OnStar binary file"""
        try:
            if progress_callback:
                progress_callback("Reading binary file...", 10)
            
            with open(file_path, 'rb') as f:
                data = f.read()
            
            if progress_callback:
                progress_callback("Finding GPS data blocks...", 30)
            
            gps_blocks = self.find_gps_blocks_binary(data)
            
            if progress_callback:
                progress_callback(f"Parsing {len(gps_blocks)} GPS blocks...", 50)
            
            entries = []
            for i, block in enumerate(gps_blocks):
                entry_data = self.parse_gps_block(block)
                if entry_data and self.is_valid_entry(entry_data):
                    # Convert to standard GPSEntry
                    gps_entry = GPSEntry(
                        lat=entry_data['lat'] if entry_data['lat'] != 'ERROR' else 0,
                        long=entry_data['long'] if entry_data['long'] != 'ERROR' else 0,
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
                
                if progress_callback and len(gps_blocks) > 0:
                    progress = 50 + (30 * (i + 1) // len(gps_blocks))
                    progress_callback(f"Parsing block {i+1}/{len(gps_blocks)}", progress)
            
            if progress_callback:
                progress_callback("Processing complete!", 90)
            
            return entries, None
            
        except FileNotFoundError:
            return [], f"File not found: {file_path}"
        except Exception as e:
            return [], f"Error processing file: {str(e)}"
    
    def find_gps_blocks_binary(self, data):
        """Find GPS data blocks in binary data"""
        blocks = []
        text_data = data.decode('latin-1', errors='ignore')
        
        gps_patterns = [
            b'gps_tow=',
            b'gps_week=', 
            b'utc_year=',
            b'lat=',
            b'lon='
        ]
        
        keyword_positions = []
        for pattern in gps_patterns:
            pattern_str = pattern.decode('latin-1')
            for match in re.finditer(re.escape(pattern_str), text_data):
                keyword_positions.append(match.start())
        
        if not keyword_positions:
            return blocks
        
        keyword_positions.sort()
        
        i = 0
        while i < len(keyword_positions):
            block_start = keyword_positions[i]
            block_end = block_start + 200
            j = i + 1
            while j < len(keyword_positions) and keyword_positions[j] - block_start < 1000:
                block_end = max(block_end, keyword_positions[j] + 200)
                j += 1
            
            start_pos = max(0, block_start - 50)
            end_pos = min(len(text_data), block_end + 50)
            block_text = text_data[start_pos:end_pos]
            blocks.append(block_text)
            i = j
        
        return blocks
    
    def parse_gps_block(self, block_text):
        """Parse a GPS data block into structured data"""
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
            gps_tow = self.extract_number_flexible(block_text, [r'gps_tow=(\d+)', r'tow=(\d+)'])
            gps_week = self.extract_number_flexible(block_text, [r'gps_week=(\d+)', r'week=(\d+)'])
            utc_year = self.extract_number_flexible(block_text, [r'utc_year=(\d+)', r'year=(\d{4})'])
            utc_month = self.extract_number_flexible(block_text, [r'utc_month=(\d+)', r'month=(\d+)'])
            utc_day = self.extract_number_flexible(block_text, [r'utc_day=(\d+)', r'day=(\d+)'])
            utc_hour = self.extract_number_flexible(block_text, [r'utc_hour=(\d+)', r'hour=(\d+)'])
            utc_min = self.extract_number_flexible(block_text, [r'utc_min=(\d+)', r'min=(\d+)'])
            
            entry['utc_year'] = utc_year if utc_year is not None else ''
            entry['utc_month'] = utc_month if utc_month is not None else ''
            entry['utc_day'] = utc_day if utc_day is not None else ''
            entry['utc_hour'] = utc_hour if utc_hour is not None else ''
            entry['utc_min'] = utc_min if utc_min is not None else ''
            
            lat_hex = self.extract_hex_flexible(block_text, [r'lat=([0-9A-Fa-f]{16})', r'lat=([0-9A-Fa-f\s]{16,})'])
            lon_hex = self.extract_hex_flexible(block_text, [r'lon=([0-9A-Fa-f]{16})', r'lon=([0-9A-Fa-f\s]{16,})'])
            
            entry['lat_hex'] = lat_hex if lat_hex else ''
            entry['lon_hex'] = lon_hex if lon_hex else ''
            
            if gps_tow is not None and gps_week is not None:
                try:
                    if 0 <= gps_tow <= 604800000 and 0 <= gps_week <= 4000:
                        gps_tow_sec = gps_tow / 1000.0
                        gps_week_sec = gps_week * 604800
                        total_seconds = gps_week_sec + gps_tow_sec
                        gps_timestamp = self.gps_epoch.timestamp() + total_seconds
                        dt = datetime.fromtimestamp(gps_timestamp, tz=timezone.utc)
                        entry['timestamp_time'] = dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                        
                        # Check if date is before 2010
                        if dt.year < 2010:
                            entry['timestamp_time'] = 'DATE BEFORE 2010 ERROR'
                except Exception:
                    pass
            
            if lat_hex:
                try:
                    clean_hex = re.sub(r'[^0-9A-Fa-f]', '', lat_hex)
                    if len(clean_hex) == 16:
                        lat_bytes = bytes.fromhex(clean_hex)
                        lat_raw = struct.unpack('<d', lat_bytes)[0]
                        lat_decimal = lat_raw / 10000000.0
                        if -90 <= lat_decimal <= 90:
                            entry['lat'] = lat_decimal
                except Exception:
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
                except Exception:
                    entry['long'] = 'ERROR'
            
            return entry
        except Exception:
            return None
    
    def extract_number_flexible(self, text, patterns):
        """Extract a number using multiple regex patterns"""
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    value = int(match.group(1))
                    return value
                except:
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
                    return clean_hex[:16]
        return None
    
    def is_valid_entry(self, entry):
        """Check if entry has at least some valid data"""
        if not entry:
            return False
        
        if entry['lat'] == 'ERROR' or entry['long'] == 'ERROR':
            return False
        
        has_utc = all(entry.get(k) not in ('', None) for k in ['utc_year', 'utc_month', 'utc_day', 'utc_hour', 'utc_min'])
        if not has_utc and entry['timestamp_time'] == 'ERROR':
            return False
        
        # Filter out dates before 2010
        if entry['timestamp_time'] != 'ERROR':
            try:
                timestamp_year = int(entry['timestamp_time'][:4])
                if timestamp_year < 2010:
                    return False
            except (ValueError, TypeError):
                pass
        
        return True