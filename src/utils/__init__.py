"""
File Operations Module for FENDER

This module contains functions for secure file handling, validation,
and export operations for various formats.
"""

import os
import sys
import json
import csv
import hashlib
import shutil
import tempfile
import stat
import platform
import secrets
import logging
from pathlib import Path
from datetime import datetime
from typing import List
from openpyxl import Workbook

logger = logging.getLogger(__name__)

# FENDER Version Information
FENDER_VERSION = "0.2.2"

# Maximum file size (in GB) the program will load
sizeingb = 200


def secure_temp_file(suffix="", prefix="fender_", dir=None):
    """Create a secure temporary file with restricted permissions"""
    logger.debug(f"Creating secure temporary file with prefix={prefix}, suffix={suffix}")
    
    # Create temporary file with secure permissions
    fd, path = tempfile.mkstemp(suffix=suffix, prefix=prefix, dir=dir)
    logger.debug(f"Created temporary file: {path}")
    
    # Set restrictive permissions (owner read/write only)
    if platform.system() != "Windows":
        logger.debug(f"Setting restrictive permissions on temporary file")
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    
    logger.info(f"Secure temporary file created: {path}")
    return fd, path


def secure_temp_dir(prefix="fender_", dir=None):
    """Create a secure temporary directory with restricted permissions"""
    logger.debug(f"Creating secure temporary directory with prefix={prefix}")
    
    path = tempfile.mkdtemp(prefix=prefix, dir=dir)
    logger.debug(f"Created temporary directory: {path}")
    
    # Set restrictive permissions (owner only)
    if platform.system() != "Windows":
        logger.debug(f"Setting restrictive permissions on temporary directory")
        os.chmod(path, stat.S_IRWXU)
    
    logger.info(f"Secure temporary directory created: {path}")
    return path


def secure_file_copy(src, dst, chunk_size=65536):
    """Securely copy file with verification"""
    logger.info(f"Starting secure file copy from {src} to {dst}")
    logger.debug(f"Using chunk size: {chunk_size} bytes")
    
    src_hash = hashlib.sha256()
    dst_hash = hashlib.sha256()
    bytes_copied = 0
    
    try:
        with open(src, 'rb') as src_file, open(dst, 'wb') as dst_file:
            while True:
                chunk = src_file.read(chunk_size)
                if not chunk:
                    break
                src_hash.update(chunk)
                dst_file.write(chunk)
                bytes_copied += len(chunk)
                
                if bytes_copied % (chunk_size * 100) == 0:  # Log progress every 100 chunks
                    logger.debug(f"Copied {bytes_copied} bytes...")
        
        logger.debug(f"Total bytes copied: {bytes_copied}")
        
        # Verify copy integrity
        logger.debug("Verifying file copy integrity")
        with open(dst, 'rb') as dst_file:
            while True:
                chunk = dst_file.read(chunk_size)
                if not chunk:
                    break
                dst_hash.update(chunk)
        
        src_hex = src_hash.hexdigest()
        dst_hex = dst_hash.hexdigest()
        
        if src_hex != dst_hex:
            logger.error(f"File copy verification failed! Source hash: {src_hex}, Destination hash: {dst_hex}")
            raise ValueError("File copy verification failed - checksums don't match")
        
        logger.info(f"File copy completed successfully. Hash: {dst_hex}")
        return dst_hex
        
    except Exception as e:
        logger.error(f"Error during secure file copy: {e}", exc_info=True)
        raise


def sanitize_filename(filename):
    """Sanitize filename to prevent path traversal attacks"""
    logger.debug(f"Sanitizing filename: {filename}")
    
    # Remove directory separators and other potentially dangerous characters
    dangerous_chars = '<>:"/\\|?*'
    for char in dangerous_chars:
        filename = filename.replace(char, '_')
    
    # Remove any path components
    filename = os.path.basename(filename)
    
    # Limit length
    if len(filename) > 200:
        name, ext = os.path.splitext(filename)
        filename = name[:200-len(ext)] + ext
        logger.debug(f"Filename truncated to 200 characters")
    
    logger.debug(f"Sanitized filename: {filename}")
    return filename


