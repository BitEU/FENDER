#!/usr/bin/env python3
"""
QNX Forensic Analysis Tool for Windows
Author: Computer Science Forensics Research Team
Purpose: Analyze QNX filesystems from disk images on Windows workstations
Target: Logical partitions 13 and 14 containing forensic data
"""

import os
import sys
import struct
import datetime
import argparse
import cmd
import logging
import json
from typing import Optional, List, Dict, Tuple, BinaryIO
from dataclasses import dataclass
from enum import IntEnum


# Configure logging
def setup_logging(log_file='qnx_forensic.log', verbose=False):
    """Setup comprehensive logging"""
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # File handler - always detailed
    file_handler = logging.FileHandler(log_file, mode='w')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(log_format))
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    console_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    
    # Root logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger


# Constants for QNX6 filesystem
QNX6_MAGIC = 0x68191122
QNX6_SUPERBLOCK_SIZE = 0x200
QNX6_BOOTBLOCK_SIZE = 0x2000
QNX6_DIR_ENTRY_SIZE = 32
QNX6_INODE_SIZE = 128
QNX6_INODE_SIZE_BITS = 7  # log2(128)

# MBR Partition types
PART_TYPE_EXTENDED = 0x05
PART_TYPE_EXTENDED_LBA = 0x0F
PART_TYPE_QNX4 = 0x4D
PART_TYPE_QNX6 = 0x4E
PART_TYPE_QNX6_2 = 0xB1  # Alternative QNX6 type
PART_TYPE_QNX_GENERIC = [0x4D, 0x4E, 0x4F, 0xB1, 0xB2, 0xB3]

# Filesystem block sizes
VALID_BLOCK_SIZES = [512, 1024, 2048, 4096]


class FileType(IntEnum):
    """QNX6 file types"""
    FIFO = 0x1000
    CHR = 0x2000
    DIR = 0x4000
    BLK = 0x6000
    REG = 0x8000
    LNK = 0xA000
    SOCK = 0xC000


@dataclass
class MBRPartition:
    """MBR Partition Table Entry"""
    number: int  # Partition number (1-4 for primary, 5+ for logical)
    status: int
    start_chs: tuple
    partition_type: int
    end_chs: tuple
    start_lba: int
    size_sectors: int
    
    @property
    def is_extended(self):
        return self.partition_type in [PART_TYPE_EXTENDED, PART_TYPE_EXTENDED_LBA]
    
    @property
    def is_qnx(self):
        return self.partition_type in PART_TYPE_QNX_GENERIC
    
    @property
    def size_bytes(self):
        return self.size_sectors * 512
    
    @property
    def end_lba(self):
        return self.start_lba + self.size_sectors


@dataclass
class QNX6SuperBlock:
    """QNX6 Superblock structure"""
    magic: int
    checksum: int
    serial: int
    ctime: int
    atime: int
    flags: int
    version1: int
    version2: int
    volumeid: bytes
    blocksize: int
    num_inodes: int
    free_inodes: int
    num_blocks: int
    free_blocks: int
    allocgroup: int
    root: Dict  # Root node info
    bitmap: Dict  # Bitmap info
    longfile: Dict  # Long filename info
    unknown: Dict  # Unknown/reserved


@dataclass
class QNX6Inode:
    """QNX6 Inode structure"""
    size: int
    uid: int
    gid: int
    ftime: int
    mtime: int
    atime: int
    ctime: int
    mode: int
    blocks: List[int]
    levels: int
    status: int
    unknown: bytes


