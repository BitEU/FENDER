"""
CLI Interface Module for FENDER

This module contains the command-line interface logic for FENDER,
including user interaction, decoder selection, and processing workflow.
"""

import os
import sys
import logging
from datetime import datetime
from typing import List

from base_decoder import BaseDecoder, GPSEntry
from file_operations import (
    validate_file_path, validate_folder_path, sanitize_filename,
    filter_duplicate_entries, write_excel_report, write_csv_report,
    write_json_report, write_geojson_report, write_kml
)
from system_info import get_system_info, get_extraction_info

logger = logging.getLogger(__name__)

# Duplicate filtering precision
decimals_of_prec = 4


class DecoderRegistry:
    """Registry for loading and managing decoders"""
    
    def __init__(self):
        self.decoders = {}
        self.load_decoders()
    
    def load_decoders(self):
        """Load all available decoders from the decoders directory"""
        logger.info("Loading decoders from decoders directory")
        
        try:
            import importlib
            import inspect
            from pathlib import Path
            
            # Get the decoders directory
            decoders_dir = Path(__file__).parent / "decoders"
            if not decoders_dir.exists():
                logger.error(f"Decoders directory not found: {decoders_dir}")
                return
            
            # Import all decoder modules
            for decoder_file in decoders_dir.glob("*_decoder.py"):
                if decoder_file.name.startswith("__"):
                    continue
                
                module_name = f"decoders.{decoder_file.stem}"
                logger.debug(f"Importing decoder module: {module_name}")
                
                try:
                    module = importlib.import_module(module_name)
                    
                    # Find classes that inherit from BaseDecoder
                    for name, obj in inspect.getmembers(module, inspect.isclass):
                        if issubclass(obj, BaseDecoder) and obj != BaseDecoder:
                            # Try to get the decoder name from the instance
                            try:
                                instance = obj()
                                decoder_name = instance.get_name()
                                self.decoders[decoder_name] = obj
                                logger.info(f"Loaded decoder: {decoder_name}")
                            except Exception as e:
                                logger.error(f"Failed to instantiate decoder {name}: {e}")
                
                except Exception as e:
                    logger.error(f"Failed to load decoder from {decoder_file}: {e}")
            
            logger.info(f"Successfully loaded {len(self.decoders)} decoders")
        
        except Exception as e:
            logger.error(f"Error loading decoders: {e}", exc_info=True)
    
    def get_decoder_names(self):
        """Get list of available decoder names"""
        return sorted(list(self.decoders.keys()))
    
    def get_decoder(self, name):
        """Get decoder class by name"""
        return self.decoders.get(name)


