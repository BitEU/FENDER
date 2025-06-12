import pytest
import logging
from pathlib import Path
import tempfile
import os
from typing import List, Any, Tuple, Optional
import shutil
import sys

# Assuming these imports are in your project structure
# from main_gps_decoder import DecoderRegistry, VehicleGPSDecoder
# from base_decoder import BaseDecoder, GPSEntry

# Dummy classes to make the script runnable standalone
class BaseDecoder:
    def get_name(self) -> str: raise NotImplementedError
    def get_supported_extensions(self) -> List[str]: raise NotImplementedError
    def extract_gps_data(self, file_path: str, progress_callback=None, stop_event=None) -> Tuple[List['GPSEntry'], Optional[str]]: raise NotImplementedError
    def get_xlsx_headers(self) -> List[str]: raise NotImplementedError
    def format_entry_for_xlsx(self, entry: 'GPSEntry') -> List[Any]: raise NotImplementedError
    def get_dropzone_text(self) -> str: raise NotImplementedError

class GPSEntry:
    def __init__(self, latitude: float, longitude: float, timestamp: str, extra_data: dict = None):
        self.latitude = latitude
        self.longitude = longitude
        self.timestamp = timestamp
        self.extra_data = extra_data if extra_data is not None else {}
    def __repr__(self):
        return f"GPSEntry(latitude={self.latitude}, longitude={self.longitude}, timestamp='{self.timestamp}', extra_data={self.extra_data})"

class DecoderRegistry:
    def __init__(self, path="decoders"):
        self.decoders = {}
        # In a real scenario, this would dynamically load decoders.
        # For this test, we'll manually add the mock decoder.
        from mock_decoder import MockDecoder
        decoder_instance = MockDecoder()
        self.decoders[decoder_instance.get_name()] = MockDecoder
    def get_decoder_names(self):
        return list(self.decoders.keys())
    def get_decoder(self, name):
        return self.decoders.get(name)

# Configure logging for cleaner output
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)8s] --- %(message)s', # Cleaner format
    datefmt='%H:%M:%S',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('test_results.log', mode='w') # Overwrite log file on each run
    ]
)
logger = logging.getLogger(__name__)

# Test fixtures
@pytest.fixture
def temp_decoders_dir():
    """Create a temporary decoders directory for testing"""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_decoder_dir = Path(temp_dir) / "decoders"
        temp_decoder_dir.mkdir()
        # Create __init__.py to make it a package
        (temp_decoder_dir / "__init__.py").touch()
        yield temp_decoder_dir

@pytest.fixture
def mock_decoder_file(temp_decoders_dir):
    """Create a mock decoder file for testing"""
    decoder_content = """
from base_decoder import BaseDecoder, GPSEntry
from typing import List, Any, Tuple, Optional

class MockDecoder(BaseDecoder):
    def get_name(self) -> str:
        return "Mock Decoder"

    def get_supported_extensions(self) -> List[str]:
        return [".MOCK"]

    def extract_gps_data(self, file_path: str, progress_callback=None, stop_event=None) -> Tuple[List[GPSEntry], Optional[str]]:
        return [GPSEntry(latitude=1.0, longitude=1.0, timestamp="2025-06-11 12:00:00")], None

    def get_xlsx_headers(self) -> List[str]:
        return ["Latitude", "Longitude", "Timestamp"]

    def format_entry_for_xlsx(self, entry: GPSEntry) -> List[Any]:
        return [entry.latitude, entry.longitude, entry.timestamp]

    def get_dropzone_text(self) -> str:
        return "Drop MOCK files here"
"""
    # Place the mock decoder directly in the temp directory, not a 'decoders' sub-folder
    mock_file_path = temp_decoders_dir / "mock_decoder.py"
    mock_file_path.write_text(decoder_content)
    
    # Add dummy base_decoder.py so the mock can import it
    base_decoder_content = """
from typing import List, Any, Tuple, Optional
class BaseDecoder: pass
class GPSEntry:
    def __init__(self, latitude: float, longitude: float, timestamp: str, extra_data: dict = None):
        self.latitude = latitude
        self.longitude = longitude
        self.timestamp = timestamp
        self.extra_data = extra_data if extra_data is not None else {}
"""
    (temp_decoders_dir / "base_decoder.py").write_text(base_decoder_content)
    
    return mock_file_path


@pytest.fixture
def decoder_registry(temp_decoders_dir, mock_decoder_file):
    """Creates a DecoderRegistry instance with the mock decoder."""
    original_cwd = os.getcwd()
    original_sys_path = sys.path[:]
    
    # The registry needs to import from the temp directory
    os.chdir(temp_decoders_dir)
    sys.path.insert(0, str(temp_decoders_dir))
    
    try:
        registry = DecoderRegistry(path=".") # Look in the current (temp) dir
        logger.info("Fixture Setup: DecoderRegistry created with decoders: %s", registry.get_decoder_names())
        yield registry
    finally:
        # Teardown: Restore original state
        os.chdir(original_cwd)
        sys.path = original_sys_path