class QNX6Parser:
    """Parser for QNX6 filesystem structures"""
    
    def __init__(self, file_handle: BinaryIO, partition_offset: int, block_size: int = 4096):
        self.file = file_handle
        self.partition_offset = partition_offset
        self.block_size = block_size
        self.superblock = None
        self.current_dir = "/"
        self.inode_cache = {}
        self.logger = logging.getLogger(f'QNX6Parser@{hex(partition_offset)}')
        
        self.logger.info(f"Initialized QNX6Parser at offset {hex(partition_offset)} with block size {block_size}")
        
    def read_at(self, offset: int, size: int) -> bytes:
        """Read data at specific offset"""
        try:
            abs_offset = self.partition_offset + offset
            self.file.seek(abs_offset)
            data = self.file.read(size)
            self.logger.debug(f"Read {len(data)} bytes from offset {hex(abs_offset)} (partition offset {hex(offset)})")
            return data
        except Exception as e:
            self.logger.error(f"Failed to read at offset {hex(offset)}: {e}")
            raise
    
    def read_block(self, block_num: int) -> bytes:
        """Read a filesystem block"""
        offset = block_num * self.block_size
        self.logger.debug(f"Reading block {block_num} at offset {hex(offset)}")
        return self.read_at(offset, self.block_size)
    
    def parse_superblock(self) -> Optional[QNX6SuperBlock]:
        """Parse QNX6 superblock"""
        self.logger.info("Attempting to parse QNX6 superblock")
        
        # Try both superblock locations
        for sb_num, sb_offset in enumerate([QNX6_BOOTBLOCK_SIZE, QNX6_BOOTBLOCK_SIZE + QNX6_SUPERBLOCK_SIZE]):
            self.logger.debug(f"Trying superblock location {sb_num + 1} at offset {hex(sb_offset)}")
            
            try:
                data = self.read_at(sb_offset, QNX6_SUPERBLOCK_SIZE)
                
                # Check magic
                magic = struct.unpack_from("<I", data, 0)[0]
                self.logger.debug(f"Found magic: {hex(magic)} (expected {hex(QNX6_MAGIC)})")
                
                if magic != QNX6_MAGIC:
                    self.logger.debug(f"Invalid magic at superblock location {sb_num + 1}")
                    continue
                    
                # Parse superblock fields
                sb = QNX6SuperBlock(
                    magic=magic,
                    checksum=struct.unpack_from("<I", data, 4)[0],
                    serial=struct.unpack_from("<Q", data, 8)[0],
                    ctime=struct.unpack_from("<I", data, 16)[0],
                    atime=struct.unpack_from("<I", data, 20)[0],
                    flags=struct.unpack_from("<I", data, 24)[0],
                    version1=struct.unpack_from("<H", data, 28)[0],
                    version2=struct.unpack_from("<H", data, 30)[0],
                    volumeid=data[32:48],
                    blocksize=struct.unpack_from("<I", data, 48)[0],
                    num_inodes=struct.unpack_from("<I", data, 52)[0],
                    free_inodes=struct.unpack_from("<I", data, 56)[0],
                    num_blocks=struct.unpack_from("<I", data, 60)[0],
                    free_blocks=struct.unpack_from("<I", data, 64)[0],
                    allocgroup=struct.unpack_from("<I", data, 68)[0],
                    root=self._parse_root_node(data, 72),
                    bitmap=self._parse_root_node(data, 128),
                    longfile=self._parse_root_node(data, 184),
                    unknown=self._parse_root_node(data, 240)
                )
                
                self.logger.info(f"Successfully parsed superblock:")
                self.logger.info(f"  Serial: {sb.serial}")
                self.logger.info(f"  Block size: {sb.blocksize}")
                self.logger.info(f"  Total blocks: {sb.num_blocks}")
                self.logger.info(f"  Total inodes: {sb.num_inodes}")
                self.logger.info(f"  Volume ID: {sb.volumeid.hex()}")
                
                # Validate block size
                if sb.blocksize in VALID_BLOCK_SIZES:
                    self.block_size = sb.blocksize
                    self.superblock = sb
                    return sb
                else:
                    self.logger.warning(f"Invalid block size: {sb.blocksize}")
                    
            except Exception as e:
                self.logger.error(f"Error parsing superblock at location {sb_num + 1}: {e}")
                
        self.logger.error("Failed to find valid QNX6 superblock")
        return None
    
    def _parse_root_node(self, data: bytes, offset: int) -> Dict:
        """Parse root node structure"""
        node = {
            'size': struct.unpack_from("<Q", data, offset)[0],
            'blocks': struct.unpack_from("<8I", data, offset + 8),
            'levels': struct.unpack_from("<B", data, offset + 40)[0],
            'mode': struct.unpack_from("<B", data, offset + 41)[0],
            'reserved': data[offset + 42:offset + 56]
        }
        self.logger.debug(f"Parsed root node at offset {hex(offset)}: size={node['size']}, levels={node['levels']}")
        return node
    
    def read_inode(self, inode_num: int) -> Optional[QNX6Inode]:
        """Read an inode by number"""
        if inode_num in self.inode_cache:
            self.logger.debug(f"Returning cached inode {inode_num}")
            return self.inode_cache[inode_num]
            
        self.logger.debug(f"Reading inode {inode_num}")
        
        try:
            # Calculate inode location
            inodes_per_block = self.block_size // QNX6_INODE_SIZE
            block_num = inode_num // inodes_per_block
            block_offset = (inode_num % inodes_per_block) * QNX6_INODE_SIZE
            
            self.logger.debug(f"Inode {inode_num}: block {block_num}, offset {block_offset}")
            
            # Read from root inode tree
            inode_block = self._read_from_inode_tree(block_num)
            if not inode_block:
                self.logger.error(f"Failed to read inode block for inode {inode_num}")
                return None
                
            data = inode_block[block_offset:block_offset + QNX6_INODE_SIZE]
            
            # Parse inode
            inode = QNX6Inode(
                size=struct.unpack_from("<Q", data, 0)[0],
                uid=struct.unpack_from("<I", data, 8)[0],
                gid=struct.unpack_from("<I", data, 12)[0],
                ftime=struct.unpack_from("<I", data, 16)[0],
                mtime=struct.unpack_from("<I", data, 20)[0],
                atime=struct.unpack_from("<I", data, 24)[0],
                ctime=struct.unpack_from("<I", data, 28)[0],
                mode=struct.unpack_from("<H", data, 32)[0],
                blocks=[struct.unpack_from("<I", data, 40 + i*4)[0] for i in range(16)],
                levels=data[104],
                status=data[105],
                unknown=data[106:128]
            )
            
            self.logger.debug(f"Inode {inode_num}: size={inode.size}, mode={oct(inode.mode)}, levels={inode.levels}")
            
            self.inode_cache[inode_num] = inode
            return inode
            
        except Exception as e:
            self.logger.error(f"Failed to read inode {inode_num}: {e}")
            return None
    
    def _read_from_inode_tree(self, block_num: int) -> Optional[bytes]:
        """Read block from inode tree"""
        root = self.superblock.root
        self.logger.debug(f"Reading from inode tree: block_num={block_num}, root levels={root['levels']}, root blocks={[b for b in root['blocks'] if b != 0][:4]}")
        return self._read_indirect_block(root['blocks'], root['levels'], block_num)
    
    def _read_indirect_block(self, blocks: List[int], levels: int, target_block: int) -> Optional[bytes]:
        """Navigate indirect block tree"""
        self.logger.debug(f"Reading indirect block: levels={levels}, target_block={target_block}, blocks={[b for b in blocks if b != 0][:4]}")
        
        # Find the first non-zero block
        valid_blocks = [b for b in blocks if b != 0]
        if not valid_blocks:
            self.logger.error("No valid blocks in indirect block list")
            return None
        
        if levels == 0:
            # Direct blocks
            if target_block < len(valid_blocks):
                block_ptr = valid_blocks[target_block]
                self.logger.debug(f"Direct block access: reading block {block_ptr}")
                return self.read_block(block_ptr)
            else:
                self.logger.debug(f"Target block {target_block} out of range for direct blocks (have {len(valid_blocks)})")
                return None
            
        # Calculate blocks per indirect level
        ptrs_per_block = self.block_size // 4
        
        self.logger.debug(f"Indirect block access: ptrs_per_block={ptrs_per_block}")
        
        # For single or multi-level indirect blocks
        # If we have indirect blocks, we need to follow the tree
        if levels == 1:
            # Single indirect - each block pointer points to a block of pointers
            indirect_block_idx = target_block // ptrs_per_block
            ptr_idx_in_block = target_block % ptrs_per_block
            
            if indirect_block_idx >= len(valid_blocks):
                self.logger.debug(f"Indirect block index {indirect_block_idx} out of range")
                return None
                
            indirect_block_ptr = valid_blocks[indirect_block_idx]
            if indirect_block_ptr == 0:
                return None
                
            self.logger.debug(f"Reading indirect block {indirect_block_ptr} to get pointer at index {ptr_idx_in_block}")
            indirect_data = self.read_block(indirect_block_ptr)
            
            # Get the pointer to the actual data block
            data_block_ptr = struct.unpack_from("<I", indirect_data, ptr_idx_in_block * 4)[0]
            if data_block_ptr == 0:
                return None
                
            self.logger.debug(f"Reading data block {data_block_ptr}")
            return self.read_block(data_block_ptr)
            
        else:
            # Multi-level indirect
            blocks_per_ptr = ptrs_per_block ** (levels - 1)
            indirect_block_idx = target_block // blocks_per_ptr
            
            if indirect_block_idx >= len(valid_blocks):
                self.logger.debug(f"Multi-level indirect block index {indirect_block_idx} out of range")
                return None
                
            indirect_block_ptr = valid_blocks[indirect_block_idx]
            if indirect_block_ptr == 0:
                return None
                
            self.logger.debug(f"Reading multi-level indirect block {indirect_block_ptr}")
            indirect_data = self.read_block(indirect_block_ptr)
            
            # Get all pointers from this indirect block
            child_blocks = []
            for i in range(ptrs_per_block):
                ptr = struct.unpack_from("<I", indirect_data, i * 4)[0]
                if ptr != 0:
                    child_blocks.append(ptr)
                    
            if not child_blocks:
                return None
                
            # Recurse with reduced level
            relative_block = target_block % blocks_per_ptr
            return self._read_indirect_block(child_blocks, levels - 1, relative_block)
                        
        return None
    
    def read_directory(self, inode: QNX6Inode) -> List[Dict]:
        """Read directory entries from an inode"""
        entries = []
        
        try:
            # Read directory data
            dir_data = self.read_file_data(inode)
            if not dir_data:
                self.logger.warning("No directory data found")
                return entries
                
            # Parse directory entries
            offset = 0
            while offset + QNX6_DIR_ENTRY_SIZE <= len(dir_data):
                entry_data = dir_data[offset:offset + QNX6_DIR_ENTRY_SIZE]
                
                inode_num = struct.unpack_from("<I", entry_data, 0)[0]
                if inode_num == 0:
                    offset += QNX6_DIR_ENTRY_SIZE
                    continue
                    
                name_len = entry_data[4]
                name = entry_data[5:5 + name_len].decode('utf-8', errors='replace').rstrip('\x00')
                
                if name and name not in ['.', '..']:
                    entry = {
                        'inode': inode_num,
                        'name': name,
                        'type': self._get_file_type(inode_num)
                    }
                    entries.append(entry)
                    self.logger.debug(f"Found directory entry: {name} (inode {inode_num})")
                    
                offset += QNX6_DIR_ENTRY_SIZE
                
        except Exception as e:
            self.logger.error(f"Error reading directory: {e}")
            
        return entries
    
    def read_file_data(self, inode: QNX6Inode) -> bytes:
        """Read file data from inode"""
        self.logger.debug(f"Reading file data: size={inode.size}, levels={inode.levels}")
        
        try:
            data = bytearray()
            blocks_to_read = (inode.size + self.block_size - 1) // self.block_size
            
            if inode.levels == 0:
                # Direct blocks
                for i in range(min(blocks_to_read, 16)):
                    if inode.blocks[i]:
                        block_data = self.read_block(inode.blocks[i])
                        data.extend(block_data)
            else:
                # Indirect blocks
                for i in range(blocks_to_read):
                    block_data = self._read_indirect_block(inode.blocks, inode.levels, i)
                    if block_data:
                        data.extend(block_data)
                        
            return bytes(data[:inode.size])
            
        except Exception as e:
            self.logger.error(f"Error reading file data: {e}")
            return b''
    
    def _get_file_type(self, inode_num: int) -> str:
        """Get file type from inode"""
        try:
            inode = self.read_inode(inode_num)
            if not inode:
                return "unknown"
                
            mode = inode.mode & 0xF000
            if mode == FileType.DIR:
                return "dir"
            elif mode == FileType.REG:
                return "file"
            elif mode == FileType.LNK:
                return "link"
            else:
                return "special"
        except:
            return "unknown"
    
    def scan_for_files(self, extensions: List[str], output_dir: str) -> List[Dict]:
        """Recursively scan filesystem for files with given extensions"""
        self.logger.info(f"Scanning for files with extensions: {extensions}")
        found_files = []
        
        def scan_directory(inode_num: int, path: str):
            try:
                inode = self.read_inode(inode_num)
                if not inode or (inode.mode & 0xF000) != FileType.DIR:
                    return
                    
                entries = self.read_directory(inode)
                
                for entry in entries:
                    entry_path = os.path.join(path, entry['name']).replace('\\', '/')
                    
                    if entry['type'] == 'dir':
                        # Recurse into subdirectory
                        scan_directory(entry['inode'], entry_path)
                    elif entry['type'] == 'file':
                        # Check if file matches our extensions
                        for ext in extensions:
                            if entry['name'].lower().endswith(ext.lower()):
                                self.logger.info(f"Found matching file: {entry_path}")
                                
                                # Read file data
                                file_inode = self.read_inode(entry['inode'])
                                if file_inode:
                                    file_info = {
                                        'path': entry_path,
                                        'name': entry['name'],
                                        'inode': entry['inode'],
                                        'size': file_inode.size,
                                        'mtime': file_inode.mtime,
                                        'extracted': False,
                                        'error': None
                                    }
                                    
                                    # Try to extract file
                                    try:
                                        data = self.read_file_data(file_inode)
                                        
                                        # Create output path
                                        safe_name = entry['name'].replace('/', '_').replace('\\', '_')
                                        output_path = os.path.join(output_dir, safe_name)
                                        
                                        # Handle duplicate names
                                        if os.path.exists(output_path):
                                            base, ext = os.path.splitext(output_path)
                                            counter = 1
                                            while os.path.exists(f"{base}_{counter}{ext}"):
                                                counter += 1
                                            output_path = f"{base}_{counter}{ext}"
                                        
                                        # Write file
                                        with open(output_path, 'wb') as f:
                                            f.write(data)
                                            
                                        file_info['extracted'] = True
                                        file_info['output_path'] = output_path
                                        self.logger.info(f"Extracted {entry_path} to {output_path}")
                                        
                                    except Exception as e:
                                        file_info['error'] = str(e)
                                        self.logger.error(f"Failed to extract {entry_path}: {e}")
                                    
                                    found_files.append(file_info)
                                break
                                
            except Exception as e:
                self.logger.error(f"Error scanning directory {path}: {e}")
        
        # Start scan from root
        scan_directory(1, "/")
        return found_files