def validate_file_path(file_path, allowed_extensions=None):
    """Validate file path for security"""
    logger.info(f"Validating file path: {file_path}")
    
    try:
        # Resolve to absolute path to prevent traversal
        abs_path = os.path.abspath(file_path)
        logger.debug(f"Resolved to absolute path: {abs_path}")
        
        # Check if file exists
        if not os.path.exists(abs_path):
            logger.warning(f"File does not exist: {abs_path}")
            return False, "File does not exist"
        
        # Check if it's actually a file
        if not os.path.isfile(abs_path):
            logger.warning(f"Path is not a file: {abs_path}")
            return False, "Path is not a file"
        
        # Check file extension if provided
        if allowed_extensions:
            file_ext = os.path.splitext(abs_path)[1].lower()
            logger.debug(f"File extension: {file_ext}, Allowed: {allowed_extensions}")
            if file_ext not in [ext.lower() for ext in allowed_extensions]:
                logger.warning(f"File extension {file_ext} not in allowed list")
                return False, f"File extension not allowed. Allowed: {allowed_extensions}"
        
        # Check file size (prevent extremely large files)
        file_size = os.path.getsize(abs_path)
        max_size = sizeingb * 1024 * 1024 * 1024
        logger.debug(f"File size: {file_size} bytes, Max allowed: {max_size} bytes")
        
        if file_size > max_size:
            logger.warning(f"File too large: {file_size} bytes")
            return False, f"File too large. Maximum size: {max_size/1024/1024/1024:.1f}GB"
        
        logger.info(f"File validation successful: {abs_path}")
        return True, abs_path
        
    except Exception as e:
        logger.error(f"Path validation error: {e}", exc_info=True)
        return False, f"Path validation error: {str(e)}"


def validate_folder_path(folder_path):
    """Validate folder path for security"""
    logger.info(f"Validating folder path: {folder_path}")
    
    try:
        # Resolve to absolute path to prevent traversal
        abs_path = os.path.abspath(folder_path)
        logger.debug(f"Resolved to absolute path: {abs_path}")
        
        # Check if folder exists
        if not os.path.exists(abs_path):
            logger.warning(f"Folder does not exist: {abs_path}")
            return False, "Folder does not exist"
        
        # Check if it's actually a directory
        if not os.path.isdir(abs_path):
            logger.warning(f"Path is not a folder: {abs_path}")
            return False, "Path is not a folder"
        
        # Check if folder is accessible
        if not os.access(abs_path, os.R_OK):
            logger.warning(f"Folder is not readable: {abs_path}")
            return False, "Folder is not readable"
        
        logger.info(f"Folder validation successful: {abs_path}")
        return True, abs_path
        
    except Exception as e:
        logger.error(f"Folder validation error: {e}", exc_info=True)
        return False, f"Folder validation error: {str(e)}"


def get_file_hash(file_path: str) -> str:
    """Calculate SHA256 hash of a file"""
    logger.debug(f"Calculating SHA256 hash for: {file_path}")
    
    hash_sha256 = hashlib.sha256()
    chunk_size = 65536  # 64KB chunks
    
    try:
        with open(file_path, "rb") as f:
            while chunk := f.read(chunk_size):
                hash_sha256.update(chunk)
        
        file_hash = hash_sha256.hexdigest()
        logger.debug(f"Hash calculated: {file_hash[:16]}...")
        return file_hash
        
    except Exception as e:
        logger.error(f"Error calculating file hash: {e}")
        raise


def get_file_hash_safe(file_path):
    """Safely get file hash with error handling"""
    logger.debug(f"Safely calculating hash for: {file_path}")
    
    try:
        return get_file_hash(file_path)
    except Exception as e:
        logger.error(f"Error getting file hash for {file_path}: {e}")
        return f"Error calculating hash: {str(e)}"