def run_cli():
    """Run the CLI version with enhanced export options"""
    logger.info("Starting FENDER in CLI mode")
    
    print("Vehicle GPS Decoder - CLI Mode")
    print("=" * 40)
    
    # Initialize registry
    registry = DecoderRegistry()
    decoder_names = registry.get_decoder_names()
    
    if not decoder_names:
        logger.error("No decoders found in CLI mode")
        print("Error: No decoders found!")
        return
    
    logger.info(f"Available decoders in CLI: {decoder_names}")
    
    # Select decoder
    print("\\nAvailable decoders:")
    for i, name in enumerate(decoder_names, 1):
        print(f"{i}. {name}")
    
    while True:
        try:
            choice = int(input("\\nSelect decoder (enter number): "))
            if 1 <= choice <= len(decoder_names):
                selected_decoder = decoder_names[choice - 1]
                logger.info(f"CLI decoder selected: {selected_decoder}")
                break
            else:
                print("Invalid choice. Please try again.")
        except ValueError:
            print("Please enter a valid number.")
    
    # Select export format
    print("\\nExport formats:")
    print("1. Excel (.xlsx)")
    print("2. CSV (.csv)")
    print("3. JSON (.json)")
    print("4. GeoJSON (.geojson)")
    print("5. KML (.kml)")

    format_map = {1: "xlsx", 2: "csv", 3: "json", 4: "geojson", 5: "kml"}
    while True:
        try:
            format_choice = int(input("\\nSelect export format (enter number): "))
            if 1 <= format_choice <= 5:
                export_format = format_map[format_choice]
                logger.info(f"CLI export format selected: {export_format}")
                break
            else:
                print("Invalid choice. Please try again.")
        except ValueError:
            print("Please enter a valid number.")
    
    # Check if decoder supports folders
    decoder_class = registry.get_decoder(selected_decoder)
    decoder_instance = decoder_class()
    extensions = decoder_instance.get_supported_extensions()

    if len(extensions) == 0:  # Folder-based decoder
        input_path = input(f"\\nEnter the path to the {selected_decoder} data FOLDER: ").strip()
        logger.info(f"CLI input folder: {input_path}")
    
        # Validate folder
        is_valid, result = validate_folder_path(input_path)
        if not is_valid:
            logger.error(f"CLI folder validation failed: {result}")
            print(f"Error: {result}")
            return
    
        input_file = result
    else:
        # Original file input logic
        input_file = input(f"\\nEnter the path to the {selected_decoder} file: ").strip()
        logger.info(f"CLI input file: {input_file}")
    
        # Validate file
        is_valid, result = validate_file_path(input_file, extensions)
        if not is_valid:
            logger.error(f"CLI file validation failed: {result}")
            print(f"Error: {result}")
            return
    
        input_file = result
    
    # Create decoder and process
    decoder = decoder_instance
    
    # Generate timestamped output filename
    base, _ = os.path.splitext(input_file)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_decoder_name = sanitize_filename(selected_decoder)
    output_file = f"{base}_{safe_decoder_name}_{timestamp}.{export_format}"
    
    print(f"\\nProcessing {selected_decoder} file...")
    logger.info(f"Starting CLI extraction process")
    
    processing_start_time = datetime.now()
    
    def progress_callback(status, percent):
        print(f"{status} ({percent}%)")
        logger.debug(f"CLI progress: {status} ({percent}%)")
    
    entries, error = decoder.extract_gps_data(input_file, progress_callback)

    processing_time = (datetime.now() - processing_start_time).total_seconds()

    if error:
        logger.error(f"CLI extraction error: {error}")
        print(f"Error: {error}")
        return

    logger.info(f"CLI extraction successful: {len(entries)} entries")

    # Ask about duplicate filtering
    filter_choice = input("\\nFilter duplicate entries? (y/n): ").strip().lower()
    if filter_choice == 'y':
        entries = filter_duplicate_entries(entries, decimals_of_prec, logger)
        print(f"Filtered to {len(entries)} unique entries")

    # Get system and extraction info for CLI
    system_info = get_system_info(
        input_file=input_file,
        output_file=output_file,
        execution_mode="CLI",
        decoder_registry=registry
    )
    extraction_info = get_extraction_info(selected_decoder, input_file, output_file, len(entries), processing_time)

    # Write to selected format
    try:
        if export_format == "xlsx":
            logger.debug("Writing XLSX output")
            write_excel_report(entries, output_file, selected_decoder, system_info, extraction_info, decoder)
            
        elif export_format == "csv":
            logger.debug("Writing CSV output")
            write_csv_report(entries, output_file, selected_decoder, system_info, extraction_info, decoder)
                
        elif export_format == "json":
            logger.debug("Writing JSON output")
            write_json_report(entries, output_file, selected_decoder, system_info, extraction_info, decoder)
        
        elif export_format == "geojson":
            logger.debug("Writing GeoJSON output")
            write_geojson_report(entries, output_file, selected_decoder, system_info, extraction_info)

        elif export_format == "kml":
            logger.debug("Writing KML output")
            write_kml(entries, output_file, selected_decoder)
        
        print(f"\\nSuccessfully extracted {len(entries)} GPS entries.")
        print(f"Results written to: {output_file}")
        logger.info(f"CLI processing complete. Output saved to: {output_file}")
        
    except Exception as e:
        logger.error(f"Error writing output file: {e}", exc_info=True)
        print(f"Error writing output file: {e}")


