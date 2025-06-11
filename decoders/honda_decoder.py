import os
import sys
import struct
import sqlite3
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Tuple, Optional, Any, BinaryIO

# Import base classes
from base_decoder import BaseDecoder, GPSEntry

try:
    import pytsk3
    TSK_AVAILABLE = True
except ImportError:
    TSK_AVAILABLE = False

class HondaDecoder(BaseDecoder):
    """
    Honda CRM Database Decoder
    Extracts GPS data from Honda Android system images containing crm.db files
    """
    
    def __init__(self):
        self.temp_files = []  # Track temporary files for cleanup
    
    def get_name(self) -> str:
        """Return the name of this decoder for display in the GUI"""
        return "Honda Telematics"
    
    def get_supported_extensions(self) -> List[str]:
        """Return supported file extensions for Honda Android images"""
        return ['.USER', '.bin']
    
    def get_dropzone_text(self) -> str:
        return "Drop your Honda Infotainment System\neMMC binary here or click to browse"

    def get_xlsx_headers(self) -> List[str]:
        """Return column headers for the XLSX output file"""
        return [
            'Starting Latitude Position',
            'Starting Longitude Position',
            'Starting Time (UTC)',
            'Finishing Time (UTC)',
            'Finishing Latitude Position',
            'Finishing Longitude Position'
        ]
    
    def format_entry_for_xlsx(self, entry: GPSEntry) -> List[Any]:
        """Format a GPSEntry into a row for the XLSX file"""
        return [
            entry.latitude if entry.latitude != 0 else 'ERROR',
            entry.longitude if entry.longitude != 0 else 'ERROR',
            entry.timestamp if entry.timestamp else 'ERROR',
            entry.extra_data.get('finish_pos_time', ''),
            entry.extra_data.get('finish_pos_lat', ''),
            entry.extra_data.get('finish_pos_lon', ''),
            '', '', '', '', '', '', '', '', ''  # Nine blank columns
        ]
    
    def extract_gps_data(self, file_path: str, progress_callback=None, stop_event=None) -> Tuple[List[GPSEntry], Optional[str]]:
        """
        Extract GPS data from Honda Android image file
        
        Args:
            file_path: Path to the Honda Android image file
            progress_callback: Optional callback for progress updates
            
        Returns:
            Tuple of (GPS entries list, error message or None)
        """
        if not TSK_AVAILABLE:
            return [], "pytsk3 is required for Honda image extraction. Install with: pip install pytsk3"
        
        entries = []
        
        try:
            if progress_callback:
                progress_callback("Analyzing Honda Android image...", 5)
            
            # Validate file exists and has reasonable size
            if not os.path.exists(file_path):
                return [], f"File not found: {file_path}"
            
            file_size = os.path.getsize(file_path)
            if file_size < 1024 * 1024:  # Less than 1MB
                return [], "File appears too small to be a valid Android image"
            
            if progress_callback:
                progress_callback("Searching for userdata partition...", 10)
            
            # Find userdata partition
            partition_info = self._find_partition_by_name(file_path, "userdata")
            if not partition_info:
                return [], "Could not find userdata partition in Android image. This may not be a valid Honda Android image."
            
            offset, size = partition_info
            
            if progress_callback:
                progress_callback("Found userdata partition, extracting filesystem...", 20)
            
            # Extract CRM database
            crm_db_path = self._extract_crm_database(file_path, offset, size, progress_callback)
            if not crm_db_path:
                return [], "Could not extract Honda CRM database from image. The database may not exist or be accessible."
            
            if progress_callback:
                progress_callback("Processing CRM database...", 60)
            
            # Extract GPS data from database
            entries = self._process_crm_database(crm_db_path, progress_callback)
            
            if not entries:
                return [], "No GPS data found in Honda CRM database. The eco_logs table may be empty or missing."
            
            # Cleanup temporary files
            self._cleanup_temp_files()
            
            if progress_callback:
                progress_callback("Honda extraction complete!", 100)
            
            return entries, None
            
        except Exception as e:
            self._cleanup_temp_files()
            return [], f"Error processing Honda image: {str(e)}"
    
    def _find_partition_by_name(self, image_path: str, partition_name: str = "userdata") -> Optional[Tuple[int, int]]:
        """Find partition offset and size by scanning for GPT or ext4 patterns"""
        try:
            with open(image_path, 'rb') as f:
                # Try to find GPT header first
                gpt_result = self._find_gpt_partition(f, partition_name)
                if gpt_result[0] is not None:
                    return gpt_result
                
                # Try to find ext4 signature directly
                ext4_result = self._find_ext4_partition(f)
                if ext4_result[0] is not None:
                    return ext4_result
            
            return None
        except Exception:
            return None
    
    def _find_gpt_partition(self, f: BinaryIO, partition_name: str) -> Tuple[Optional[int], Optional[int]]:
        """Find partition using GPT (GUID Partition Table)"""
        try:
            # GPT header is at LBA 1 (sector size 512)
            f.seek(512)
            gpt_header = f.read(92)
            
            if len(gpt_header) < 92 or gpt_header[:8] != b'EFI PART':
                return None, None
            
            # Parse GPT header
            partition_entries_lba, = struct.unpack('<Q', gpt_header[72:80])
            num_partitions, = struct.unpack('<I', gpt_header[80:84])
            partition_entry_size, = struct.unpack('<I', gpt_header[84:88])
            
            # Read partition entries
            f.seek(partition_entries_lba * 512)
            
            for i in range(min(num_partitions, 128)):  # Reasonable limit
                entry = f.read(partition_entry_size)
                if len(entry) < 128:
                    break
                
                # Check if partition exists (non-zero GUID)
                if entry[:16] == b'\x00' * 16:
                    continue
                
                # Extract partition name (UTF-16LE, 72 bytes max)
                name_bytes = entry[56:128]
                try:
                    name = name_bytes.decode('utf-16le').rstrip('\x00')
                except:
                    continue
                
                if partition_name.lower() in name.lower():
                    start_lba, = struct.unpack('<Q', entry[32:40])
                    end_lba, = struct.unpack('<Q', entry[40:48])
                    
                    offset = start_lba * 512
                    size = (end_lba - start_lba + 1) * 512
                    
                    return offset, size
            
        except Exception:
            pass
        
        return None, None
    
    def _find_ext4_partition(self, f: BinaryIO) -> Tuple[Optional[int], Optional[int]]:
        """Find ext4 partition by scanning for superblock signature"""
        try:
            # Get file size
            current_pos = f.tell()
            f.seek(0, 2)  # Seek to end
            file_size = f.tell()
            f.seek(current_pos)  # Restore position
            
            # ext4 superblock is at offset 1024 from partition start
            chunk_size = 4 * 1024 * 1024  # 4MB chunks
            max_search = min(file_size, 500 * 1024 * 1024)  # Search first 500MB
            
            for offset in range(0, max_search, chunk_size):
                f.seek(offset)
                chunk = f.read(min(chunk_size, max_search - offset))
                
                # Look for ext4 magic number (0xEF53) at offset 1024 + 56
                for i in range(len(chunk) - 1080):
                    if chunk[i + 1024 + 56:i + 1024 + 58] == b'\x53\xEF':
                        partition_offset = offset + i
                        
                        # Validate this is a real ext4 superblock
                        f.seek(partition_offset + 1024)
                        superblock = f.read(1024)
                        
                        if len(superblock) >= 1024:
                            # Get block count and block size
                            block_count, = struct.unpack('<I', superblock[4:8])
                            log_block_size, = struct.unpack('<I', superblock[24:28])
                            block_size = 1024 << log_block_size
                            
                            # Sanity check
                            if block_size in [1024, 2048, 4096] and block_count > 1000:
                                partition_size = block_count * block_size
                                return partition_offset, partition_size
            
        except Exception:
            pass
        
        return None, None
    
    def _extract_crm_database(self, image_path: str, offset: int, size: int, progress_callback=None) -> Optional[str]:
        """Extract the Honda CRM database from the Android image"""
        try:
            # Create temporary file for partition
            temp_partition = tempfile.NamedTemporaryFile(delete=False, suffix='.img')
            self.temp_files.append(temp_partition.name)
            
            if progress_callback:
                progress_callback("Extracting userdata partition...", 25)
            
            # Extract partition to temporary file
            with open(image_path, 'rb') as src:
                src.seek(offset)
                remaining = size
                chunk_size = 8 * 1024 * 1024  # 8MB chunks
                
                while remaining > 0:
                    read_size = min(chunk_size, remaining)
                    chunk = src.read(read_size)
                    if not chunk:
                        break
                    temp_partition.write(chunk)
                    remaining -= len(chunk)
            
            temp_partition.close()
            
            if progress_callback:
                progress_callback("Opening partition with TSK...", 35)
            
            # Open with TSK
            img = pytsk3.Img_Info(temp_partition.name)
            fs = pytsk3.FS_Info(img)
            
            # Try to extract CRM database
            crm_db_path = self._try_extract_crm_paths(fs, progress_callback)
            
            return crm_db_path
                
        except Exception:
            return None
    
    def _try_extract_crm_paths(self, fs, progress_callback=None) -> Optional[str]:
        """Try extracting CRM database from multiple possible paths"""
        
        # Common paths where Honda CRM database might be located
        search_paths = [
            "/data/com.honda.telematics.core/databases/crm.db",
            "/data/data/com.honda.telematics.core/databases/crm.db", 
            "data/com.honda.telematics.core/databases/crm.db",
            "data/data/com.honda.telematics.core/databases/crm.db",
            "/userdata/data/com.honda.telematics.core/databases/crm.db",
            "userdata/data/com.honda.telematics.core/databases/crm.db",
        ]
        
        for i, search_path in enumerate(search_paths):
            try:
                if progress_callback:
                    progress_callback(f"Trying path {i+1}/{len(search_paths)}: {search_path}", 40 + i * 2)
                
                file_obj = fs.open(search_path)
                
                # Create temporary file for database
                temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
                self.temp_files.append(temp_db.name)
                
                # Read and write the file
                file_size = file_obj.info.meta.size
                data = file_obj.read_random(0, file_size)
                temp_db.write(data)
                temp_db.close()
                
                return temp_db.name
                
            except Exception:
                continue
        
        # If direct paths fail, try recursive search
        if progress_callback:
            progress_callback("Starting recursive search for crm.db...", 50)
        
        return self._recursive_search_crm(fs)
    
    def _recursive_search_crm(self, fs) -> Optional[str]:
        """Recursively search for crm.db files"""
        try:
            if self._search_directory(fs, fs.open_dir("/"), "/", 0):
                # Return the last created temp file (should be crm.db)
                for temp_file in reversed(self.temp_files):
                    if temp_file.endswith('.db'):
                        return temp_file
            return None
        except Exception:
            return None
    
    def _search_directory(self, fs, directory, current_path: str, depth: int) -> bool:
        """Search directory recursively with depth limit"""
        if depth > 10:  # Prevent infinite recursion
            return False
            
        try:
            for entry in directory:
                entry_name = entry.info.name.name.decode('utf-8', errors='ignore')
                
                if entry_name in ['.', '..']:
                    continue
                
                full_path = f"{current_path}{entry_name}" if current_path.endswith('/') else f"{current_path}/{entry_name}"
                
                # Check if it's a regular file named crm.db
                if (entry.info.meta and 
                    entry.info.meta.type == pytsk3.TSK_FS_META_TYPE_REG and 
                    entry_name.lower() == "crm.db"):
                    
                    try:
                        file_obj = fs.open(full_path)
                        
                        # Create temporary file for database
                        temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
                        self.temp_files.append(temp_db.name)
                        
                        # Read file data and write to temp file
                        file_size = file_obj.info.meta.size
                        data = file_obj.read_random(0, file_size)
                        temp_db.write(data)
                        temp_db.close()
                        
                        return True
                    except Exception:
                        pass
                
                # Recurse into directories that might contain Honda data
                elif (entry.info.meta and 
                      entry.info.meta.type == pytsk3.TSK_FS_META_TYPE_DIR and
                      any(keyword in entry_name.lower() for keyword in ['honda', 'telematics', 'data', 'app'])):
                    
                    try:
                        sub_dir = fs.open_dir(full_path)
                        if self._search_directory(fs, sub_dir, full_path, depth + 1):
                            return True
                    except Exception:
                        continue
        
        except Exception:
            pass
        
        return False
    
    def _process_crm_database(self, crm_db_path: str, progress_callback=None) -> List[GPSEntry]:
        """Process the eco_logs table and convert to GPSEntry objects"""
        entries = []
        
        try:
            # Connect to the SQLite database
            conn = sqlite3.connect(crm_db_path)
            cursor = conn.cursor()
            
            # Check if eco_logs table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='eco_logs';")
            if not cursor.fetchone():
                conn.close()
                return entries
            
            if progress_callback:
                progress_callback("Reading eco_logs table...", 70)
            
            # Check available columns
            cursor.execute("PRAGMA table_info(eco_logs);")
            columns = [row[1] for row in cursor.fetchall()]
            
            required_columns = [
                'start_pos_time', 'start_pos_lat', 'start_pos_lon',
                'finish_pos_time', 'finish_pos_lat', 'finish_pos_lon'
            ]
            
            # Check which columns are available
            available_required = [col for col in required_columns if col in columns]
            
            if not available_required:
                conn.close()
                return entries
            
            # Query the available columns
            columns_str = ', '.join(available_required)
            query = f"SELECT {columns_str} FROM eco_logs WHERE start_pos_lat IS NOT NULL AND start_pos_lon IS NOT NULL"
            cursor.execute(query)
            rows = cursor.fetchall()
            
            if progress_callback:
                progress_callback(f"Processing {len(rows)} records...", 80)
            
            # Convert rows to GPSEntry objects
            for row_data in rows:
                row_dict = dict(zip(available_required, row_data))
                
                # Extract coordinates and timestamps
                start_lat = self._safe_float(row_dict.get('start_pos_lat'))
                start_lon = self._safe_float(row_dict.get('start_pos_lon'))
                finish_lat = self._safe_float(row_dict.get('finish_pos_lat'))
                finish_lon = self._safe_float(row_dict.get('finish_pos_lon'))
                
                start_time = self._format_timestamp(row_dict.get('start_pos_time'))
                finish_time = self._format_timestamp(row_dict.get('finish_pos_time'))
                
                # Prepare extra data
                extra_data = {
                    'start_pos_time': start_time,
                    'start_pos_lat': start_lat or '',
                    'start_pos_lon': start_lon or '',
                    'finish_pos_time': finish_time,
                    'finish_pos_lat': finish_lat or '',
                    'finish_pos_lon': finish_lon or '',
                }
                
                # Create entries for start position
                if start_lat and start_lon and self._is_valid_coordinate(start_lat, start_lon):
                    entry = GPSEntry(
                        latitude=start_lat,
                        longitude=start_lon,
                        timestamp=start_time,
                        extra_data=extra_data.copy()
                    )
                    entries.append(entry)
                
                # Create entries for finish position (if different from start)
                if (finish_lat and finish_lon and 
                    self._is_valid_coordinate(finish_lat, finish_lon) and
                    (finish_lat != start_lat or finish_lon != start_lon)):
                    
                    finish_extra_data = {
                        'start_pos_time': start_time,
                        'start_pos_lat': start_lat or '',
                        'start_pos_lon': start_lon or '',
                        'finish_pos_time': finish_time,
                        'finish_pos_lat': finish_lat,
                        'finish_pos_lon': finish_lon,
                    }
                    
                    entry = GPSEntry(
                        latitude=finish_lat,
                        longitude=finish_lon,
                        timestamp=finish_time,
                        extra_data=finish_extra_data
                    )
                    entries.append(entry)
            
            conn.close()
            
            if progress_callback:
                progress_callback("Database processing complete!", 90)
            
        except Exception:
            # Silently fail - we'll return empty entries
            pass
        
        return entries
    
    def _safe_float(self, value) -> Optional[float]:
        """Safely convert value to float"""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    
    def _is_valid_coordinate(self, lat: float, lon: float) -> bool:
        """Check if coordinates are valid GPS values"""
        return -90 <= lat <= 90 and -180 <= lon <= 180 and (lat != 0 or lon != 0)
    
    def _format_timestamp(self, timestamp) -> str:
        """Format timestamp as datetime string"""
        if not timestamp:
            return ''
        
        try:
            # Try to parse as Unix timestamp (milliseconds)
            if isinstance(timestamp, (int, float)):
                if timestamp > 1e12:  # Milliseconds
                    ts = timestamp / 1000.0
                else:  # Seconds
                    ts = timestamp
                
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                return dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            
            # Try to parse as string timestamp
            elif isinstance(timestamp, str):
                # Try different timestamp formats
                formats = [
                    '%Y-%m-%d %H:%M:%S',
                    '%Y-%m-%d %H:%M:%S.%f',
                    '%Y-%m-%dT%H:%M:%S',
                    '%Y-%m-%dT%H:%M:%S.%f',
                    '%Y-%m-%dT%H:%M:%SZ',
                    '%Y-%m-%dT%H:%M:%S.%fZ'
                ]
                
                for fmt in formats:
                    try:
                        dt = datetime.strptime(timestamp, fmt)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        return dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                    except ValueError:
                        continue
                
                # Try parsing as Unix timestamp string
                try:
                    ts = float(timestamp)
                    if ts > 1e12:  # Milliseconds
                        ts = ts / 1000.0
                    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                    return dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                except ValueError:
                    pass
            
        except Exception:
            pass
        
        return str(timestamp) if timestamp else ''
    
    def _cleanup_temp_files(self):
        """Clean up all temporary files"""
        for temp_file in self.temp_files:
            try:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)
            except Exception:
                pass
        
        self.temp_files.clear()
    
    def __del__(self):
        """Cleanup when object is destroyed"""
        self._cleanup_temp_files()