def write_geojson(entries: List, output_path: str, decoder_name: str = "Unknown"):
    """Write GPS entries to GeoJSON format"""
    logger.info(f"Writing {len(entries)} entries to GeoJSON file: {output_path}")
    logger.debug(f"Using decoder: {decoder_name}")
    
    features = []
    skipped_count = 0
    
    for i, entry in enumerate(entries):
        # Skip invalid coordinates
        if (entry.latitude == 0 and entry.longitude == 0) or \
           not (-90 <= entry.latitude <= 90) or \
           not (-180 <= entry.longitude <= 180):
            logger.debug(f"Skipping invalid coordinates at index {i}: lat={entry.latitude}, lon={entry.longitude}")
            skipped_count += 1
            continue
        
        # Create feature
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [entry.longitude, entry.latitude]  # GeoJSON uses [lon, lat]
            },
            "properties": {
                "id": i + 1,
                "timestamp": entry.timestamp,
                "latitude": entry.latitude,
                "longitude": entry.longitude,
            }
        }
        
        # Add extra data if available
        if entry.extra_data:
            feature["properties"].update(entry.extra_data)
            logger.debug(f"Added extra data to feature {i+1}: {list(entry.extra_data.keys())}")
        
        features.append(feature)
    
    logger.info(f"Created {len(features)} valid features, skipped {skipped_count} invalid entries")
    
    # Create GeoJSON structure
    geojson = {
        "type": "FeatureCollection",
        "metadata": {
            "decoder": decoder_name,
            "extraction_timestamp": datetime.now().isoformat(),
            "total_features": len(features),
            "coordinate_system": "WGS84",
            "creator": f"FENDER v{FENDER_VERSION}"
        },
        "features": features
    }
    
    # Write to file
    try:
        logger.debug(f"Writing GeoJSON to file")
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(geojson, f, indent=2, ensure_ascii=False)
        logger.info(f"GeoJSON file written successfully: {output_path}")
    except Exception as e:
        logger.error(f"Error writing GeoJSON file: {e}", exc_info=True)
        raise