class MBRParser:
    """Parser for Master Boot Record and partition tables"""
    
    def __init__(self, file_handle: BinaryIO):
        self.file = file_handle
        self.partitions = []
        self.logger = logging.getLogger('MBRParser')
        
    def parse_mbr(self) -> List[MBRPartition]:
        """Parse the Master Boot Record and all partitions"""
        self.logger.info("Parsing Master Boot Record")
        
        try:
            self.file.seek(0)
            mbr = self.file.read(512)
            
            # Check MBR signature
            signature = mbr[510:512]
            self.logger.debug(f"MBR signature: {signature.hex()}")
            
            if signature != b'\x55\xAA':
                self.logger.error(f"Invalid MBR signature: {signature.hex()}")
                raise ValueError("Invalid MBR signature")
                
            # Parse partition table (4 entries at offset 446)
            self.logger.info("Parsing primary partitions")
            
            for i in range(4):
                offset = 446 + (i * 16)
                entry = mbr[offset:offset + 16]
                
                partition = MBRPartition(
                    number=i + 1,
                    status=entry[0],
                    start_chs=(entry[1], entry[2], entry[3]),
                    partition_type=entry[4],
                    end_chs=(entry[5], entry[6], entry[7]),
                    start_lba=struct.unpack("<I", entry[8:12])[0],
                    size_sectors=struct.unpack("<I", entry[12:16])[0]
                )
                
                if partition.partition_type != 0:
                    self.partitions.append(partition)
                    self.logger.info(f"Found primary partition {i+1}: type=0x{partition.partition_type:02X}, "
                                   f"start={partition.start_lba}, size={partition.size_sectors}")
                    
                    # If extended partition, parse logical partitions
                    if partition.is_extended:
                        self.logger.info(f"Partition {i+1} is extended, parsing logical partitions")
                        self._parse_extended_partitions(partition)
                        
            self.logger.info(f"Total partitions found: {len(self.partitions)}")
            return self.partitions
            
        except Exception as e:
            self.logger.error(f"Failed to parse MBR: {e}")
            raise
    
    def _parse_extended_partitions(self, extended_part: MBRPartition):
        """Parse logical partitions within an extended partition"""
        self.logger.info(f"Parsing logical partitions in extended partition at LBA {extended_part.start_lba}")
        
        base_ebr = extended_part.start_lba
        current_ebr = base_ebr
        logical_num = 5  # Logical partitions start at 5
        
        try:
            while current_ebr:
                self.logger.debug(f"Reading EBR at LBA {current_ebr}")
                
                self.file.seek(current_ebr * 512)
                ebr = self.file.read(512)
                
                # Check EBR signature
                signature = ebr[510:512]
                if signature != b'\x55\xAA':
                    self.logger.warning(f"Invalid EBR signature at LBA {current_ebr}: {signature.hex()}")
                    break
                    
                # Parse first entry (actual logical partition)
                entry = ebr[446:462]
                
                part_type = entry[4]
                start_offset = struct.unpack("<I", entry[8:12])[0]
                size_sectors = struct.unpack("<I", entry[12:16])[0]
                
                if part_type != 0 and size_sectors != 0:
                    partition = MBRPartition(
                        number=logical_num,
                        status=entry[0],
                        start_chs=(entry[1], entry[2], entry[3]),
                        partition_type=part_type,
                        end_chs=(entry[5], entry[6], entry[7]),
                        start_lba=current_ebr + start_offset,
                        size_sectors=size_sectors
                    )
                    
                    self.partitions.append(partition)
                    self.logger.info(f"Found logical partition {logical_num}: type=0x{part_type:02X}, "
                                   f"start={partition.start_lba}, size={size_sectors}")
                    logical_num += 1
                    
                # Parse second entry (link to next EBR)
                entry2 = ebr[462:478]
                next_ebr_offset = struct.unpack("<I", entry2[8:12])[0]
                
                self.logger.debug(f"Next EBR offset: {next_ebr_offset}")
                
                if next_ebr_offset == 0:
                    self.logger.info("No more logical partitions")
                    break
                    
                # Next EBR is relative to the start of the extended partition
                current_ebr = base_ebr + next_ebr_offset
                
                # Safety check to prevent infinite loops
                if logical_num > 60:  # Maximum 60 logical partitions
                    self.logger.warning("Too many logical partitions, stopping")
                    break
                    
        except Exception as e:
            self.logger.error(f"Error parsing logical partitions: {e}")


