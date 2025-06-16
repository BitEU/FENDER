import sqlite3
import struct
import os
from datetime import datetime, timezone
from typing import List, Tuple, Optional, Any
from base_decoder import BaseDecoder, GPSEntry
import logging
import time

# Setup logger for this module
logger = logging.getLogger(__name__)

class MercedesDecoder(BaseDecoder):
    def __init__(self):
        super().__init__()
        self.INT32_MAX = 2147483647  # 2^31 - 1
        self._logger.info(f"MercedesDecoder initialized")
    
    def get_name(self) -> str:
        return "Mercedes NTG5*2"
    
    def get_supported_extensions(self) -> List[str]:
        extensions = ['.sqlite', '.db']
        self._logger.debug(f"Supported extensions: {extensions}")
        return extensions
    
    def get_dropzone_text(self) -> str:
        return "Drop your Mercedes NTG5*2 SQLite database\nhere or click to browse"

    def get_xlsx_headers(self) -> List[str]:
        headers = [
            'TrailId',
            'BeginTime_UTC',
            'EndTime_UTC',
            'GPS_Longitude',
            'GPS_Latitude',
            'PathOffset',
            'SourceTable'
        ]
        self._logger.debug(f"XLSX headers: {len(headers)} columns")
        return headers
    
    def format_entry_for_xlsx(self, entry: GPSEntry) -> List[Any]:
        """Format a GPSEntry into a row for the XLSX file"""
        self._logger.debug(f"Formatting entry for XLSX: lat={entry.latitude}, lon={entry.longitude}")

        row = [
            entry.extra_data.get('TrailId', ''),
            entry.extra_data.get('BeginTime_UTC', ''),
            entry.extra_data.get('EndTime_UTC', ''),
            entry.longitude if entry.longitude != 0 else 'ERROR',
            entry.latitude if entry.latitude != 0 else 'ERROR',
            entry.extra_data.get('PathOffset', ''),
            entry.extra_data.get('SourceTable', '')
        ]

        return row
    
    def extract_gps_data(self, file_path: str, progress_callback=None, stop_event=None) -> Tuple[List[GPSEntry], Optional[str]]:
        """Extract GPS data from Mercedes SQLite database, with support for stopping."""
        start_time = time.time()
        self._log_extraction_start(file_path)
        
        try:
            if not os.path.exists(file_path):
                error_msg = f"Database file not found: {file_path}"
                self._log_extraction_error(error_msg)
                return [], error_msg
            
            # Check file size
            file_size = os.path.getsize(file_path)
            self._logger.info(f"Processing Mercedes SQLite file: {file_path} (Size: {file_size/1024/1024:.2f} MB)")
            
            if progress_callback:
                progress_callback("Opening SQLite database...", 10)
                self._log_progress("Opening SQLite database", 10)
                
            if stop_event and stop_event.is_set():
                self._logger.warning("Processing stopped by user before database open")
                return [], "Processing stopped by user."

            conn = sqlite3.connect(file_path)
            cursor = conn.cursor()
            
            if progress_callback:
                progress_callback("Reading trails table...", 30)
                self._log_progress("Reading trails table", 30)
                
            if stop_event and stop_event.is_set():
                conn.close()
                self._logger.warning("Processing stopped by user before trail read")
                return [], "Processing stopped by user."

            # Get all trails
            cursor.execute("SELECT * FROM Trails")
            trails = cursor.fetchall()
            
            # Get column names
            column_names = [description[0] for description in cursor.description]
            
            self._logger.info(f"Found {len(trails)} trails in database")
            
            if progress_callback:
                progress_callback(f"Processing {len(trails)} trails...", 50)
                self._log_progress(f"Processing {len(trails)} trails", 50)
                
            if stop_event and stop_event.is_set():
                conn.close()
                self._logger.warning("Processing stopped by user before trail processing")
                return [], "Processing stopped by user."

            entries = []
            valid_entries = 0
            invalid_entries = 0
            
            for i, trail in enumerate(trails):
                if stop_event and stop_event.is_set():
                    conn.close()
                    self._logger.warning(f"Processing stopped by user at trail {i}/{len(trails)}")
                    return entries, "Processing stopped by user."

                self._logger.debug(f"Processing trail {i+1}/{len(trails)}")
                
                trail_dict = dict(zip(column_names, trail))
                
                trail_id = trail_dict['TrailId']
                begin_time = trail_dict['BeginTime']
                end_time = trail_dict['EndTime']
                path_data = trail_dict['Path']
                
                # Convert timestamps to ISO format
                begin_time_iso = self.unix_to_iso(begin_time)
                end_time_iso = self.unix_to_iso(end_time)
                
                # Decode path events
                events = self.decode_path_events(path_data, begin_time) if path_data else []
                
                # Create base record
                base_record = {
                    'TrailId': trail_id,
                    'BeginTime_UTC': begin_time_iso,
                    'EndTime_UTC': end_time_iso
                }
                
                # If no GPS events in path, just add the trail info
                if not events:
                    gps_entry = GPSEntry(
                        latitude=0,
                        longitude=0,
                        timestamp=begin_time_iso if begin_time_iso else '',
                        extra_data=base_record
                    )
                    entries.append(gps_entry)
                    invalid_entries += 1
                else:
                    # Add each GPS event as a separate row
                    for event in events:
                        if self.is_valid_coordinates(event['latitude'], event['longitude']):
                            gps_entry = GPSEntry(
                                latitude=event['latitude'],
                                longitude=event['longitude'],
                                timestamp=begin_time_iso if begin_time_iso else '',
                                extra_data={
                                    **base_record,
                                    'PathOffset': event.get('offset', ''),
                                    'SourceTable': 'Trails',
                                    'TrailId': trail_id
                                }
                            )
                            entries.append(gps_entry)
                            valid_entries += 1
                        else:
                            invalid_entries += 1
                            self._logger.debug(f"Invalid coordinates in trail {trail_id}: {event['latitude']}, {event['longitude']}")

                if progress_callback and len(trails) > 0:
                    progress = 50 + (30 * (i + 1) // len(trails))
                    progress_callback(f"Processing trail {i+1}/{len(trails)}", progress)
                    
                    # Log progress every 10%
                    if i % max(1, len(trails) // 10) == 0:
                        self._log_progress(f"Processing trails ({i+1}/{len(trails)})", progress)

            conn.close()
            
            elapsed_time = time.time() - start_time
            self._logger.info(f"Processing complete. Valid entries: {valid_entries}, Invalid entries: {invalid_entries}")
            
            # Deduplicate entries before returning
            unique = set()
            deduped_entries = []
            for entry in entries:
                # Use a tuple of identifying fields as the deduplication key
                key = (
                    round(entry.latitude, 7),  # rounding to avoid float precision issues
                    round(entry.longitude, 7),
                    entry.timestamp,
                    tuple(sorted(entry.extra_data.items()))
                )
                if key not in unique:
                    unique.add(key)
                    deduped_entries.append(entry)

            if progress_callback:
                progress_callback("Processing complete!", 90)
                self._log_progress("Processing complete", 90)

            self._log_extraction_complete(len(deduped_entries), elapsed_time)
            return deduped_entries, None

        except sqlite3.Error as e:
            error_msg = f"SQLite database error: {str(e)}"
            self._log_extraction_error(error_msg)
            return [], error_msg
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
    
    def decode_gps_coordinate(self, encoded_value):
        """
        Decode GPS coordinate from proprietary format
        Formula: decoded_value = encoded_value * 180 / Int32.MAX_VALUE
        """
        # Convert unsigned to signed if necessary
        if encoded_value > self.INT32_MAX:
            encoded_value = encoded_value - 2**32
        
        return (encoded_value * 180.0) / self.INT32_MAX
    
    def decode_path_events(self, path_data, start_timestamp):
        """
        Decode the path binary data to extract GPS events
        Format: 04 01 01 00 + segments with various event types
        """
        events = []
        if len(path_data) < 8:
            return events
        try:
            num_segments = struct.unpack('<H', path_data[4:6])[0]
            offset = 6
            for segment_idx in range(num_segments):
                if offset + 4 > len(path_data):
                    break
                segment_size = struct.unpack('<I', path_data[offset:offset+4])[0]
                if offset + segment_size > len(path_data):
                    break
                segment_data = path_data[offset:offset+segment_size]
                event_offset = 16
                while event_offset + 5 < len(segment_data):
                    event_start = offset + event_offset  # Absolute offset in path_data
                    event_id = segment_data[event_offset]
                    distance = struct.unpack('<I', segment_data[event_offset+1:event_offset+5])[0]
                    event_offset += 5
                    if event_id == 1:  # GPS coordinates
                        if event_offset + 12 <= len(segment_data):
                            coords = struct.unpack('<3I', segment_data[event_offset:event_offset+12])
                            lon = self.decode_gps_coordinate(coords[0])
                            lat = self.decode_gps_coordinate(coords[1])
                            elev = coords[2]
                            events.append({
                                'longitude': lon,
                                'latitude': lat,
                                'elevation': elev,
                                'offset': hex(event_start)
                            })
                            event_offset += 12
                    elif event_id == 2:  # Milliseconds since start
                        if event_offset + 4 <= len(segment_data):
                            millis = struct.unpack('<I', segment_data[event_offset:event_offset+4])[0]
                            # Not used in output
                            event_offset += 4
                    elif event_id == 3:  # Timestamp
                        if event_offset + 8 <= len(segment_data):
                            # Skip 4 zero bytes, then read timestamp
                            timestamp = struct.unpack('<I', segment_data[event_offset+4:event_offset+8])[0]
                            # Not used in output
                            event_offset += 8
                    else:
                        # Skip unknown events
                        if event_id == 14 or event_id == 16:
                            pass  # No additional data
                        elif event_id == 15:
                            event_offset += 4
                        elif event_id == 18:
                            event_offset += 1
                        else:
                            break  # Unknown event, stop parsing
                offset += segment_size
        except struct.error as e:
            self._logger.error(f"Error decoding path events: {e}")
        return events
    
    def unix_to_iso(self, unix_timestamp):
        """Convert Unix timestamp to ISO formatted UTC string"""
        if unix_timestamp and unix_timestamp > 0:
            try:
                dt = datetime.fromtimestamp(unix_timestamp, tz=timezone.utc)
                return dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            except (ValueError, OSError):
                self._logger.warning(f"Invalid Unix timestamp: {unix_timestamp}")
                return None
        return None
    
    def is_valid_coordinates(self, lat, lon):
        """Check if coordinates are valid"""
        if lat is None or lon is None:
            return False
        if lat == 0 and lon == 0:
            return False  # Null island
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return False
        return True