def write_kml(entries: List, output_path: str, decoder_name: str = "Unknown"):
    """Write GPS entries to KML format for Google Earth"""
    logger.info(f"Writing {len(entries)} entries to KML file: {output_path}")
    logger.debug(f"Using decoder: {decoder_name}")
    
    # KML header with XML declaration
    kml_content = ['<?xml version="1.0" encoding="UTF-8"?>']
    kml_content.append('<kml xmlns="http://www.opengis.net/kml/2.2">')
    kml_content.append('  <Document>')
    
    # Document metadata
    kml_content.append(f'    <name>FENDER GPS Data - {decoder_name}</name>')
    kml_content.append(f'    <description>Extracted by FENDER v{FENDER_VERSION} on {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</description>')
    
    # Define styles for placemarks
    kml_content.append('    <Style id="normalPin">')
    kml_content.append('      <IconStyle>')
    kml_content.append('        <color>ff0000ff</color>')  # Red color in KML format (aabbggrr)
    kml_content.append('        <scale>0.8</scale>')
    kml_content.append('        <Icon>')
    kml_content.append('          <href>http://maps.google.com/mapfiles/kml/pushpin/red-pushpin.png</href>')
    kml_content.append('        </Icon>')
    kml_content.append('      </IconStyle>')
    kml_content.append('      <LabelStyle>')
    kml_content.append('        <scale>0.7</scale>')
    kml_content.append('      </LabelStyle>')
    kml_content.append('    </Style>')
    
    # Style for path/track
    kml_content.append('    <Style id="trackStyle">')
    kml_content.append('      <LineStyle>')
    kml_content.append('        <color>ff0000ff</color>')  # Red color
    kml_content.append('        <width>2</width>')
    kml_content.append('      </LineStyle>')
    kml_content.append('    </Style>')
    
    # Add placemarks for each GPS entry
    valid_entries = []
    skipped_count = 0
    
    for i, entry in enumerate(entries):
        # Skip invalid coordinates
        if (entry.latitude == 0 and entry.longitude == 0) or \
           not (-90 <= entry.latitude <= 90) or \
           not (-180 <= entry.longitude <= 180):
            logger.debug(f"Skipping invalid coordinates at index {i}: lat={entry.latitude}, lon={entry.longitude}")
            skipped_count += 1
            continue
        
        valid_entries.append(entry)
        
        # Create placemark
        kml_content.append('    <Placemark>')
        kml_content.append(f'      <name>Point {i + 1}</name>')
        
        # Description with all available data
        description_parts = [
            f"Timestamp: {entry.timestamp}",
            f"Latitude: {entry.latitude}",
            f"Longitude: {entry.longitude}"
        ]
        
        # Add extra data if available
        if entry.extra_data:
            for key, value in entry.extra_data.items():
                description_parts.append(f"{key}: {value}")
        
        description = "\\n".join(description_parts)
        kml_content.append(f'      <description>{description}</description>')
        kml_content.append('      <styleUrl>#normalPin</styleUrl>')
        kml_content.append('      <Point>')
        kml_content.append(f'        <coordinates>{entry.longitude},{entry.latitude},0</coordinates>')
        kml_content.append('      </Point>')
        kml_content.append('    </Placemark>')
    
    logger.info(f"Created {len(valid_entries)} valid placemarks, skipped {skipped_count} invalid entries")
    
    # Optionally add a path connecting all points
    if len(valid_entries) > 1:
        logger.debug("Adding path connecting all GPS points")
        kml_content.append('    <Placemark>')
        kml_content.append('      <name>GPS Track</name>')
        kml_content.append('      <description>Connected GPS track showing vehicle movement</description>')
        kml_content.append('      <styleUrl>#trackStyle</styleUrl>')
        kml_content.append('      <LineString>')
        kml_content.append('        <tessellate>1</tessellate>')
        kml_content.append('        <coordinates>')
        
        # Add all coordinates to the path
        coordinate_strings = []
        for entry in valid_entries:
            coordinate_strings.append(f'{entry.longitude},{entry.latitude},0')
        
        kml_content.append('          ' + ' '.join(coordinate_strings))
        kml_content.append('        </coordinates>')
        kml_content.append('      </LineString>')
        kml_content.append('    </Placemark>')
    
    # Close KML structure
    kml_content.append('  </Document>')
    kml_content.append('</kml>')
    
    # Write to file
    try:
        logger.debug(f"Writing KML to file")
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\\n'.join(kml_content))
        logger.info(f"KML file written successfully: {output_path}")
    except Exception as e:
        logger.error(f"Error writing KML file: {e}", exc_info=True)
        raise


def filter_duplicate_entries(entries, precision_decimals, logger):
    """Filter duplicate GPS entries based on timestamp and coordinates"""
    logger.info(f"Filtering duplicate entries with precision: {precision_decimals} decimal places")
    
    if not entries:
        logger.warning("No entries to filter")
        return entries
    
    seen = set()
    filtered_entries = []
    duplicate_count = 0
    
    for entry in entries:
        # Round coordinates to specified precision
        rounded_lat = round(entry.latitude, precision_decimals)
        rounded_lon = round(entry.longitude, precision_decimals)
        
        # Create unique key from timestamp and rounded coordinates
        key = (entry.timestamp, rounded_lat, rounded_lon)
        
        if key not in seen:
            seen.add(key)
            filtered_entries.append(entry)
        else:
            duplicate_count += 1
    
    logger.info(f"Filtering complete: {len(filtered_entries)} unique entries, {duplicate_count} duplicates removed")
    return filtered_entries


