"""
System Information Gathering Module for FENDER

This module contains functions for gathering system information,
hardware details, and environment data for forensic reporting.
"""

import os
import sys
import platform
import socket
import subprocess
import tempfile
import locale
import logging
from datetime import datetime
from pathlib import Path

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

# FENDER Version Information
FENDER_VERSION = "0.2.2"
FENDER_BUILD_DATE = "June 17 2025"

logger = logging.getLogger(__name__)


def get_system_info(input_file=None, output_file=None, execution_mode="GUI", decoder_registry=None):
    """Gather system and configuration information for reports"""
    logger.info("Gathering system information for report generation")
    logger.debug(f"Input file: {input_file}, Output file: {output_file}, Mode: {execution_mode}")
    
    # Get directory paths for permission checking
    output_dir = os.path.dirname(output_file) if output_file else os.getcwd()
    logger.debug(f"Output directory: {output_dir}")
    
    system_info = {
        "fender_version": FENDER_VERSION,
        "fender_build_date": FENDER_BUILD_DATE,
        "report_generated_on": datetime.now().isoformat(),
        "python_interpreter_version": sys.version,
        "python_interpreter_path": sys.executable,
        "operating_system": platform.system(),
        "os_release": platform.release(),
        "os_version": platform.version(),
        "system_architecture": platform.machine(),
        "processor_type": platform.processor(),
        "computer_hostname": platform.node(),
        "system_ram_available_total": get_system_ram(),
        "output_disk_space_available": get_disk_space(output_dir),
        "system_locale": get_system_locale(),
        "network_status": check_network_status(),
        "execution_mode": execution_mode,
    }
    
    logger.debug(f"Basic system info collected: OS={system_info['operating_system']}, "
                f"Architecture={system_info['system_architecture']}")
    
    # Add file permission checks if files are provided
    if input_file:
        logger.debug(f"Checking read permissions for: {input_file}")
        system_info["read_permissions_granted"] = check_read_permissions(input_file)
    
    if output_file:
        logger.debug(f"Checking write permissions for: {output_dir}")
        system_info["write_permissions_granted"] = check_write_permissions(output_dir)
    
    # Add CLI arguments if running in CLI mode
    if execution_mode == "CLI":
        cli_args = " ".join(sys.argv)
        logger.debug(f"CLI arguments: {cli_args}")
        system_info["cli_arguments"] = cli_args
    
    # Add decoder information if registry is provided
    if decoder_registry:
        from file_operations import get_file_hash_safe
        logger.debug("Collecting decoder information from registry")
        system_info["available_decoders"] = list(decoder_registry.get_decoder_names())
        system_info["decoder_details"] = get_decoder_info(decoder_registry)
        system_info["decoder_hashes"] = get_decoder_hashes(decoder_registry)
        logger.info(f"Found {len(system_info['available_decoders'])} decoders")
    
    # Add file hashes for main components
    try:
        main_script_path = os.path.abspath(sys.argv[0])
        logger.debug(f"Calculating hash for main script: {main_script_path}")
        from file_operations import get_file_hash_safe
        system_info["main_script_hash"] = get_file_hash_safe(main_script_path)
        system_info["main_script_path"] = main_script_path
    except Exception as e:
        logger.error(f"Error getting main script hash: {e}")
        system_info["main_script_hash"] = "Error getting main script hash"
    
    try:
        base_decoder_path = os.path.join(os.path.dirname(sys.argv[0]), "base_decoder.py")
        if os.path.exists(base_decoder_path):
            logger.debug(f"Calculating hash for base decoder: {base_decoder_path}")
            from file_operations import get_file_hash_safe
            system_info["base_decoder_hash"] = get_file_hash_safe(base_decoder_path)
            system_info["base_decoder_path"] = base_decoder_path
        else:
            logger.warning(f"base_decoder.py not found at: {base_decoder_path}")
            system_info["base_decoder_hash"] = "base_decoder.py not found"
    except Exception as e:
        logger.error(f"Error getting base decoder hash: {e}")
        system_info["base_decoder_hash"] = "Error getting base decoder hash"
    
    logger.info("System information gathering completed successfully")
    return system_info


def get_decoder_info(registry):
    """Get detailed information about all loaded decoders"""
    logger.info("Collecting detailed decoder information")
    decoder_info = {}
    
    for name in registry.get_decoder_names():
        logger.debug(f"Getting info for decoder: {name}")
        try:
            decoder_class = registry.get_decoder(name)
            decoder_instance = decoder_class()
            
            decoder_info[name] = {
                "class_name": decoder_class.__name__,
                "supported_extensions": decoder_instance.get_supported_extensions(),
                "description": getattr(decoder_instance, 'description', 'No description available'),
                "version": getattr(decoder_instance, 'version', 'Unknown')
            }
            logger.debug(f"Collected info for {name}: {decoder_info[name]}")
            
        except Exception as e:
            logger.error(f"Error getting info for decoder {name}: {e}")
            decoder_info[name] = {"error": f"Error getting decoder info: {str(e)}"}
    
    logger.info(f"Completed decoder info collection for {len(decoder_info)} decoders")
    return decoder_info