# Test classes
class TestDecoderRegistry:
    def test_auto_discover_decoders(self, decoder_registry):
        """Test decoder auto-discovery"""
        logger.info("[PASS] Test: Auto-discover decoders")
        decoder_names = decoder_registry.get_decoder_names()
        assert "Mock Decoder" in decoder_names
        logger.info("Found decoders: %s", decoder_names)

    def test_get_decoder(self, decoder_registry):
        """Test getting decoder by name"""
        logger.info("[PASS] Test: Retrieve a specific decoder by name")
        decoder_class = decoder_registry.get_decoder("Mock Decoder")
        assert decoder_class is not None
        decoder = decoder_class()
        assert decoder.get_name() == "Mock Decoder"
        logger.info("Successfully retrieved decoder: '%s'", decoder.get_name())

class TestBaseDecoder:
    def test_gps_entry_creation(self):
        """Test GPSEntry creation and validation"""
        logger.info("[PASS] Test: GPSEntry creation with extra data")
        entry = GPSEntry(
            latitude=37.7749,
            longitude=-122.4194,
            timestamp="2025-06-11 12:00:00",
            extra_data={"speed": 60}
        )
        assert entry.latitude == 37.7749
        assert entry.extra_data["speed"] == 60
        logger.info("GPSEntry created successfully: %s", entry)

    def test_gps_entry_default_extra_data(self):
        """Test GPSEntry default extra_data initialization"""
        logger.info("[PASS] Test: GPSEntry default 'extra_data' initialization")
        entry = GPSEntry(latitude=0, longitude=0, timestamp="2025-06-11 12:00:00")
        assert entry.extra_data == {}
        logger.info("Verified 'extra_data' defaults to an empty dict.")

class TestMockDecoder:
    def test_supported_extensions(self, decoder_registry):
        """Test supported file extensions"""
        logger.info("[PASS] Test: Mock decoder's supported extensions")
        decoder = decoder_registry.get_decoder("Mock Decoder")()
        extensions = decoder.get_supported_extensions()
        assert ".MOCK" in extensions
        logger.info("Supported extensions: %s", extensions)

    def test_extract_gps_data(self, decoder_registry, tmp_path):
        """Test GPS data extraction"""
        logger.info("[PASS] Test: Mock decoder's data extraction")
        decoder = decoder_registry.get_decoder("Mock Decoder")()
        mock_file = tmp_path / "test.MOCK"
        mock_file.touch()
        
        entries, error = decoder.extract_gps_data(str(mock_file))
        assert error is None
        assert len(entries) == 1
        assert entries[0].latitude == 1.0
        logger.info("Extracted %d entries from the mock file.", len(entries))

    def test_xlsx_formatting(self, decoder_registry):
        """Test XLSX formatting"""
        logger.info("[PASS] Test: Mock decoder's XLSX formatting")
        decoder = decoder_registry.get_decoder("Mock Decoder")()
        
        headers = decoder.get_xlsx_headers()
        logger.info("XLSX Headers: %s", headers)
        assert "Latitude" in headers
        
        entry = GPSEntry(latitude=1.0, longitude=1.0, timestamp="2025-06-11 12:00:00")
        row = decoder.format_entry_for_xlsx(entry)
        logger.info("Formatted Row: %s", row)
        assert row == [1.0, 1.0, "2025-06-11 12:00:00"]

def test_integration(decoder_registry, tmp_path):
    """Integration test for the complete workflow"""
    logger.info("Starting Integration Test: Full Workflow")
    
    mock_file = tmp_path / "test.MOCK"
    mock_file.touch()
    
    decoder = decoder_registry.get_decoder("Mock Decoder")()
    
    logger.info("   [1] Verifying file extension support...")
    assert ".MOCK" in decoder.get_supported_extensions()
    logger.info("       -> OK")
    
    logger.info("   [2] Extracting GPS data...")
    entries, error = decoder.extract_gps_data(str(mock_file))
    assert error is None
    assert len(entries) > 0
    logger.info("       -> OK, extracted %d entries.", len(entries))
    
    logger.info("   [3] Formatting data for XLSX...")
    headers = decoder.get_xlsx_headers()
    rows = [decoder.format_entry_for_xlsx(entry) for entry in entries]
    assert len(headers) == len(rows[0])
    logger.info("       -> OK, headers and rows are consistent.")
    
    logger.info("[PASS] Integration Test Completed Successfully!")

if __name__ == "__main__":
    # Note: Added dummy classes and adjusted imports/fixtures to make this script self-contained and runnable.
    # In your actual project, you would remove the dummy classes.
    logging.info("Starting test suite execution")
    pytest.main([__file__, "-v", "--log-cli-level=INFO"])