def get_resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
        logger.debug(f"Using PyInstaller base path: {base_path}")
    except AttributeError:
        base_path = os.path.abspath(".")
        logger.debug(f"Using development base path: {base_path}")
    
    resource_path = os.path.join(base_path, relative_path)
    logger.debug(f"Resource path resolved: {resource_path}")
    return resource_path


def write_excel_report(entries: List, output_path: str, decoder_name: str, system_info: dict, extraction_info: dict, decoder_instance, examiner_name: str = None, case_number: str = None):
    """Write comprehensive Excel report with GPS data and metadata"""
    logger.info(f"Writing Excel report to: {output_path}")
    
    wb = Workbook()
    
    # Main GPS Data worksheet
    ws_data = wb.active
    ws_data.title = "GPS Data"
    
    headers = decoder_instance.get_xlsx_headers()
    ws_data.append(headers)
    
    for entry in entries:
        row = decoder_instance.format_entry_for_xlsx(entry)
        ws_data.append(row)
    
    # Create Extraction Details worksheet
    ws_details = wb.create_sheet("Extraction Details")
      # Write extraction details
    ws_details.append(["FENDER Extraction Report"])
    ws_details.append([])
    
    # Case Information (if provided)
    if examiner_name or case_number:
        ws_details.append(["Case Information"])
        ws_details.append(["Field", "Value"])
        if examiner_name:
            ws_details.append(["Examiner Name", examiner_name])
        if case_number:
            ws_details.append(["Case Number", case_number])
        ws_details.append([])
    
    # System Information
    ws_details.append(["System Information"])
    ws_details.append(["Field", "Value"])
    for key, value in system_info.items():
        if key != "decoder_hashes":
            ws_details.append([key.replace("_", " ").title(), str(value)])
    
    ws_details.append([])
    
    # Decoder Hashes
    if "decoder_hashes" in system_info:
        ws_details.append(["Decoder Integrity Verification"])
        ws_details.append(["Decoder", "File Path", "SHA256 Hash", "File Size", "Last Modified"])
        for decoder_name_hash, hash_info in system_info["decoder_hashes"].items():
            if "error" in hash_info:
                ws_details.append([decoder_name_hash, "Error", hash_info["error"], "", ""])
            else:
                ws_details.append([
                    decoder_name_hash,
                    hash_info["file_path"],
                    hash_info["sha256_hash"],
                    hash_info["file_size"],
                    hash_info["last_modified"]
                ])
    
    ws_details.append([])
    
    # Extraction Information
    ws_details.append(["Extraction Information"])
    ws_details.append(["Field", "Value"])
    
    # Input file details
    ws_details.append(["Input File Path", extraction_info["input_file"]["path"]])
    ws_details.append(["Input File Name", extraction_info["input_file"]["filename"]])
    ws_details.append(["Input File Size (MB)", extraction_info["input_file"]["size_mb"]])
    ws_details.append(["Input File SHA256", extraction_info["input_file"]["sha256_hash"]])
    
    # Output file details
    ws_details.append(["Output File Path", extraction_info["output_file"]["path"]])
    ws_details.append(["Output File Name", extraction_info["output_file"]["filename"]])
    
    # Extraction details
    ws_details.append(["Decoder Used", extraction_info["extraction_details"]["decoder_used"]])
    ws_details.append(["Entries Extracted", extraction_info["extraction_details"]["entries_extracted"]])
    ws_details.append(["Processing Time (seconds)", extraction_info["extraction_details"]["processing_time_seconds"]])
    
    # Format the details worksheet
    ws_details.column_dimensions['A'].width = 25
    ws_details.column_dimensions['B'].width = 50
    ws_details.column_dimensions['C'].width = 70
    
    wb.save(output_path)
    logger.info(f"Excel report written successfully: {output_path}")


