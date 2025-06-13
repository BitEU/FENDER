import os
import sys
import struct
import sqlite3
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Tuple, Optional, Any, BinaryIO
import logging
import time

# Import base classes
from base_decoder import BaseDecoder, GPSEntry

# Setup logger for this module
logger = logging.getLogger(__name__)

try:
    import pytsk3
    TSK_AVAILABLE = True
    logger.info("pytsk3 module loaded successfully")
except ImportError:
    TSK_AVAILABLE = False
    logger.warning("pytsk3 module not available - Honda decoder functionality will be limited")

class HondaDecoder(BaseDecoder):
    """
    Honda CRM Database Decoder
    Extracts GPS data from Honda Android system images containing crm.db files
    """
    
    def __init__(self):
        super().__init__()
        self.temp_files = []  # Track temporary files for cleanup
        self._logger.info("HondaDecoder initialized")
        self._logger.debug(f"TSK available: {TSK_AVAILABLE}")
    
    def get_name(self) -> str:
        """Return the name of this decoder for display in the GUI"""
        return "Honda Telematics"
    
    def get_supported_extensions(self) -> List[str]:
        """Return supported file extensions for Honda Android images"""
        extensions = ['.USER', '.bin']
        self._logger.debug(f"Supported extensions: {extensions}")
        return extensions
    
    def get_dropzone_text(self) -> str:
        return "Drop your Honda Infotainment System\neMMC binary here or click to browse"

    def get_xlsx_headers(self) -> List[str]:
        """Return column headers for the XLSX output file"""
        headers = [
            'Starting Latitude Position',
            'Starting Longitude Position',
            'Starting Time (UTC)',
            'Finishing Time (UTC)',
            'Finishing Latitude Position',
            'Finishing Longitude Position'
        ]
        self._logger.debug(f"XLSX headers: {len(headers)} columns")
        return headers
    
    def format_entry_for_xlsx(self, entry: GPSEntry) -> List[Any]:
        """Format a GPSEntry into a row for the XLSX file"""
        self._logger.debug(f"Formatting entry for XLSX: lat={entry.latitude}, lon={entry.longitude}")
        
        row = [
            entry.latitude if entry.latitude != 0 else 'ERROR',
            entry.longitude if entry.longitude != 0 else 'ERROR',
            entry.timestamp if entry.timestamp else 'ERROR',
            entry.extra_data.get('finish_pos_time', ''),
            entry.extra_data.get('finish_pos_lat', ''),
            entry.extra_data.get('finish_pos_lon', ''),
            '', '', '', '', '', '', '', '', ''  # Nine blank columns
        ]
        
        return row
    
    def extract_gps_data(self, file_path: str, progress_callback=None, stop_event=None) -> Tuple[List[GPSEntry], Optional[str]]:
        """
        Extract GPS data from Honda Android image file
        
        Args:
            file_path: Path to the Honda Android image file
            progress_callback: Optional callback for progress updates
            stop_event: Optional threading.Event to signal stop processing
            
        Returns:
            Tuple of (GPS entries list, error message or None)
        """
        start_time = time.time()
        self._log_extraction_start(file_path)
        
        if not TSK_AVAILABLE:
            error_msg = "pytsk3 is required for Honda image extraction. Install with: pip install pytsk3"
            self._logger.error(error_msg)
            return [], error_msg
        
        entries = []
        
        try:
            # Check file size
            file_size = os.path.getsize(file_path)
            self._logger.info(f"Processing Honda image: {file_path} (Size: {file_size/1024/1024:.2f} MB)")
            
            if progress_callback:
                progress_callback("Analyzing Honda Android image...", 5)
                self._log_progress("Analyzing Honda Android image", 5)
            
            # Check for stop signal
            if stop_event and stop_event.is_set():
                self._logger.warning("Processing stopped by user before analysis")
                return [], "Processing stopped by user."
            
            # Validate file exists and has reasonable size
            if not os.path.exists(file_path):
                error_msg = f"File not found: {file_path}"
                self._logger.error(error_msg)
                return [], error_msg
            
            if file_size < 1024 * 1024:  # Less than 1MB
                error_msg = "File appears too small to be a valid Android image"
                self._logger.warning(f"{error_msg}: {file_size} bytes")
                return [], error_msg
            
            if progress_callback:
                progress_callback("Searching for userdata partition...", 10)
                self._log_progress("Searching for userdata partition", 10)
            
            # Check for stop signal
            if stop_event and stop_event.is_set():
                self._logger.warning("Processing stopped by user before partition search")
                return [], "Processing stopped by user."
            
            # Find userdata partition
            self._logger.info("Starting search for userdata partition")
            partition_info = self._find_partition_by_name(file_path, "userdata", stop_event)
            
            if not partition_info:
                error_msg = "Could not find userdata partition in Android image. This may not be a valid Honda Android image."
                self._logger.error(error_msg)
                return [], error_msg
            
            offset, size = partition_info
            self._logger.info(f"Found userdata partition at offset {offset} (size: {size/1024/1024:.2f} MB)")
            
            if progress_callback:
                progress_callback("Found userdata partition, extracting filesystem...", 20)
                self._log_progress("Found userdata partition, extracting filesystem", 20)
            
            # Check for stop signal
            if stop_event and stop_event.is_set():
                self._logger.warning("Processing stopped by user before filesystem extraction")
                return [], "Processing stopped by user."
            
            # Extract CRM database
            self._logger.info("Starting CRM database extraction")
            crm_db_path = self._extract_crm_database(file_path, offset, size, progress_callback, stop_event)
            
            if not crm_db_path:
                error_msg = "Could not extract Honda CRM database from image. The database may not exist or be accessible."
                self._logger.error(error_msg)
                return [], error_msg
            
            self._logger.info(f"Successfully extracted CRM database to: {crm_db_path}")
            
            # Check for stop signal before database processing
            if stop_event and stop_event.is_set():
                self._logger.warning("Processing stopped by user before database processing")
                return [], "Processing stopped by user."
            
            if progress_callback:
                progress_callback("Processing CRM database...", 60)
                self._log_progress("Processing CRM database", 60)
            
            # Extract GPS data from database
            self._logger.info("Starting GPS data extraction from CRM database")
            entries = self._process_crm_database(crm_db_path, progress_callback, stop_event)
            
            # Check for stop signal after database processing
            if stop_event and stop_event.is_set():
                self._logger.warning(f"Processing stopped by user. Returning {len(entries)} partial results")
                return entries, "Processing stopped by user."  # Return partial results
            
            if not entries:
                error_msg = "No GPS data found in Honda CRM database. The eco_logs table may be empty or missing."
                self._logger.warning(error_msg)
                return [], error_msg
            
            # Cleanup temporary files
            self._logger.info("Starting cleanup of temporary files")
            self._cleanup_temp_files()
            
            elapsed_time = time.time() - start_time
            
            if progress_callback:
                progress_callback("Honda extraction complete!", 100)
                self._log_progress("Honda extraction complete", 100)
            
            self._log_extraction_complete(len(entries), elapsed_time)
            return entries, None
            
        except Exception as e:
            self._logger.error(f"Unexpected error during Honda extraction: {e}", exc_info=True)
            self._cleanup_temp_files()
            return [], f"Error processing Honda image: {str(e)}"
    
    def _find_partition_by_name(self, image_path: str, partition_name: str = "userdata", stop_event=None) -> Optional[Tuple[int, int]]:
        """Find partition offset and size by scanning for GPT or ext4 patterns"""
        self._logger.info(f"Searching for '{partition_name}' partition in image")
        
        try:
            with open(image_path, 'rb') as f:
                # Check for stop signal
                if stop_event and stop_event.is_set():
                    self._logger.debug("Partition search stopped by user")
                    return None
                
                # Try to find GPT header first
                self._logger.debug("Attempting to find GPT partition")
                gpt_result = self._find_gpt_partition(f, partition_name, stop_event)
                if gpt_result[0] is not None:
                    self._logger.info(f"Found partition via GPT at offset {gpt_result[0]}")
                    return gpt_result
                
                # Check for stop signal
                if stop_event and stop_event.is_set():
                    self._logger.debug("Partition search stopped by user")
                    return None
                
                # Try to find ext4 signature directly
                self._logger.debug("GPT search failed, attempting direct ext4 search")
                ext4_result = self._find_ext4_partition(f, stop_event)
                if ext4_result[0] is not None:
                    self._logger.info(f"Found partition via ext4 signature at offset {ext4_result[0]}")
                    return ext4_result
            
            self._logger.warning("No partition found using any method")
            return None
            
        except Exception as e:
            self._logger.error(f"Error during partition search: {e}", exc_info=True)
            return None
    
    def _find_gpt_partition(self, f: BinaryIO, partition_name: str, stop_event=None) -> Tuple[Optional[int], Optional[int]]:
        """Find partition using GPT (GUID Partition Table)"""
        self._logger.debug("Starting GPT partition search")
        
        try:
            # Check for stop signal
            if stop_event and stop_event.is_set():
                return None, None
            
            # GPT header is at LBA 1 (sector size 512)
            f.seek(512)
            gpt_header = f.read(92)
            
            if len(gpt_header) < 92 or gpt_header[:8] != b'EFI PART':
                self._logger.debug("No valid GPT header found at expected location")
                return None, None
            
            self._logger.debug("Found valid GPT header")
            
            # Parse GPT header
            partition_entries_lba, = struct.unpack('<Q', gpt_header[72:80])
            num_partitions, = struct.unpack('<I', gpt_header[80:84])
            partition_entry_size, = struct.unpack('<I', gpt_header[84:88])
            
            self._logger.debug(f"GPT: {num_partitions} partitions, entry size: {partition_entry_size}, "
                             f"entries start at LBA {partition_entries_lba}")
            
            # Read partition entries
            f.seek(partition_entries_lba * 512)
            
            for i in range(min(num_partitions, 128)):  # Reasonable limit
                # Check for stop signal periodically
                if stop_event and stop_event.is_set():
                    self._logger.debug("GPT search stopped by user")
                    return None, None
                
                entry = f.read(partition_entry_size)
                if len(entry) < 128:
                    self._logger.warning(f"Incomplete partition entry at index {i}")
                    break
                
                # Check if partition exists (non-zero GUID)
                if entry[:16] == b'\x00' * 16:
                    continue
                
                # Extract partition name (UTF-16LE, 72 bytes max)
                name_bytes = entry[56:128]
                try:
                    name = name_bytes.decode('utf-16le').rstrip('\x00')
                    self._logger.debug(f"Partition {i}: '{name}'")
                except:
                    self._logger.debug(f"Failed to decode partition {i} name")
                    continue
                
                if partition_name.lower() in name.lower():
                    start_lba, = struct.unpack('<Q', entry[32:40])
                    end_lba, = struct.unpack('<Q', entry[40:48])
                    
                    offset = start_lba * 512
                    size = (end_lba - start_lba + 1) * 512
                    
                    self._logger.info(f"Found '{name}' partition: offset={offset}, size={size/1024/1024:.2f}MB")
                    return offset, size
            
            self._logger.debug(f"Partition '{partition_name}' not found in GPT")
            
        except Exception as e:
            self._logger.error(f"Error parsing GPT: {e}")
            pass
        
        return None, None
    
    def _find_ext4_partition(self, f: BinaryIO, stop_event=None) -> Tuple[Optional[int], Optional[int]]:
        """Find ext4 partition by scanning for superblock signature"""
        self._logger.debug("Starting ext4 partition search")
        
        try:
            # Get file size
            current_pos = f.tell()
            f.seek(0, 2)  # Seek to end
            file_size = f.tell()
            f.seek(current_pos)  # Restore position
            
            self._logger.debug(f"File size: {file_size/1024/1024:.2f} MB")
            
            # ext4 superblock is at offset 1024 from partition start
            chunk_size = 4 * 1024 * 1024  # 4MB chunks
            max_search = min(file_size, 500 * 1024 * 1024)  # Search first 500MB
            
            self._logger.debug(f"Searching first {max_search/1024/1024:.0f} MB in {chunk_size/1024/1024:.0f} MB chunks")
            
            for offset in range(0, max_search, chunk_size):
                # Check for stop signal
                if stop_event and stop_event.is_set():
                    self._logger.debug("ext4 search stopped by user")
                    return None, None
                
                if offset % (50 * 1024 * 1024) == 0:  # Log every 50MB
                    self._logger.debug(f"Searching at offset {offset/1024/1024:.0f} MB")
                
                f.seek(offset)
                chunk = f.read(min(chunk_size, max_search - offset))
                
                # Look for ext4 magic number (0xEF53) at offset 1024 + 56
                for i in range(len(chunk) - 1080):
                    if chunk[i + 1024 + 56:i + 1024 + 58] == b'\x53\xEF':
                        partition_offset = offset + i
                        self._logger.debug(f"Found ext4 magic at offset {partition_offset}")
                        
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
                                self._logger.info(f"Valid ext4 filesystem found: {block_count} blocks of "
                                                f"{block_size} bytes = {partition_size/1024/1024:.2f} MB")
                                return partition_offset, partition_size
                            else:
                                self._logger.debug(f"Invalid ext4 parameters: block_size={block_size}, "
                                                 f"block_count={block_count}")
            
            self._logger.debug("No ext4 partition found")
            
        except Exception as e:
            self._logger.error(f"Error searching for ext4: {e}")
            pass
        
        return None, None
    
    def _extract_crm_database(self, image_path: str, offset: int, size: int, progress_callback=None, stop_event=None) -> Optional[str]:
        """Extract the Honda CRM database from the Android image"""
        self._logger.info(f"Extracting CRM database from partition at offset {offset}")
        
        try:
            # Check for stop signal
            if stop_event and stop_event.is_set():
                self._logger.debug("Database extraction stopped by user")
                return None
            
            # Create temporary file for partition
            temp_partition = tempfile.NamedTemporaryFile(delete=False, suffix='.img')
            self.temp_files.append(temp_partition.name)
            self._logger.debug(f"Created temporary partition file: {temp_partition.name}")
            
            if progress_callback:
                progress_callback("Extracting userdata partition...", 25)
                self._log_progress("Extracting userdata partition", 25)
            
            # Extract partition to temporary file with stop checking
            with open(image_path, 'rb') as src:
                src.seek(offset)
                remaining = size
                chunk_size = 8 * 1024 * 1024  # 8MB chunks
                bytes_extracted = 0
                
                self._logger.debug(f"Extracting {size/1024/1024:.2f} MB in {chunk_size/1024/1024:.0f} MB chunks")
                
                while remaining > 0:
                    # Check for stop signal during extraction
                    if stop_event and stop_event.is_set():
                        self._logger.warning("Partition extraction stopped by user")
                        temp_partition.close()
                        return None
                    
                    read_size = min(chunk_size, remaining)
                    chunk = src.read(read_size)
                    if not chunk:
                        break
                    temp_partition.write(chunk)
                    remaining -= len(chunk)
                    bytes_extracted += len(chunk)
                    
                    if bytes_extracted % (100 * 1024 * 1024) == 0:  # Log every 100MB
                        self._logger.debug(f"Extracted {bytes_extracted/1024/1024:.0f} MB / {size/1024/1024:.0f} MB")
            
            temp_partition.close()
            self._logger.info(f"Successfully extracted {bytes_extracted/1024/1024:.2f} MB to temporary file")
            
            # Check for stop signal
            if stop_event and stop_event.is_set():
                self._logger.debug("Database extraction stopped by user after partition extract")
                return None
            
            if progress_callback:
                progress_callback("Opening partition with TSK...", 35)
                self._log_progress("Opening partition with TSK", 35)
            
            # Open with TSK
            self._logger.debug("Opening partition with pytsk3")
            img = pytsk3.Img_Info(temp_partition.name)
            fs = pytsk3.FS_Info(img)
            
            self._logger.info(f"Filesystem opened successfully - Type: {fs.info.ftype}")
            
            # Try to extract CRM database
            crm_db_path = self._try_extract_crm_paths(fs, progress_callback, stop_event)
            
            if crm_db_path:
                self._logger.info(f"CRM database extracted to: {crm_db_path}")
            else:
                self._logger.error("Failed to extract CRM database")
                
            return crm_db_path
                
        except Exception as e:
            self._logger.error(f"Error extracting CRM database: {e}", exc_info=True)
            return None
    
    def _try_extract_crm_paths(self, fs, progress_callback=None, stop_event=None) -> Optional[str]:
        """Try extracting CRM database from multiple possible paths"""
        self._logger.info("Searching for CRM database in filesystem")
        
        # Common paths where Honda CRM database might be located
        search_paths = [
            "/data/com.honda.telematics.core/databases/crm.db",
            "/data/data/com.honda.telematics.core/databases/crm.db", 
            "data/com.honda.telematics.core/databases/crm.db",
            "data/data/com.honda.telematics.core/databases/crm.db",
            "/userdata/data/com.honda.telematics.core/databases/crm.db",
            "userdata/data/com.honda.telematics.core/databases/crm.db",
        ]
        
        self._logger.debug(f"Trying {len(search_paths)} known paths")
        
        for i, search_path in enumerate(search_paths):
            # Check for stop signal
            if stop_event and stop_event.is_set():
                self._logger.debug("Path search stopped by user")
                return None
            
            try:
                if progress_callback:
                    progress_callback(f"Trying path {i+1}/{len(search_paths)}: {search_path}", 40 + i * 2)
                
                self._logger.debug(f"Trying path: {search_path}")
                
                file_obj = fs.open(search_path)
                
                # Create temporary file for database
                temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
                self.temp_files.append(temp_db.name)
                
                # Read and write the file
                file_size = file_obj.info.meta.size
                self._logger.info(f"Found crm.db at {search_path} (size: {file_size} bytes)")
                
                data = file_obj.read_random(0, file_size)
                temp_db.write(data)
                temp_db.close()
                
                self._logger.info(f"Successfully extracted database to: {temp_db.name}")
                return temp_db.name
                
            except Exception as e:
                self._logger.debug(f"Path {search_path} not found: {e}")
                continue
        
        # Check for stop signal before recursive search
        if stop_event and stop_event.is_set():
            self._logger.debug("Path search stopped by user before recursive search")
            return None
        
        # If direct paths fail, try recursive search
        self._logger.info("Direct paths failed, starting recursive search for crm.db")
        if progress_callback:
            progress_callback("Starting recursive search for crm.db...", 50)
            self._log_progress("Starting recursive search for crm.db", 50)
        
        return self._recursive_search_crm(fs, stop_event)
    
    def _recursive_search_crm(self, fs, stop_event=None) -> Optional[str]:
        """Recursively search for crm.db files"""
        self._logger.info("Starting recursive search for crm.db")
        
        try:
            if self._search_directory(fs, fs.open_dir("/"), "/", 0, stop_event):
                # Return the last created temp file (should be crm.db)
                for temp_file in reversed(self.temp_files):
                    if temp_file.endswith('.db'):
                        self._logger.info(f"Found crm.db via recursive search: {temp_file}")
                        return temp_file
            
            self._logger.warning("Recursive search completed without finding crm.db")
            return None
            
        except Exception as e:
            self._logger.error(f"Error during recursive search: {e}")
            return None
    
    def _search_directory(self, fs, directory, current_path: str, depth: int, stop_event=None) -> bool:
        """Search directory recursively with depth limit and stop checking"""
        if depth > 10:  # Prevent infinite recursion
            self._logger.debug(f"Max recursion depth reached at: {current_path}")
            return False
        
        # Check for stop signal
        if stop_event and stop_event.is_set():
            return False
        
        if depth == 0:
            self._logger.debug(f"Searching root directory")
        else:
            self._logger.debug(f"Searching directory: {current_path} (depth: {depth})")
            
        try:
            entry_count = 0
            for entry in directory:
                entry_count += 1
                
                # Check for stop signal during directory iteration
                if stop_event and stop_event.is_set():
                    self._logger.debug("Directory search stopped by user")
                    return False
                
                try:
                    entry_name = entry.info.name.name.decode('utf-8', errors='ignore')
                except:
                    continue
                
                if entry_name in ['.', '..']:
                    continue
                
                full_path = f"{current_path}{entry_name}" if current_path.endswith('/') else f"{current_path}/{entry_name}"
                
                # Check if it's a regular file named crm.db
                if (entry.info.meta and 
                    entry.info.meta.type == pytsk3.TSK_FS_META_TYPE_REG and 
                    entry_name.lower() == "crm.db"):
                    
                    self._logger.info(f"Found crm.db at: {full_path}")
                    
                    try:
                        file_obj = fs.open(full_path)
                        
                        # Create temporary file for database
                        temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
                        self.temp_files.append(temp_db.name)
                        
                        # Read file data and write to temp file
                        file_size = file_obj.info.meta.size
                        self._logger.debug(f"Extracting crm.db (size: {file_size} bytes)")
                        
                        data = file_obj.read_random(0, file_size)
                        temp_db.write(data)
                        temp_db.close()
                        
                        self._logger.info(f"Successfully extracted crm.db to: {temp_db.name}")
                        return True
                        
                    except Exception as e:
                        self._logger.error(f"Failed to extract {full_path}: {e}")
                        pass
                
                # Recurse into directories that might contain Honda data
                elif (entry.info.meta and 
                      entry.info.meta.type == pytsk3.TSK_FS_META_TYPE_DIR and
                      any(keyword in entry_name.lower() for keyword in ['honda', 'telematics', 'data', 'app'])):
                    
                    try:
                        sub_dir = fs.open_dir(full_path)
                        if self._search_directory(fs, sub_dir, full_path, depth + 1, stop_event):
                            return True
                    except Exception as e:
                        self._logger.debug(f"Cannot open directory {full_path}: {e}")
                        continue
            
            self._logger.debug(f"Searched {entry_count} entries in {current_path}")
        
        except Exception as e:
            self._logger.error(f"Error searching directory {current_path}: {e}")
            pass
        
        return False
    
    def _process_crm_database(self, crm_db_path: str, progress_callback=None, stop_event=None) -> List[GPSEntry]:
        """Process the eco_logs table and convert to GPSEntry objects"""
        self._logger.info(f"Processing CRM database: {crm_db_path}")
        entries = []
        
        try:
            # Check for stop signal
            if stop_event and stop_event.is_set():
                self._logger.debug("Database processing stopped by user")
                return entries
            
            # Connect to the SQLite database
            self._logger.debug("Connecting to SQLite database")
            conn = sqlite3.connect(crm_db_path)
            cursor = conn.cursor()
            
            # Check if eco_logs table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='eco_logs';")
            result = cursor.fetchone()
            
            if not result:
                self._logger.warning("eco_logs table not found in database")
                conn.close()
                return entries
            
            self._logger.info("Found eco_logs table")
            
            if progress_callback:
                progress_callback("Reading eco_logs table...", 70)
                self._log_progress("Reading eco_logs table", 70)
            
            # Check for stop signal
            if stop_event and stop_event.is_set():
                conn.close()
                return entries
            
            # Check available columns
            cursor.execute("PRAGMA table_info(eco_logs);")
            columns_info = cursor.fetchall()
            columns = [row[1] for row in columns_info]
            
            self._logger.debug(f"eco_logs columns: {columns}")
            
            required_columns = [
                'start_pos_time', 'start_pos_lat', 'start_pos_lon',
                'finish_pos_time', 'finish_pos_lat', 'finish_pos_lon'
            ]
            
            # Check which columns are available
            available_required = [col for col in required_columns if col in columns]
            
            if not available_required:
                self._logger.error("No required columns found in eco_logs table")
                conn.close()
                return entries
            
            self._logger.info(f"Available required columns: {available_required}")
            
            # Query the available columns
            columns_str = ', '.join(available_required)
            query = f"SELECT {columns_str} FROM eco_logs WHERE start_pos_lat IS NOT NULL AND start_pos_lon IS NOT NULL"
            
            self._logger.debug(f"Executing query: {query}")
            cursor.execute(query)
            rows = cursor.fetchall()
            
            self._logger.info(f"Retrieved {len(rows)} records from eco_logs")
            
            if progress_callback:
                progress_callback(f"Processing {len(rows)} records...", 80)
                self._log_progress(f"Processing {len(rows)} records", 80)
            
            # Convert rows to GPSEntry objects
            valid_entries = 0
            invalid_entries = 0
            
            for i, row_data in enumerate(rows):
                # Check for stop signal during processing
                if stop_event and stop_event.is_set():
                    self._logger.warning(f"Database processing stopped by user at record {i}/{len(rows)}")
                    conn.close()
                    return entries  # Return partial results
                
                row_dict = dict(zip(available_required, row_data))
                
                # Extract coordinates and timestamps
                start_lat = self._safe_float(row_dict.get('start_pos_lat'))
                start_lon = self._safe_float(row_dict.get('start_pos_lon'))
                finish_lat = self._safe_float(row_dict.get('finish_pos_lat'))
                finish_lon = self._safe_float(row_dict.get('finish_pos_lon'))
                
                start_time = self._format_timestamp(row_dict.get('start_pos_time'))
                finish_time = self._format_timestamp(row_dict.get('finish_pos_time'))
                
                if i % 100 == 0:  # Log every 100 records
                    self._logger.debug(f"Processing record {i}: start=({start_lat}, {start_lon}), "
                                     f"finish=({finish_lat}, {finish_lon})")
                
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
                    valid_entries += 1
                else:
                    invalid_entries += 1
                
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
                    valid_entries += 1
                
                # Update progress periodically
                if progress_callback and i % 10 == 0 and len(rows) > 0:
                    progress = 80 + (10 * i // len(rows))
                    progress_callback(f"Processing record {i+1}/{len(rows)}", progress)
                    
                    if i % 100 == 0:
                        self._log_progress(f"Processing records ({i+1}/{len(rows)})", progress)
            
            conn.close()
            
            self._logger.info(f"Database processing complete. Valid positions: {valid_entries}, "
                            f"Invalid positions: {invalid_entries}")
            
            if progress_callback:
                progress_callback("Database processing complete!", 90)
                self._log_progress("Database processing complete", 90)
            
        except Exception as e:
            self._logger.error(f"Error processing CRM database: {e}", exc_info=True)
            # Silently fail - we'll return empty entries
            pass
        
        return entries
    
    def _safe_float(self, value) -> Optional[float]:
        """Safely convert value to float"""
        if value is None:
            return None
        try:
            result = float(value)
            return result
        except (ValueError, TypeError) as e:
            self._logger.debug(f"Failed to convert '{value}' to float: {e}")
            return None
    
    def _is_valid_coordinate(self, lat: float, lon: float) -> bool:
        """Check if coordinates are valid GPS values"""
        # Basic range check
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            self._logger.debug(f"Coordinates out of valid range: lat={lat}, lon={lon}")
            return False
            
        # Check for null island
        if lat == 0 and lon == 0:
            self._logger.debug(f"Null island coordinates detected (0, 0)")
            return False
            
        return True
    
    def _format_timestamp(self, timestamp) -> str:
        """Format timestamp as datetime string"""
        if not timestamp:
            return ''
        
        self._logger.debug(f"Formatting timestamp: {timestamp} (type: {type(timestamp)})")
        
        try:
            # Try to parse as Unix timestamp (milliseconds)
            if isinstance(timestamp, (int, float)):
                if timestamp > 1e12:  # Milliseconds
                    ts = timestamp / 1000.0
                else:  # Seconds
                    ts = timestamp
                
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                formatted = dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                self._logger.debug(f"Formatted timestamp: {formatted}")
                return formatted
            
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
                        formatted = dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                        self._logger.debug(f"Parsed string timestamp with format '{fmt}': {formatted}")
                        return formatted
                    except ValueError:
                        continue
                
                # Try parsing as Unix timestamp string
                try:
                    ts = float(timestamp)
                    if ts > 1e12:  # Milliseconds
                        ts = ts / 1000.0
                    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                    formatted = dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                    self._logger.debug(f"Parsed string as Unix timestamp: {formatted}")
                    return formatted
                except ValueError:
                    pass
            
        except Exception as e:
            self._logger.error(f"Error formatting timestamp '{timestamp}': {e}")
            pass
        
        # Return original value as string if parsing fails
        result = str(timestamp) if timestamp else ''
        self._logger.debug(f"Failed to parse timestamp, returning as string: '{result}'")
        return result
    
    def _cleanup_temp_files(self):
        """Clean up all temporary files"""
        self._logger.info(f"Cleaning up {len(self.temp_files)} temporary files")
        
        cleaned = 0
        for temp_file in self.temp_files:
            try:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)
                    cleaned += 1
                    self._logger.debug(f"Deleted temporary file: {temp_file}")
            except Exception as e:
                self._logger.error(f"Failed to delete temporary file {temp_file}: {e}")
                pass
        
        self._logger.info(f"Cleaned up {cleaned}/{len(self.temp_files)} temporary files")
        self.temp_files.clear()
    
    def __del__(self):
        """Cleanup when object is destroyed"""
        if hasattr(self, 'temp_files') and self.temp_files:
            self._logger.debug("Running cleanup in destructor")
            self._cleanup_temp_files()