def get_decoder_hashes(registry):
    """Get SHA256 hashes of all loaded decoder files for integrity verification"""
    logger.info("Calculating hashes for decoder integrity verification")
    decoder_hashes = {}
    
    import inspect
    
    for name in registry.get_decoder_names():
        logger.debug(f"Processing decoder: {name}")
        try:
            decoder_class = registry.get_decoder(name)
            
            # Get the module file path
            module = inspect.getmodule(decoder_class)
            if module and hasattr(module, '__file__') and module.__file__:
                file_path = os.path.abspath(module.__file__)
                logger.debug(f"Decoder {name} located at: {file_path}")
                
                # Calculate hash
                from file_operations import get_file_hash_safe
                decoder_hashes[name] = {
                    "file_path": file_path,
                    "sha256_hash": get_file_hash_safe(file_path),
                    "file_size": os.path.getsize(file_path) if os.path.exists(file_path) else 0,
                    "last_modified": datetime.fromtimestamp(
                        os.path.getmtime(file_path)
                    ).isoformat() if os.path.exists(file_path) else "Unknown"
                }
                logger.debug(f"Hash for {name}: {decoder_hashes[name]['sha256_hash'][:16]}...")
            else:
                logger.warning(f"Could not determine file path for decoder: {name}")
                decoder_hashes[name] = {
                    "error": "Could not determine decoder file path"
                }
                
        except Exception as e:
            logger.error(f"Error getting decoder hash for {name}: {e}", exc_info=True)
            decoder_hashes[name] = {
                "error": f"Error getting decoder hash: {str(e)}"
            }
    
    logger.info(f"Completed hash calculation for {len(decoder_hashes)} decoders")
    return decoder_hashes


def get_system_ram():
    """Get total system RAM using psutil if available, fallback to platform-specific methods"""
    logger.debug("Getting system RAM information")
    
    if PSUTIL_AVAILABLE:
        try:
            memory_info = psutil.virtual_memory()
            total_ram_gb = memory_info.total / (1024**3)
            logger.debug(f"System RAM (psutil): {total_ram_gb:.2f} GB")
            return f"{total_ram_gb:.2f} GB"
        except Exception as e:
            logger.warning(f"psutil RAM detection failed: {e}")
            return get_system_ram_fallback()
    else:
        logger.debug("psutil not available, using fallback method")
        return get_system_ram_fallback()


def get_system_ram_fallback():
    """Fallback method to get system RAM without psutil"""
    logger.debug("Using fallback method for RAM detection")
    
    try:
        if platform.system() == "Windows":
            # Windows specific method
            import ctypes
            kernel32 = ctypes.windll.kernel32
            c_ulong = ctypes.c_ulong
            
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ('dwLength', ctypes.c_ulong),
                    ('dwMemoryLoad', ctypes.c_ulong),
                    ('ullTotalPhys', ctypes.c_ulonglong),
                    ('ullAvailPhys', ctypes.c_ulonglong),
                    ('ullTotalPageFile', ctypes.c_ulonglong),
                    ('ullAvailPageFile', ctypes.c_ulonglong),
                    ('ullTotalVirtual', ctypes.c_ulonglong),
                    ('ullAvailVirtual', ctypes.c_ulonglong),
                    ('ullAvailExtendedVirtual', ctypes.c_ulonglong),
                ]
            
            memoryStatusEx = MEMORYSTATUSEX()
            memoryStatusEx.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            kernel32.GlobalMemoryStatusEx(ctypes.byref(memoryStatusEx))
            
            total_ram_gb = memoryStatusEx.ullTotalPhys / (1024**3)
            logger.debug(f"System RAM (Windows API): {total_ram_gb:.2f} GB")
            return f"{total_ram_gb:.2f} GB"
            
        elif platform.system() == "Linux":
            # Linux specific method
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    if line.startswith('MemTotal:'):
                        mem_kb = int(line.split()[1])
                        total_ram_gb = mem_kb / (1024**2)
                        logger.debug(f"System RAM (Linux): {total_ram_gb:.2f} GB")
                        return f"{total_ram_gb:.2f} GB"
        
        logger.warning("Could not determine system RAM")
        return "Unable to determine"
    
    except Exception as e:
        logger.error(f"Error getting system RAM: {e}")
        return "Error getting RAM info"