def write_csv_report(entries: List, output_path: str, decoder_name: str, system_info: dict, extraction_info: dict, decoder_instance, examiner_name: str = None, case_number: str = None):
    """Write comprehensive CSV report with GPS data and metadata"""
    logger.info(f"Writing CSV report to: {output_path}")
    
    headers = decoder_instance.get_xlsx_headers()
    
    with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        
        # Write headers
        writer.writerow(headers)
        
        # Write entries
        for entry in entries:
            row = decoder_instance.format_entry_for_xlsx(entry)
            writer.writerow(row)
        
        # Add separator
        for _ in range(3):
            writer.writerow([])
          # Write extraction details
        writer.writerow(["FENDER Extraction Report"])
        writer.writerow([])
        
        # Case Information (if provided)
        if examiner_name or case_number:
            writer.writerow(["Case Information"])
            writer.writerow(["Field", "Value"])
            if examiner_name:
                writer.writerow(["Examiner Name", examiner_name])
            if case_number:
                writer.writerow(["Case Number", case_number])
            writer.writerow([])
        
        # System Information
        writer.writerow(["System Information"])
        writer.writerow(["Field", "Value"])
        for key, value in system_info.items():
            if key != "decoder_hashes":
                writer.writerow([key.replace("_", " ").title(), str(value)])
        
        writer.writerow([])
        
        # Decoder Hashes
        if "decoder_hashes" in system_info:
            writer.writerow(["Decoder Integrity Verification"])
            writer.writerow(["Decoder", "File Path", "SHA256 Hash", "File Size", "Last Modified"])
            for decoder_name_hash, hash_info in system_info["decoder_hashes"].items():
                if "error" in hash_info:
                    writer.writerow([decoder_name_hash, "Error", hash_info["error"], "", ""])
                else:
                    writer.writerow([
                        decoder_name_hash,
                        hash_info["file_path"],
                        hash_info["sha256_hash"],
                        hash_info["file_size"],
                        hash_info["last_modified"]
                    ])
        
        writer.writerow([])
        
        # Extraction Information
        writer.writerow(["Extraction Information"])
        writer.writerow(["Field", "Value"])
        
        # Input file details
        writer.writerow(["Input File Path", extraction_info["input_file"]["path"]])
        writer.writerow(["Input File Name", extraction_info["input_file"]["filename"]])
        writer.writerow(["Input File Size (MB)", extraction_info["input_file"]["size_mb"]])
        writer.writerow(["Input File SHA256", extraction_info["input_file"]["sha256_hash"]])
        
        # Output file details
        writer.writerow(["Output File Path", extraction_info["output_file"]["path"]])
        writer.writerow(["Output File Name", extraction_info["output_file"]["filename"]])
        
        # Extraction details
        writer.writerow(["Decoder Used", extraction_info["extraction_details"]["decoder_used"]])
        writer.writerow(["Entries Extracted", extraction_info["extraction_details"]["entries_extracted"]])
        writer.writerow(["Processing Time (seconds)", extraction_info["extraction_details"]["processing_time_seconds"]])

    logger.info(f"CSV report written successfully: {output_path}")


def write_json_report(entries: List, output_path: str, decoder_name: str, system_info: dict, extraction_info: dict, decoder_instance, examiner_name: str = None, case_number: str = None):
    """Write comprehensive JSON report with GPS data and metadata"""
    logger.info(f"Writing JSON report to: {output_path}")
    
    json_data = {
        "metadata": {
            "decoder": decoder_name,
            "extraction_timestamp": datetime.now().isoformat(),
            "total_entries": len(entries)
        },
        "case_information": {},
        "system_information": system_info,
        "extraction_information": extraction_info,
        "gps_entries": []
    }
    
    # Add case information if provided
    if examiner_name:
        json_data["case_information"]["examiner_name"] = examiner_name
    if case_number:
        json_data["case_information"]["case_number"] = case_number
    
    headers = decoder_instance.get_xlsx_headers()
    
    for entry in entries:
        row = decoder_instance.format_entry_for_xlsx(entry)
        entry_dict = {}
        
        for i, header in enumerate(headers):
            if i < len(row):
                entry_dict[header] = row[i]
        
        entry_dict.update({
            "latitude": entry.latitude,
            "longitude": entry.longitude,
            "timestamp": entry.timestamp,
            "extra_data": entry.extra_data
        })
        
        json_data["gps_entries"].append(entry_dict)
    
    with open(output_path, 'w', encoding='utf-8') as jsonfile:
        json.dump(json_data, jsonfile, indent=2, ensure_ascii=False, default=str)
    
    logger.info(f"JSON report written successfully: {output_path}")