class QNXShell(cmd.Cmd):
    """Interactive shell for QNX filesystem exploration"""
    
    intro = "QNX Forensic Shell v1.0\nType 'help' for commands\n"
    prompt = "qnx> "
    
    def __init__(self, parser: QNX6Parser):
        super().__init__()
        self.parser = parser
        self.current_inode = 1  # Root inode - QNX6 typically uses inode 1
        self.current_path = "/"
        self.logger = logging.getLogger('QNXShell')
        
        # Try to find the actual root inode
        self.logger.info("Initializing shell, looking for root inode")
        
        # Try different possible root inode numbers
        for possible_root in [1, 2, 0]:
            try:
                inode = self.parser.read_inode(possible_root)
                if inode and (inode.mode & 0xF000) == FileType.DIR:
                    self.current_inode = possible_root
                    self.logger.info(f"Found root directory at inode {possible_root}")
                    break
            except Exception as e:
                self.logger.debug(f"Inode {possible_root} is not root: {e}")
        else:
            self.logger.warning("Could not find root directory inode, defaulting to 1")
        
    def do_ls(self, arg):
        """List directory contents"""
        try:
            inode = self.parser.read_inode(self.current_inode)
            if not inode or (inode.mode & 0xF000) != FileType.DIR:
                print("Error: Not a directory")
                return
                
            entries = self.parser.read_directory(inode)
            
            print(f"Directory: {self.current_path}")
            print(f"{'Type':<8} {'Inode':<10} {'Size':<12} {'Modified':<20} {'Name'}")
            print("-" * 80)
            
            for entry in sorted(entries, key=lambda x: x['name']):
                # Get additional info
                entry_inode = self.parser.read_inode(entry['inode'])
                if entry_inode:
                    size = entry_inode.size if entry['type'] == 'file' else '-'
                    mtime = datetime.datetime.fromtimestamp(entry_inode.mtime).strftime('%Y-%m-%d %H:%M:%S')
                else:
                    size = '?'
                    mtime = '?'
                    
                print(f"{entry['type']:<8} {entry['inode']:<10} {str(size):<12} {mtime:<20} {entry['name']}")
                
        except Exception as e:
            print(f"Error listing directory: {e}")
            self.logger.error(f"Error in ls command: {e}", exc_info=True)
    
    def do_cd(self, path):
        """Change directory"""
        if not path:
            return
            
        try:
            if path == "/":
                self.current_inode = 1
                self.current_path = "/"
                return
                
            if path == "..":
                # Go to parent directory
                if self.current_path != "/":
                    self.current_path = os.path.dirname(self.current_path)
                    # Find parent inode (simplified - should traverse properly)
                    self.current_inode = 1  # For now, just go to root
                return
                
            # Find target directory
            inode = self.parser.read_inode(self.current_inode)
            entries = self.parser.read_directory(inode)
            
            for entry in entries:
                if entry['name'] == path and entry['type'] == 'dir':
                    self.current_inode = entry['inode']
                    if self.current_path == "/":
                        self.current_path = f"/{path}"
                    else:
                        self.current_path = f"{self.current_path}/{path}"
                    return
                    
            print(f"Directory not found: {path}")
            
        except Exception as e:
            print(f"Error changing directory: {e}")
            self.logger.error(f"Error in cd command: {e}", exc_info=True)
    
    def do_cat(self, filename):
        """Display file contents"""
        if not filename:
            print("Usage: cat <filename>")
            return
            
        try:
            # Find file in current directory
            inode = self.parser.read_inode(self.current_inode)
            entries = self.parser.read_directory(inode)
            
            for entry in entries:
                if entry['name'] == filename and entry['type'] == 'file':
                    file_inode = self.parser.read_inode(entry['inode'])
                    if file_inode:
                        data = self.parser.read_file_data(file_inode)
                        # Try to decode as text
                        try:
                            text = data.decode('utf-8')
                            print(text)
                        except:
                            try:
                                text = data.decode('latin-1')
                                print(text)
                            except:
                                print(f"Binary file ({len(data)} bytes)")
                                print("First 256 bytes (hex):")
                                print(data[:256].hex())
                    return
                    
            print(f"File not found: {filename}")
            
        except Exception as e:
            print(f"Error reading file: {e}")
            self.logger.error(f"Error in cat command: {e}", exc_info=True)
    
    def do_info(self, filename):
        """Show file/directory information"""
        if not filename:
            filename = "."
            
        try:
            if filename == ".":
                target_inode = self.current_inode
            else:
                # Find file in current directory
                inode = self.parser.read_inode(self.current_inode)
                entries = self.parser.read_directory(inode)
                
                target_inode = None
                for entry in entries:
                    if entry['name'] == filename:
                        target_inode = entry['inode']
                        break
                        
                if not target_inode:
                    print(f"Not found: {filename}")
                    return
                    
            inode = self.parser.read_inode(target_inode)
            if inode:
                print(f"Inode: {target_inode}")
                print(f"Size: {inode.size} bytes")
                print(f"Mode: {oct(inode.mode)}")
                print(f"Type: {self._get_file_type_string(inode.mode)}")
                print(f"UID/GID: {inode.uid}/{inode.gid}")
                print(f"Modified: {datetime.datetime.fromtimestamp(inode.mtime)}")
                print(f"Created: {datetime.datetime.fromtimestamp(inode.ctime)}")
                print(f"Accessed: {datetime.datetime.fromtimestamp(inode.atime)}")
                print(f"File time: {datetime.datetime.fromtimestamp(inode.ftime)}")
                print(f"Levels: {inode.levels}")
                print(f"Direct blocks: {[b for b in inode.blocks if b != 0][:8]}")
                
        except Exception as e:
            print(f"Error getting info: {e}")
            self.logger.error(f"Error in info command: {e}", exc_info=True)
    
    def _get_file_type_string(self, mode):
        """Get human-readable file type from mode"""
        file_type = mode & 0xF000
        if file_type == FileType.DIR:
            return "Directory"
        elif file_type == FileType.REG:
            return "Regular file"
        elif file_type == FileType.LNK:
            return "Symbolic link"
        elif file_type == FileType.BLK:
            return "Block device"
        elif file_type == FileType.CHR:
            return "Character device"
        elif file_type == FileType.FIFO:
            return "FIFO"
        elif file_type == FileType.SOCK:
            return "Socket"
        else:
            return f"Unknown (0x{file_type:04X})"
    
    def do_extract(self, args):
        """Extract file to Windows filesystem: extract <source> <destination>"""
        parts = args.split()
        if len(parts) != 2:
            print("Usage: extract <source_file> <destination_path>")
            return
            
        source, dest = parts
        
        try:
            # Find file in current directory
            inode = self.parser.read_inode(self.current_inode)
            entries = self.parser.read_directory(inode)
            
            for entry in entries:
                if entry['name'] == source and entry['type'] == 'file':
                    file_inode = self.parser.read_inode(entry['inode'])
                    if file_inode:
                        data = self.parser.read_file_data(file_inode)
                        with open(dest, 'wb') as f:
                            f.write(data)
                        print(f"Extracted {len(data)} bytes to {dest}")
                        self.logger.info(f"Extracted {source} ({len(data)} bytes) to {dest}")
                    return
                    
            print(f"File not found: {source}")
            
        except Exception as e:
            print(f"Error extracting file: {e}")
            self.logger.error(f"Error in extract command: {e}", exc_info=True)
    
    def do_pwd(self, arg):
        """Print current directory"""
        print(self.current_path)
    
    def do_find(self, pattern):
        """Find files matching pattern (e.g., *.txt)"""
        if not pattern:
            print("Usage: find <pattern>")
            return
            
        import fnmatch
        
        print(f"Searching for files matching '{pattern}'...")
        matches = []
        
        def search_dir(inode_num, path):
            try:
                inode = self.parser.read_inode(inode_num)
                if not inode or (inode.mode & 0xF000) != FileType.DIR:
                    return
                    
                entries = self.parser.read_directory(inode)
                
                for entry in entries:
                    entry_path = os.path.join(path, entry['name']).replace('\\', '/')
                    
                    if entry['type'] == 'dir':
                        search_dir(entry['inode'], entry_path)
                    elif fnmatch.fnmatch(entry['name'], pattern):
                        matches.append(entry_path)
                        
            except Exception as e:
                self.logger.error(f"Error searching directory {path}: {e}")
        
        search_dir(1, "/")
        
        if matches:
            print(f"\nFound {len(matches)} matches:")
            for match in sorted(matches):
                print(f"  {match}")
        else:
            print("No matches found")
    
    def do_debug(self, arg):
        """Show debug information about the filesystem"""
        if not self.parser.superblock:
            print("No superblock loaded")
            return
            
        sb = self.parser.superblock
        print("Filesystem Debug Information:")
        print(f"  Block size: {sb.blocksize}")
        print(f"  Total blocks: {sb.num_blocks}")
        print(f"  Total inodes: {sb.num_inodes}")
        print(f"  Root node info:")
        print(f"    Size: {sb.root['size']}")
        print(f"    Levels: {sb.root['levels']}")
        print(f"    Mode: {sb.root['mode']}")
        print(f"    First 4 blocks: {[b for b in sb.root['blocks'] if b != 0][:4]}")
        
        # Try to read some inodes
        print("\nTrying to read inodes:")
        for i in range(10):
            try:
                inode = self.parser.read_inode(i)
                if inode and inode.size > 0:
                    mode_str = self._get_file_type_string(inode.mode)
                    print(f"  Inode {i}: {mode_str}, size={inode.size}")
            except Exception as e:
                print(f"  Inode {i}: Error - {e}")
    
    def do_hexdump(self, args):
        """Hexdump a block: hexdump <block_number>"""
        if not args:
            print("Usage: hexdump <block_number>")
            return
            
        try:
            block_num = int(args)
            data = self.parser.read_block(block_num)
            
            print(f"Hexdump of block {block_num}:")
            for i in range(0, min(len(data), 512), 16):
                hex_str = ' '.join(f'{b:02x}' for b in data[i:i+16])
                ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data[i:i+16])
                print(f"{i:04x}: {hex_str:<48} {ascii_str}")
                
        except Exception as e:
            print(f"Error: {e}")
            self.logger.error(f"Error in hexdump: {e}", exc_info=True)
    
    def do_exit(self, arg):
        """Exit the shell"""
        return True
    
    def do_quit(self, arg):
        """Exit the shell"""
        return True
    
    def emptyline(self):
        """Do nothing on empty line"""
        pass
    
    def default(self, line):
        """Handle unknown commands"""
        print(f"Unknown command: {line}")
        print("Type 'help' for available commands")


