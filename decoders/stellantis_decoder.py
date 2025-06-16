import os
import re
import glob
from datetime import datetime, timezone
from typing import List, Tuple, Optional, Any
from pathlib import Path
from base_decoder import BaseDecoder, GPSEntry
import logging
import time

# Setup logger for this module
logger = logging.getLogger(__name__)

class StellantisDecoder(BaseDecoder):
    """
    Stellantis Vehicle Decoder
    Extracts GPS data from Stellantis vehicle log files in various formats
    Supports folder-based input with recursive file discovery
    """
    
    def __init__(self):
        super().__init__()
        
        # Define log file patterns to search for
        self.log_patterns = [
            "**/pas_debug.log.*",
            "**/persistentLogs/AASXMTC/Log*",
            "**/persistentLogs/AlertsService/Log*", 
            "**/Logs/vr/vr_voice_continous.log",
            "**/Logs/Appfw/ams.log",
            "**/Logs/**/*.log*",
            "**/*.log*"
        ]
        
        # GPS data extraction patterns
        self.gps_patterns = {
            # SAL_SDARS_FUEL pattern: Dest Latitude:[40.774902] Dest Longitude:[-74.031372]
            'SAL_SDARS_FUEL': {
                'pattern': r'=SAL_SDARS_FUEL:\s*Dest\s+Latitude:\s*\[([^\]]+)\]\s*Dest\s+Longitude:\s*\[([^\]]+)\]',
                'lat_group': 1,
                'lon_group': 2,
                'timestamp_pattern': r'^(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}\.\d{3})',
                'has_speed': False
            },
            
            # NW_SOS pattern: Latitude = 40.768099 Longitude = -73.995909
            'NW_SOS': {
                'pattern': r'=NW_SOS:\s*Latitude\s*=\s*([+-]?\d+\.?\d*)\s*Longitude\s*=\s*([+-]?\d+\.?\d*)',
                'lat_group': 1,
                'lon_group': 2,
                'timestamp_pattern': r'^(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}\.\d{3})',
                'has_speed': False
            },
            
            # SAL_KONA_NAVI pattern: Latitude: [40.942678] Longitude: [-73.836788]
            'SAL_KONA_NAVI': {
                'pattern': r'=SAL_KONA_NAVI:\s*Latitude:\s*\[([^\]]+)\]\s*Longitude:\s*\[([^\]]+)\]',
                'lat_group': 1,
                'lon_group': 2,
                'timestamp_pattern': r'^(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}\.\d{3})',
                'has_speed': False
            },
            
            # GetCurrentLocAddressResponse pattern: Latitude - 40.8969492,Longitude - -73.8763137
            'GetCurrentLocAddressResponse': {
                'pattern': r'GetCurrentLocAddressResponse.*?Latitude\s*-\s*([+-]?\d+\.?\d*)\s*,\s*Longitude\s*-\s*([+-]?\d+\.?\d*)',
                'lat_group': 1,
                'lon_group': 2,
                'timestamp_pattern': r'^(\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2}:\d{2},\d{3})',
                'has_speed': False
            },
            
            # JSR179InterfaceImpl pattern with speed: Latitude: 40.8969492; Longitude: -73.8763137; ... Speed: 16.89;
            'JSR179InterfaceImpl': {
                'pattern': r'JSR179InterfaceImpl.*?Latitude:\s*([+-]?\d+\.?\d*);.*?Longitude:\s*([+-]?\d+\.?\d*);',
                'lat_group': 1,
                'lon_group': 2,
                'timestamp_pattern': r'^(\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2}:\d{2},\d{3})',
                'speed_pattern': r'Speed:\s*([+-]?\d+\.?\d*);',
                'has_speed': True
            },
            
            # NaviTelematicsDataRequest pattern: dLatitude: 40.764625, dLongitude: -73.994852
            'NaviTelematicsDataRequest': {
                'pattern': r'NaviTelematicsDataRequest.*?dLatitude:\s*([+-]?\d+\.?\d*).*?dLongitude:\s*([+-]?\d+\.?\d*)',
                'lat_group': 1,
                'lon_group': 2,
                'timestamp_pattern': r'^\[(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}\.\d{3})',
                'has_speed': False
            }
        }
        
        self._logger.info("StellantisDecoder initialized")
        self._logger.debug(f"Configured {len(self.gps_patterns)} GPS pattern types")
        self._logger.debug(f"Log file patterns: {self.log_patterns}")
    
    def get_name(self) -> str:
        return "Stellantis Vehicles"
    
    def get_supported_extensions(self) -> List[str]:
        # Return empty list since we work with folders, not individual files
        return []
    
    def get_dropzone_text(self) -> str:
        return "Drop your Stellantis vehicle data\nFOLDER here or click to browse"

    def get_xlsx_headers(self) -> List[str]:
        headers = [
            'Latitude',
            'Longitude',
            'Timestamp (UTC)',
            'Event_Type',
            '',  # Blank column 1
            '',  # Blank column 2
            '',  # Blank column 3
            '',  # Blank column 4
            '',  # Blank column 5
            '',  # Blank column 6
            'Line_Number',
            'Source_File'
        ]
        self._logger.debug(f"XLSX headers: {len(headers)} columns")
        return headers
    
    def format_entry_for_xlsx(self, entry: GPSEntry) -> List[Any]:
        """Format a GPSEntry into a row for the XLSX file"""
        self._logger.debug(f"Formatting entry for XLSX: lat={entry.latitude}, lon={entry.longitude}")
        
        row = [
            entry.latitude if entry.latitude != 0 else 'ERROR',
            entry.longitude if entry.longitude != 0 else 'ERROR',
            entry.timestamp if entry.timestamp else '',
            entry.extra_data.get('event_type', ''),
            '',  # Blank column 1
            '',  # Blank column 2
            '',  # Blank column 3
            '',  # Blank column 4
            '',  # Blank column 5
            '',  # Blank column 6
            entry.extra_data.get('line_number', ''),
            entry.extra_data.get('source_file', '')
        ]
        
        return row
    
    def extract_gps_data(self, folder_path: str, progress_callback=None, stop_event=None) -> Tuple[List[GPSEntry], Optional[str]]:
        """
        Extract GPS data from Stellantis vehicle folder structure
        
        Args:
            folder_path: Path to the folder containing Stellantis log files
            progress_callback: Optional callback for progress updates
            stop_event: Optional threading.Event to signal stop processing
            
        Returns:
            Tuple of (GPS entries list, error message or None)
        """
        start_time = time.time()
        self._log_extraction_start(folder_path)
        
        if not os.path.isdir(folder_path):
            error_msg = f"Path is not a directory: {folder_path}"
            self._log_extraction_error(error_msg)
            return [], error_msg
        
        entries = []
        total_files_processed = 0
        total_entries_found = 0
        
        try:
            if progress_callback:
                progress_callback("Scanning for log files...", 5)
                self._log_progress("Scanning for log files", 5)
            
            # Check for stop signal
            if stop_event and stop_event.is_set():
                self._logger.warning("Processing stopped by user before file discovery")
                return [], "Processing stopped by user."
            
            # Discover all relevant log files
            self._logger.info(f"Starting file discovery in: {folder_path}")
            log_files = self._discover_log_files(folder_path)
            self._logger.info(f"Found {len(log_files)} log files to process")
            
            if not log_files:
                error_msg = "No relevant log files found in the specified folder"
                self._logger.warning(error_msg)
                return [], error_msg
            
            if progress_callback:
                progress_callback(f"Found {len(log_files)} log files", 10)
                self._log_progress(f"Found {len(log_files)} log files", 10)
            
            # Process each log file
            for i, log_file in enumerate(log_files):
                # Check for stop signal
                if stop_event and stop_event.is_set():
                    self._logger.warning(f"Processing stopped by user at file {i}/{len(log_files)}")
                    return entries, "Processing stopped by user."
                
                self._logger.debug(f"Processing file {i+1}/{len(log_files)}: {log_file}")
                
                try:
                    file_entries = self._process_log_file(log_file, stop_event, folder_path)
                    entries.extend(file_entries)
                    total_entries_found += len(file_entries)
                    total_files_processed += 1
                    
                    self._logger.debug(f"File {log_file}: found {len(file_entries)} entries")
                    
                except Exception as e:
                    self._logger.error(f"Error processing file {log_file}: {e}")
                    # Continue processing other files
                    continue
                
                # Update progress
                if progress_callback:
                    progress = 10 + (70 * (i + 1) // len(log_files))
                    progress_callback(f"Processing file {i+1}/{len(log_files)}", progress)
                    
                    if i % max(1, len(log_files) // 10) == 0:
                        self._log_progress(f"Processing files ({i+1}/{len(log_files)})", progress)
            
            # Sort entries by timestamp
            if progress_callback:
                progress_callback("Sorting entries by timestamp...", 85)
                self._log_progress("Sorting entries by timestamp", 85)
            
            entries = self._sort_entries_by_timestamp(entries)
            
            elapsed_time = time.time() - start_time
            
            if progress_callback:
                progress_callback("Processing complete!", 100)
                self._log_progress("Processing complete", 100)
            
            self._logger.info(f"Processing complete: {total_files_processed} files processed, "
                            f"{total_entries_found} GPS entries found")
            self._log_extraction_complete(len(entries), elapsed_time)
            
            return entries, None
            
        except Exception as e:
            self._logger.error(f"Unexpected error during Stellantis extraction: {e}", exc_info=True)
            return [], f"Error processing Stellantis folder: {str(e)}"
    
    def _discover_log_files(self, root_folder: str) -> List[str]:
        """Discover all relevant log files in the folder structure"""
        self._logger.info(f"Discovering log files in: {root_folder}")
        
        log_files = []
        root_path = Path(root_folder)
        
        for pattern in self.log_patterns:
            self._logger.debug(f"Searching pattern: {pattern}")
            
            # Use glob to find files matching the pattern
            matches = list(root_path.glob(pattern))
            self._logger.debug(f"Pattern '{pattern}' found {len(matches)} files")
            
            for match in matches:
                if match.is_file():
                    log_files.append(str(match))
                    self._logger.debug(f"Added log file: {match}")
        
        # Remove duplicates and sort
        log_files = sorted(list(set(log_files)))
        self._logger.info(f"Total unique log files found: {len(log_files)}")
        
        return log_files
    
    def _process_log_file(self, file_path: str, stop_event=None, folder_path=None) -> List[GPSEntry]:
        """Process a single log file and extract GPS entries"""
        self._logger.debug(f"Processing log file: {file_path}")
        
        entries = []
        line_number = 0
        
        try:
            # Determine encoding - try UTF-8 first, fallback to latin-1
            encoding = 'utf-8'
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    f.read(1024)  # Test read
            except UnicodeDecodeError:
                encoding = 'latin-1'
                self._logger.debug(f"Using latin-1 encoding for {file_path}")
            
            with open(file_path, 'r', encoding=encoding, errors='ignore') as f:
                for line in f:
                    line_number += 1
                    
                    # Check for stop signal periodically
                    if stop_event and stop_event.is_set() and line_number % 1000 == 0:
                        self._logger.debug(f"Stop signal received while processing {file_path}")
                        break
                    
                    # Try to extract GPS data from this line
                    entry = self._extract_gps_from_line(line.strip(), file_path, line_number, folder_path)
                    if entry:
                        entries.append(entry)
                        
                        if len(entries) % 100 == 0:
                            self._logger.debug(f"File {file_path}: extracted {len(entries)} entries so far")
        
        except Exception as e:
            self._logger.error(f"Error reading file {file_path}: {e}")
            # Return what we have so far
        
        self._logger.debug(f"Completed processing {file_path}: {len(entries)} entries found")
        return entries
    
    def _extract_gps_from_line(self, line: str, file_path: str, line_number: int, folder_path: str = None) -> Optional[GPSEntry]:
        """Extract GPS data from a single log line"""
        
        for event_type, pattern_info in self.gps_patterns.items():
            # Check if this line contains the event type
            if event_type in line:
                # Try to extract GPS coordinates
                coord_match = re.search(pattern_info['pattern'], line, re.IGNORECASE)
                if coord_match:
                    try:
                        latitude = float(coord_match.group(pattern_info['lat_group']))
                        longitude = float(coord_match.group(pattern_info['lon_group']))
                        if not self._is_valid_coordinate(latitude, longitude):
                            continue
                        timestamp_str = self._extract_timestamp(line, pattern_info['timestamp_pattern'])
                    
                        # --- CHANGED BLOCK START ---
                        if folder_path:
                            parent_folder = os.path.dirname(folder_path)
                            source_file = os.path.relpath(file_path, parent_folder)
                        else:
                            source_file = os.path.abspath(file_path)
                        # --- CHANGED BLOCK END ---
                    
                        extra_data = {
                            'event_type': event_type,
                            'source_file': source_file,
                            'line_number': line_number
                        }
                        
                        # Create GPS entry
                        entry = GPSEntry(
                            latitude=latitude,
                            longitude=longitude,
                            timestamp=timestamp_str,
                            extra_data=extra_data
                        )
                        
                        self._logger.debug(f"Extracted GPS entry: {event_type} at {latitude}, {longitude}")
                        return entry
                        
                    except (ValueError, IndexError) as e:
                        self._logger.debug(f"Error parsing coordinates from line {line_number}: {e}")
                        continue
        
        return None
    
    def _extract_timestamp(self, line: str, timestamp_pattern: str) -> str:
        """Extract and format timestamp from log line"""
    
        timestamp_match = re.search(timestamp_pattern, line)
        if not timestamp_match:
            self._logger.debug(f"No timestamp found in line: {line[:100]}...")
            return ""
    
        timestamp_str = timestamp_match.group(1)
    
        try:
            # Parse different timestamp formats
            if '/' in timestamp_str and '.' in timestamp_str:
                # Format: 12/29/2022 13:51:18.429 or [08/09/2022 00:12:57.403
                clean_ts = timestamp_str.strip('[]')
                dt = datetime.strptime(clean_ts, '%m/%d/%Y %H:%M:%S.%f')
                # Add UTC timezone
                dt = dt.replace(tzinfo=timezone.utc)
            elif '.' in timestamp_str and ',' in timestamp_str:
                # Format: 2023.01.21 06:46:56,618
                dt = datetime.strptime(timestamp_str, '%Y.%m.%d %H:%M:%S,%f')
                # Add UTC timezone
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                # Fallback - return as is
                self._logger.debug(f"Unknown timestamp format: {timestamp_str}")
                return timestamp_str
        
            # Convert to UTC ISO format
            formatted = dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        
            self._logger.debug(f"Parsed timestamp: {timestamp_str} -> {formatted}")
            return formatted
        
        except ValueError as e:
            self._logger.debug(f"Error parsing timestamp '{timestamp_str}': {e}")
            return timestamp_str  # Return original if parsing fails
    
    def _is_valid_coordinate(self, lat: float, lon: float) -> bool:
        """Check if coordinates are valid GPS values"""
        # Basic range check
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return False
            
        # Check for null island
        if lat == 0 and lon == 0:
            return False
            
        return True
    
    def _sort_entries_by_timestamp(self, entries: List[GPSEntry]) -> List[GPSEntry]:
        """Sort GPS entries by timestamp"""
        self._logger.debug(f"Sorting {len(entries)} entries by timestamp")
    
        def timestamp_key(entry):
            try:
                if entry.timestamp:
                    # Parse the ISO format timestamp for sorting
                    dt = datetime.fromisoformat(entry.timestamp.replace('Z', '+00:00'))
                    # Ensure timezone awareness
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt
                else:
                    return datetime.min.replace(tzinfo=timezone.utc)
            except Exception as e:
                self._logger.debug(f"Error parsing timestamp '{entry.timestamp}': {e}")
                return datetime.min.replace(tzinfo=timezone.utc)
    
        sorted_entries = sorted(entries, key=timestamp_key)
        self._logger.debug(f"Entries sorted successfully")
    
        return sorted_entries