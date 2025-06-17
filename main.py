"""
FENDER - Forensic Extraction of Navigational Data & Event Records
Main Entry Point

This is the main entry point for FENDER, which has been modularized into
separate components for better maintainability and organization.
"""

import sys
import logging
import argparse
from pathlib import Path

# FENDER Version Information
FENDER_VERSION = "0.2.2"
FENDER_BUILD_DATE = "June 17 2025"


def setup_logging():
    """Setup comprehensive logging with custom timestamp format that appends to a single log file"""
    from datetime import datetime
    
    # Create logs directory if it doesn't exist
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # Custom formatter with exact timestamp format requested
    class CustomFormatter(logging.Formatter):
        def formatTime(self, record, datefmt=None):
            dt = datetime.fromtimestamp(record.created)
            return dt.strftime('[%Y-%B-%d %H:%M:%S]')
        
        def format(self, record):
            # Get the custom timestamp
            record.asctime = self.formatTime(record)
            # Format the message
            return f"{record.asctime} [{record.levelname}] {record.name} - {record.getMessage()}"
    
    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    
    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # File handler with append mode (no rotation)
    file_handler = logging.FileHandler(
        log_dir / 'fender.log',
        mode='a',  # 'a' for append mode
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(CustomFormatter())
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(CustomFormatter())
    
    # Add handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    # Log startup
    logger.info("="*80)
    logger.info(f"FENDER v{FENDER_VERSION} - Forensic Extraction of Navigational Data & Event Records")
    logger.info(f"Build Date: {FENDER_BUILD_DATE}")
    logger.info(f"Python Version: {sys.version}")
    
    # Import platform here to avoid issues with frozen executables
    try:
        import platform
        import os
        logger.info(f"Platform: {platform.platform()}")
        logger.info(f"Process ID: {os.getpid()}")
    except ImportError:
        logger.warning("Could not import platform information")
    
    logger.info("="*80)
    
    return logger


def main():
    """Main entry point for FENDER"""
    # Initialize logging first
    logger = setup_logging()
    logger.info("FENDER main() started")
    
    try:
        # Parse command line arguments
        parser = argparse.ArgumentParser(
            description='Vehicle GPS Decoder - Extract GPS data from vehicle telematics binary files'
        )
        parser.add_argument('--cli', action='store_true', help='Run in command line interface mode')
        
        args = parser.parse_args()
        logger.info(f"Command line arguments: {sys.argv[1:]}")
        
        if args.cli:
            logger.info("Running in CLI mode")
            from src.cli.cli_interface import run_cli
            run_cli()
        else:
            logger.info("Running in GUI mode")
            from src.gui.main_window import run_gui
            run_gui()
        
        logger.info("FENDER main() completed")
        
    except ImportError as e:
        logger.critical(f"Import error - missing required module: {e}")
        print(f"Error: Missing required module - {e}")
        print("Please ensure all FENDER components are properly installed.")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"Unhandled exception in main: {e}", exc_info=True)
        print(f"Critical error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