def get_cli_arguments():
    """Parse and return CLI arguments"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Vehicle GPS Decoder - Extract GPS data from vehicle telematics binary files'
    )
    parser.add_argument('--cli', action='store_true', help='Run in command line interface mode')
    
    return parser.parse_args()


def display_decoder_info(registry):
    """Display detailed information about available decoders"""
    print("\\nAvailable Decoders:")
    print("-" * 50)
    
    for i, name in enumerate(registry.get_decoder_names(), 1):
        decoder_class = registry.get_decoder(name)
        decoder_instance = decoder_class()
        extensions = decoder_instance.get_supported_extensions()
        
        print(f"{i}. {name}")
        
        if extensions:
            print(f"   Supported file extensions: {', '.join(extensions)}")
        else:
            print("   Supports folder input")
        
        # Get additional info if available
        if hasattr(decoder_instance, 'description'):
            print(f"   Description: {decoder_instance.description}")
        
        if hasattr(decoder_instance, 'version'):
            print(f"   Version: {decoder_instance.version}")
        
        print()


def validate_cli_input(input_path, decoder_instance):
    """Validate CLI input path based on decoder requirements"""
    extensions = decoder_instance.get_supported_extensions()
    
    if len(extensions) == 0:  # Folder-based decoder
        return validate_folder_path(input_path)
    else:  # File-based decoder
        return validate_file_path(input_path, extensions)


def generate_output_filename(input_file, decoder_name, export_format):
    """Generate timestamped output filename"""
    base, _ = os.path.splitext(input_file)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_decoder_name = sanitize_filename(decoder_name)
    return f"{base}_{safe_decoder_name}_{timestamp}.{export_format}"


def print_processing_summary(entries_count, processing_time, filtered_count=None):
    """Print summary of processing results"""
    print("\\n" + "="*50)
    print("PROCESSING SUMMARY")
    print("="*50)
    print(f"Total entries extracted: {entries_count}")
    
    if filtered_count is not None:
        print(f"Entries after filtering: {filtered_count}")
        print(f"Duplicates removed: {entries_count - filtered_count}")
    
    print(f"Processing time: {processing_time:.2f} seconds")
    print("="*50)


def handle_cli_error(error_message, logger):
    """Handle CLI errors consistently"""
    logger.error(f"CLI Error: {error_message}")
    print(f"Error: {error_message}")
    print("Please check the log file for more details.")


def prompt_for_duplicate_filtering():
    """Prompt user for duplicate filtering preference"""
    while True:
        choice = input("\\nFilter duplicate entries? (y/n): ").strip().lower()
        if choice in ['y', 'yes', '1']:
            return True
        elif choice in ['n', 'no', '0']:
            return False
        else:
            print("Please enter 'y' for yes or 'n' for no.")


def show_export_format_details():
    """Show detailed information about export formats"""
    print("\\nExport Format Details:")
    print("-" * 30)
    print("1. Excel (.xlsx) - Comprehensive report with multiple sheets")
    print("2. CSV (.csv)    - Comma-separated values with metadata")
    print("3. JSON (.json)  - Structured data with full metadata")
    print("4. GeoJSON       - Geographic data format for mapping")
    print("5. KML (.kml)    - Google Earth compatible format")
    print()


def interactive_decoder_selection(registry):
    """Interactive decoder selection with detailed information"""
    decoder_names = registry.get_decoder_names()
    
    print("\\nSelect a decoder:")
    display_decoder_info(registry)
    
    while True:
        try:
            choice = int(input("Enter decoder number: "))
            if 1 <= choice <= len(decoder_names):
                selected_decoder = decoder_names[choice - 1]
                logger.info(f"CLI decoder selected: {selected_decoder}")
                return selected_decoder
            else:
                print(f"Invalid choice. Please enter a number between 1 and {len(decoder_names)}.")
        except ValueError:
            print("Please enter a valid number.")


def interactive_format_selection():
    """Interactive export format selection with details"""
    show_export_format_details()
    
    format_map = {1: "xlsx", 2: "csv", 3: "json", 4: "geojson", 5: "kml"}
    
    while True:
        try:
            format_choice = int(input("Select export format (enter number): "))
            if 1 <= format_choice <= 5:
                export_format = format_map[format_choice]
                logger.info(f"CLI export format selected: {export_format}")
                return export_format
            else:
                print("Invalid choice. Please enter a number between 1 and 5.")
        except ValueError:
            print("Please enter a valid number.")