def write_geojson_report(entries: List, output_path: str, decoder_name: str, system_info: dict, extraction_info: dict, examiner_name: str = None, case_number: str = None):
    """Write comprehensive GeoJSON report with GPS data and metadata"""
    logger.info(f"Writing GeoJSON report to: {output_path}")
    
    features = []
    skipped_count = 0
    
    for i, entry in enumerate(entries):
        # Skip invalid coordinates
        if (entry.latitude == 0 and entry.longitude == 0) or \
           not (-90 <= entry.latitude <= 90) or \
           not (-180 <= entry.longitude <= 180):
            skipped_count += 1
            continue
        
        # Create feature
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [entry.longitude, entry.latitude]
            },
            "properties": {
                "id": i + 1,
                "timestamp": entry.timestamp,
                "latitude": entry.latitude,
                "longitude": entry.longitude,
            }
        }
        
        # Add extra data if available
        if entry.extra_data:
            feature["properties"].update(entry.extra_data)
        
        features.append(feature)
      # Create GeoJSON structure with diagnostic data
    geojson = {
        "type": "FeatureCollection",
        "metadata": {
            "decoder": decoder_name,
            "extraction_timestamp": datetime.now().isoformat(),
            "total_features": len(features),
            "coordinate_system": "WGS84",
            "creator": f"FENDER v{FENDER_VERSION}",
            "case_information": {},
            "system_information": system_info,
            "extraction_information": extraction_info
        },
        "features": features
    }
    
    # Add case information if provided
    if examiner_name:
        geojson["metadata"]["case_information"]["examiner_name"] = examiner_name
    if case_number:
        geojson["metadata"]["case_information"]["case_number"] = case_number
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(geojson, f, indent=2, ensure_ascii=False, default=str)
    
    logger.info(f"GeoJSON report written successfully: {output_path}")


def secure_delete_file(filepath):
    """Securely delete a file by overwriting it multiple times before deletion"""
    logger.info(f"Starting secure deletion of file: {filepath}")
    
    try:
        if not os.path.exists(filepath):
            logger.warning(f"File does not exist for secure deletion: {filepath}")
            return True
            
        file_size = os.path.getsize(filepath)
        logger.debug(f"File size to securely delete: {file_size} bytes")
        
        # Overwrite the file multiple times with different patterns
        patterns = [b'\x00', b'\xFF', b'\xAA', b'\x55']
        
        for i, pattern in enumerate(patterns):
            logger.debug(f"Overwrite pass {i+1}/{len(patterns)} with pattern {pattern.hex()}")
            with open(filepath, 'rb+') as f:
                f.seek(0)
                remaining = file_size
                chunk_size = 65536  # 64KB chunks
                
                while remaining > 0:
                    write_size = min(chunk_size, remaining)
                    f.write(pattern * write_size)
                    remaining -= write_size
                
                f.flush()
                os.fsync(f.fileno())  # Force write to disk
        
        # Final random overwrite pass
        logger.debug("Final random overwrite pass")
        with open(filepath, 'rb+') as f:
            f.seek(0)
            remaining = file_size
            
            while remaining > 0:
                write_size = min(65536, remaining)
                random_data = os.urandom(write_size)
                f.write(random_data)
                remaining -= write_size
            
            f.flush()
            os.fsync(f.fileno())
        
        # Finally delete the file
        os.remove(filepath)
        logger.info(f"File securely deleted: {filepath}")
        return True
        
    except Exception as e:
        logger.error(f"Error during secure deletion of {filepath}: {e}", exc_info=True)
        # Fallback to regular deletion
        try:
            os.remove(filepath)
            logger.warning(f"Fallback to regular deletion successful: {filepath}")
            return True
        except Exception as e2:
            logger.error(f"Fallback deletion also failed for {filepath}: {e2}")
            return False