def get_disk_space(path):
    """Get available disk space for a given path"""
    logger.debug(f"Getting disk space for: {path}")
    
    try:
        if PSUTIL_AVAILABLE:
            usage = psutil.disk_usage(path)
            free_gb = usage.free / (1024**3)
            total_gb = usage.total / (1024**3)
            logger.debug(f"Disk space (psutil): {free_gb:.2f} GB free of {total_gb:.2f} GB total")
            return f"{free_gb:.2f} GB free of {total_gb:.2f} GB total"
        else:
            # Fallback using os.statvfs (Unix) or ctypes (Windows)
            if platform.system() == "Windows":
                import ctypes
                free_bytes = ctypes.c_ulonglong(0)
                total_bytes = ctypes.c_ulonglong(0)
                ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                    ctypes.c_wchar_p(path),
                    ctypes.pointer(free_bytes),
                    ctypes.pointer(total_bytes),
                    None
                )
                free_gb = free_bytes.value / (1024**3)
                total_gb = total_bytes.value / (1024**3)
            else:
                statvfs = os.statvfs(path)
                free_gb = (statvfs.f_frsize * statvfs.f_bavail) / (1024**3)
                total_gb = (statvfs.f_frsize * statvfs.f_blocks) / (1024**3)
            
            logger.debug(f"Disk space (fallback): {free_gb:.2f} GB free of {total_gb:.2f} GB total")
            return f"{free_gb:.2f} GB free of {total_gb:.2f} GB total"
    
    except Exception as e:
        logger.error(f"Error getting disk space: {e}")
        return "Unable to determine disk space"


def get_system_locale():
    """Get system locale information"""
    logger.debug("Getting system locale information")
    
    try:
        # Get the current locale
        current_locale = locale.getlocale()
        default_locale = locale.getdefaultlocale()
        
        locale_info = {
            "current_locale": current_locale,
            "default_locale": default_locale,
            "preferred_encoding": locale.getpreferredencoding()
        }
        
        logger.debug(f"Locale info: {locale_info}")
        return str(locale_info)
    
    except Exception as e:
        logger.error(f"Error getting locale info: {e}")
        return "Unable to determine locale"


def check_network_status():
    """Check basic network connectivity"""
    logger.debug("Checking network connectivity")
    
    try:
        # Try to connect to a reliable public DNS server
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        logger.debug("Network connectivity: Available")
        return "Available"
    except OSError:
        logger.debug("Network connectivity: Not available")
        return "Not available"


def check_read_permissions(file_path):
    """Check if file is readable"""
    logger.debug(f"Checking read permissions for: {file_path}")
    
    try:
        if os.path.exists(file_path):
            if os.access(file_path, os.R_OK):
                logger.debug("Read permissions: Granted")
                return "Granted"
            else:
                logger.warning("Read permissions: Denied")
                return "Denied"
        else:
            logger.warning("File does not exist")
            return "File does not exist"
    except Exception as e:
        logger.error(f"Error checking read permissions: {e}")
        return f"Error: {str(e)}"


def check_write_permissions(dir_path):
    """Check if directory is writable"""
    logger.debug(f"Checking write permissions for: {dir_path}")
    
    try:
        if os.path.exists(dir_path):
            if os.access(dir_path, os.W_OK):
                logger.debug("Write permissions: Granted")
                return "Granted"
            else:
                logger.warning("Write permissions: Denied")
                return "Denied"
        else:
            logger.warning("Directory does not exist")
            return "Directory does not exist"
    except Exception as e:
        logger.error(f"Error checking write permissions: {e}")
        return f"Error: {str(e)}"


def get_extraction_info(decoder_name: str, input_file: str, output_file: str, entry_count: int, processing_time: float = None):
    """Generate extraction information for reports"""
    logger.info("Generating extraction information for report")
    logger.debug(f"Decoder: {decoder_name}, Input: {input_file}, Output: {output_file}, Entries: {entry_count}")
    
    try:
        # Input file information
        input_path = Path(input_file)
        input_size_bytes = input_path.stat().st_size if input_path.exists() else 0
        input_size_mb = input_size_bytes / (1024 * 1024)
        
        # Calculate input file hash
        from file_operations import get_file_hash_safe
        input_hash = get_file_hash_safe(input_file)
        
        # Output file information
        output_path = Path(output_file)
        
        extraction_info = {
            "input_file": {
                "path": str(input_path.absolute()),
                "filename": input_path.name,
                "size_bytes": input_size_bytes,
                "size_mb": round(input_size_mb, 2),
                "sha256_hash": input_hash,
                "last_modified": datetime.fromtimestamp(input_path.stat().st_mtime).isoformat() if input_path.exists() else "Unknown"
            },
            "output_file": {
                "path": str(output_path.absolute()),
                "filename": output_path.name,
                "format": output_path.suffix.lower()
            },
            "extraction_details": {
                "decoder_used": decoder_name,
                "entries_extracted": entry_count,
                "extraction_timestamp": datetime.now().isoformat(),
                "processing_time_seconds": processing_time if processing_time else 0
            }
        }
        
        logger.info("Extraction information generated successfully")
        return extraction_info
        
    except Exception as e:
        logger.error(f"Error generating extraction info: {e}", exc_info=True)
        return {
            "error": f"Error generating extraction info: {str(e)}"
        }
