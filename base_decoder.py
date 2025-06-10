from abc import ABC, abstractmethod
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass

@dataclass
class GPSEntry:
    """Standard GPS entry that all decoders must return"""
    latitude: float  # Fixed the typo from 'latitutde' to 'latitude'
    longitude: float
    timestamp: str
    # Additional fields that may or may not be used by specific decoders
    extra_data: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.extra_data is None:
            self.extra_data = {}

class BaseDecoder(ABC):
    """Abstract base class for all vehicle telematics decoders"""
    
    @abstractmethod
    def get_name(self) -> str:
        """Return the name of this decoder (e.g., 'OnStar', 'Toyota')"""
        pass
    
    @abstractmethod
    def get_supported_extensions(self) -> List[str]:
        """Return list of supported file extensions (e.g., ['.CE0'])"""
        pass
    
    @abstractmethod
    def extract_gps_data(self, file_path: str, progress_callback=None) -> Tuple[List[GPSEntry], Optional[str]]:
        """
        Extract GPS data from the binary file.
        
        Args:
            file_path: Path to the input file
            progress_callback: Optional callback function(status: str, percent: int)
            
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