def main():
    parser = argparse.ArgumentParser(description="QNX Forensic Analysis Tool")
    parser.add_argument("image", help="Path to disk image file")
    parser.add_argument("-p", "--partition", type=int, nargs='+', default=[13, 14],
                       help="Partition numbers to analyze (default: 13 14)")
    parser.add_argument("-l", "--list", action="store_true",
                       help="List all partitions and exit")
    parser.add_argument("-b", "--blocksize", type=int, default=4096,
                       help="Default block size (default: 4096)")
    parser.add_argument("-e", "--extract-all", metavar="DIR",
                       help="Extract all .txt and .log files to specified directory")
    parser.add_argument("-v", "--verbose", action="store_true",
                       help="Enable verbose logging")
    parser.add_argument("--log-file", default="qnx_forensic.log",
                       help="Log file path (default: qnx_forensic.log)")
    
    args = parser.parse_args()
    
    # Setup logging
    logger = setup_logging(args.log_file, args.verbose)
    logger.info("="*80)
    logger.info("QNX Forensic Analysis Tool Started")
    logger.info(f"Image file: {args.image}")
    logger.info(f"Target partitions: {args.partition}")
    logger.info("="*80)
    
    try:
        # Open disk image
        with open(args.image, 'rb') as f:
            print(f"Opening disk image: {args.image}")
            logger.info(f"Successfully opened disk image")
            
            # Get file size
            f.seek(0, 2)
            file_size = f.tell()
            f.seek(0)
            logger.info(f"Disk image size: {file_size} bytes ({file_size / (1024**3):.2f} GB)")
            
            # Parse MBR
            mbr_parser = MBRParser(f)
            partitions = mbr_parser.parse_mbr()
            
            print(f"\nFound {len(partitions)} partitions:")
            print(f"{'#':<4} {'Type':<6} {'Start LBA':<12} {'Size (MB)':<10} {'Description'}")
            print("-" * 60)
            
            for part in partitions:
                size_mb = (part.size_sectors * 512) / (1024 * 1024)
                desc = "QNX" if part.is_qnx else f"Type 0x{part.partition_type:02X}"
                if part.is_extended:
                    desc = "Extended"
                    
                print(f"{part.number:<4} 0x{part.partition_type:02X}   {part.start_lba:<12} {size_mb:<10.1f} {desc}")
            
            if args.list:
                return
                
            # Analyze requested partitions
            for part_num in args.partition:
                # Find partition by number
                partition = None
                for p in partitions:
                    if p.number == part_num:
                        partition = p
                        break
                        
                if not partition:
                    print(f"\nError: Partition {part_num} not found")
                    logger.error(f"Partition {part_num} not found")
                    continue
                    
                print(f"\n{'='*60}")
                print(f"Analyzing partition {part_num}")
                print(f"Type: 0x{partition.partition_type:02X}")
                print(f"Start: {partition.start_lba} sectors ({partition.start_lba * 512} bytes)")
                print(f"Size: {partition.size_sectors} sectors ({partition.size_sectors * 512} bytes)")
                
                logger.info(f"Analyzing partition {part_num}: type=0x{partition.partition_type:02X}, "
                          f"start={partition.start_lba}, size={partition.size_sectors}")
                
                # Try to parse as QNX6
                offset = partition.start_lba * 512
                qnx_parser = QNX6Parser(f, offset, args.blocksize)
                
                print("\nAttempting to parse QNX6 filesystem...")
                superblock = qnx_parser.parse_superblock()
                
                if superblock:
                    print("✓ QNX6 filesystem detected!")
                    print(f"  Block size: {superblock.blocksize} bytes")
                    print(f"  Total blocks: {superblock.num_blocks}")
                    print(f"  Total inodes: {superblock.num_inodes}")
                    print(f"  Volume ID: {superblock.volumeid.hex()}")
                    print(f"  Created: {datetime.datetime.fromtimestamp(superblock.ctime)}")
                    
                    # Extract all text/log files if requested
                    if args.extract_all:
                        print(f"\nExtracting all .txt and .log files to {args.extract_all}")
                        
                        # Create output directory
                        os.makedirs(args.extract_all, exist_ok=True)
                        
                        # Create partition subdirectory
                        part_dir = os.path.join(args.extract_all, f"partition_{part_num}")
                        os.makedirs(part_dir, exist_ok=True)
                        
                        # Scan and extract files
                        found_files = qnx_parser.scan_for_files(['.txt', '.log'], part_dir)
                        
                        print(f"\nExtraction complete:")
                        print(f"  Files found: {len(found_files)}")
                        print(f"  Files extracted: {sum(1 for f in found_files if f['extracted'])}")
                        print(f"  Extraction errors: {sum(1 for f in found_files if f['error'])}")
                        
                        # Save extraction report
                        report_path = os.path.join(part_dir, "extraction_report.json")
                        with open(report_path, 'w') as f:
                            json.dump(found_files, f, indent=2, default=str)
                        print(f"  Report saved to: {report_path}")
                        
                        logger.info(f"Extraction complete for partition {part_num}: "
                                  f"{len(found_files)} files found, "
                                  f"{sum(1 for f in found_files if f['extracted'])} extracted")
                    
                    # Start interactive shell if not just extracting
                    if not args.extract_all:
                        print(f"\nStarting interactive shell for partition {part_num}...")
                        shell = QNXShell(qnx_parser)
                        shell.cmdloop()
                else:
                    print("✗ Could not detect QNX6 filesystem")
                    print("  This partition may use a different filesystem or be encrypted")
                    logger.warning(f"Could not detect QNX6 filesystem on partition {part_num}")
                    
    except FileNotFoundError:
        print(f"Error: File not found: {args.image}")
        logger.error(f"File not found: {args.image}")
    except Exception as e:
        print(f"Error: {e}")
        logger.error(f"Fatal error: {e}", exc_info=True)
        import traceback
        traceback.print_exc()
    finally:
        logger.info("QNX Forensic Analysis Tool Finished")


if __name__ == "__main__":
    main()