def secure_delete_directory(dirpath):
    """Securely delete a directory and all its contents"""
    logger.info(f"Starting secure deletion of directory: {dirpath}")
    
    try:
        if not os.path.exists(dirpath):
            logger.warning(f"Directory does not exist for secure deletion: {dirpath}")
            return True
        
        # Recursively secure delete all files
        for root, dirs, files in os.walk(dirpath, topdown=False):
            # Delete all files in this directory
            for file in files:
                filepath = os.path.join(root, file)
                if not secure_delete_file(filepath):
                    logger.error(f"Failed to securely delete file: {filepath}")
            
            # Delete all subdirectories
            for dir in dirs:
                subdir_path = os.path.join(root, dir)
                try:
                    os.rmdir(subdir_path)
                    logger.debug(f"Deleted directory: {subdir_path}")
                except Exception as e:
                    logger.error(f"Failed to delete directory {subdir_path}: {e}")
        
        # Finally delete the root directory
        os.rmdir(dirpath)
        logger.info(f"Directory securely deleted: {dirpath}")
        return True
        
    except Exception as e:
        logger.error(f"Error during secure deletion of directory {dirpath}: {e}", exc_info=True)
        # Fallback to regular deletion
        try:
            shutil.rmtree(dirpath)
            logger.warning(f"Fallback to regular directory deletion successful: {dirpath}")
            return True
        except Exception as e2:
            logger.error(f"Fallback directory deletion also failed for {dirpath}: {e2}")
            return False


def log_report_hash(output_path, logger_instance=None):
    """Calculate and log the SHA256 hash of a generated report"""
    if logger_instance is None:
        logger_instance = logger
    
    try:
        hash_value = get_file_hash_safe(output_path)
        if hash_value:
            logger_instance.info(f"Report generated: {output_path}")
            logger_instance.info(f"Report SHA256 hash: {hash_value}")
            return hash_value
        else:
            logger_instance.error(f"Failed to calculate hash for report: {output_path}")
            return None
    except Exception as e:
        logger_instance.error(f"Error logging report hash for {output_path}: {e}")
        return None
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
        from .file_operations import get_file_hash_safe
        logger.debug("Collecting decoder information from registry")
        system_info["available_decoders"] = list(decoder_registry.get_decoder_names())
        system_info["decoder_details"] = get_decoder_info(decoder_registry)
        system_info["decoder_hashes"] = get_decoder_hashes(decoder_registry)
        logger.info(f"Found {len(system_info['available_decoders'])} decoders")
    
    # Add file hashes for main components
    try:
        main_script_path = os.path.abspath(sys.argv[0])
        logger.debug(f"Calculating hash for main script: {main_script_path}")
        from .file_operations import get_file_hash_safe
        system_info["main_script_hash"] = get_file_hash_safe(main_script_path)
        system_info["main_script_path"] = main_script_path
    except Exception as e:
        logger.error(f"Error getting main script hash: {e}")
        system_info["main_script_hash"] = "Error getting main script hash"
    
    try:
        base_decoder_path = os.path.join(os.path.dirname(sys.argv[0]), "base_decoder.py")
        if os.path.exists(base_decoder_path):
            logger.debug(f"Calculating hash for base decoder: {base_decoder_path}")
            from .file_operations import get_file_hash_safe
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
                from .file_operations import get_file_hash_safe
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
        from .file_operations import get_file_hash_safe
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
"""
FENDER Utility Functions
Contains file operations, system info, and other utility functions
"""
