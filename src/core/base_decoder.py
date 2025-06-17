from abc import ABC, abstractmethod
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass
import logging
from datetime import datetime

# Setup logger for base_decoder module
logger = logging.getLogger(__name__)

@dataclass
class GPSEntry:
    """Standard GPS entry that all decoders must return"""
    latitude: float
    longitude: float
    timestamp: str
    # Additional fields that may or may not be used by specific decoders
    extra_data: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.extra_data is None:
            self.extra_data = {}
        
        # Log creation of GPS entry
        logger.debug(f"GPSEntry created: lat={self.latitude}, lon={self.longitude}, "
                    f"timestamp={self.timestamp}, extra_data_keys={list(self.extra_data.keys())}")

class BaseDecoder(ABC):
    """Abstract base class for all vehicle telematics decoders"""
    
    def __init__(self):
        self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._logger.info(f"Initializing decoder: {self.__class__.__name__}")
    
    @abstractmethod
    def get_name(self) -> str:
        """Return the name of this decoder (e.g., 'OnStar', 'Toyota')"""
        pass
    
    @abstractmethod
    def get_supported_extensions(self) -> List[str]:
        """Return list of supported file extensions (e.g., ['.CE0'])"""
        pass
    
    @abstractmethod
    def extract_gps_data(self, file_path: str, progress_callback=None, stop_event=None) -> Tuple[List[GPSEntry], Optional[str]]:
        """
        Extract GPS data from the binary file.
        
        Args:
            file_path: Path to the input file
            progress_callback: Optional callback function(status: str, percent: int)
            stop_event: Optional threading.Event to signal stop processing
            
        Returns:
            Tuple of (list of GPSEntry objects, error message or None)
        """
        pass
    
    @abstractmethod
    def get_xlsx_headers(self) -> List[str]:
        """Return the headers for the XLSX file specific to this decoder"""
        pass
    
    @abstractmethod
    def format_entry_for_xlsx(self, entry: GPSEntry) -> List[Any]:
        """Format a GPSEntry into a row for the XLSX file"""
        pass

    @abstractmethod
    def get_dropzone_text(self) -> str:
        """Return the text to display in the drop zone for this decoder."""
        pass
    
    def _log_extraction_start(self, file_path: str):
        """Helper method to log extraction start"""
        self._logger.info(f"Starting GPS extraction from: {file_path}")
        self._logger.debug(f"Decoder: {self.get_name()}, Supported extensions: {self.get_supported_extensions()}")
    
    def _log_extraction_complete(self, entries_count: int, elapsed_time: float = None):
        """Helper method to log extraction completion"""
        if elapsed_time:
            self._logger.info(f"Extraction complete. Extracted {entries_count} entries in {elapsed_time:.2f} seconds")
        else:
            self._logger.info(f"Extraction complete. Extracted {entries_count} entries")
    
    def _log_extraction_error(self, error: str):
        """Helper method to log extraction errors"""
        self._logger.error(f"Extraction failed: {error}")
    
    def _log_progress(self, status: str, percent: int):
        """Helper method to log progress updates"""
        self._logger.debug(f"Progress: {status} ({percent}%)")