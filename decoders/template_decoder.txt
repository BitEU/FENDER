# decoders/template_decoder.py

# Import necessary base classes and types
from base_decoder import BaseDecoder, GPSEntry
from typing import List, Tuple, Optional, Any

# It's often useful to import other standard libraries for binary parsing,
# such as 'struct' for unpacking binary data, 'datetime' for timestamps,
# and 're' for finding patterns.
import struct
from datetime import datetime, timezone

class TemplateDecoder(BaseDecoder):
    """
    This is a template for creating a new decoder.
    To use this template:
    1. Rename this file to something descriptive, like 'ford_decoder.py'.
    2. Rename the class 'TemplateDecoder' to a descriptive name, like 'FordDecoder'.
    3. Implement the logic for each of the abstract methods defined below.
    4. Place the new file in the 'decoders/' directory. The main application
       will automatically discover and load it.
    """

    def get_name(self) -> str:
        """
        Return the name of this decoder. This name will be displayed in the GUI's
        decoder selection list.
        """
        # TODO: Replace "Template" with the actual name of your decoder
        return "Template"

    def get_supported_extensions(self) -> List[str]:
        """
        Return a list of file extensions that this decoder can process.
        For example: ['.BIN', '.DAT']
        The GUI will use these extensions to filter files in the file browser.
        """
        # TODO: Add the file extensions your decoder supports
        return ['.dat']

    def get_xlsx_headers(self) -> List[str]:
        """
        Return a list of strings representing the column headers for the output
        XLSX file. The order of these headers must match the order of the
        data returned by the 'format_entry_for_xlsx' method.
        """
        # TODO: Define your XLSX column headers
        return ['Latitude', 'Longitude', 'Timestamp', 'Speed', 'Altitude', 'Status']

    def format_entry_for_xlsx(self, entry: GPSEntry) -> List[Any]:
        """
        Format a single GPSEntry object into a list of values for an XLSX row.
        The order of items in the returned list must correspond to the headers
        defined in 'get_xlsx_headers'.

        The 'entry' object contains the standard 'lat', 'long', and 'timestamp'
        fields. Any custom data you extracted should be in the 'entry.extra_data'
        dictionary.
        """
        # TODO: Format the GPSEntry into a list for the XLSX row.
        # Access your custom data from the extra_data dictionary.
        return [
            entry.lat,
            entry.long,
            entry.timestamp,
            entry.extra_data.get('speed', 'N/A'),
            entry.extra_data.get('altitude', 'N/A'),
            entry.extra_data.get('status', 'N/A'),
        ]

    def extract_gps_data(self, file_path: str, progress_callback=None) -> Tuple[List[GPSEntry], Optional[str]]:
        """
        This is the core method of the decoder. It reads the binary file,
        parses the data, and returns a list of GPSEntry objects.

        Args:
            file_path: The full path to the input file.
            progress_callback: An optional function to report progress to the GUI.
                               It should be called with (status_string, percentage).

        Returns:
            A tuple containing:
            - A list of GPSEntry objects.
            - An error message string if an error occurred, otherwise None.
        """
        entries = []
        try:
            # 1. Read the binary file
            if progress_callback:
                progress_callback("Reading file...", 10)

            with open(file_path, 'rb') as f:
                binary_data = f.read()

            # 2. Find and parse data records
            # This is where your custom parsing logic goes. You might need to
            # search for specific byte patterns (headers/markers) to find
            # where the GPS records are.
            if progress_callback:
                progress_callback("Parsing data...", 30)

            # Example: Loop through the data to find records. This is just a placeholder.
            # You will need to replace this with your actual logic.
            # for record in find_my_records(binary_data):
            #     # 3. Parse a single record
            #     parsed_data = self.parse_record(record)
            #
            #     # 4. Create a GPSEntry object
            #     # The GPSEntry requires lat, long, and a timestamp string.
            #     # Store any other data in the 'extra_data' dictionary.
            #     gps_entry = GPSEntry(
            #         lat=parsed_data.get('latitude', 0.0),
            #         long=parsed_data.get('longitude', 0.0),
            #         timestamp=parsed_data.get('timestamp_str', ''),
            #         extra_data={
            #             'speed': parsed_data.get('speed', 0),
            #             'altitude': parsed_data.get('altitude', 0),
            #             'status': parsed_data.get('status', 'OK')
            #         }
            #     )
            #     entries.append(gps_entry)
            #
            #     # Update progress periodically
            #     if progress_callback:
            #         # Calculate and report progress percentage
            #         # progress = 30 + (60 * (current_item / total_items))
            #         # progress_callback("Parsing...", progress)
            #         pass

            # Placeholder: Create a dummy entry for demonstration
            dummy_entry = GPSEntry(
                lat=40.7128,
                long=-74.0060,
                timestamp=datetime.now(timezone.utc).isoformat(),
                extra_data={'speed': 55, 'altitude': 100, 'status': 'DUMMY DATA'}
            )
            entries.append(dummy_entry)


            if progress_callback:
                progress_callback("Finalizing...", 90)

            # 5. Return the list of entries and no error
            return entries, None

        except FileNotFoundError:
            return [], f"File not found: {file_path}"
        except Exception as e:
            # If any other error occurs, return an empty list and the error message
            # It's good practice to be specific about the error if possible.
            return [], f"An unexpected error occurred: {str(e)}"

    # It's a good practice to add helper methods for your parsing logic.
    # For example:
    # def parse_record(self, record_bytes: bytes) -> dict:
    #     """
    #     Parses a single block of binary data into a dictionary.
    #     """
    #     # Example using struct to unpack a latitude and longitude
    #     # This assumes a specific binary format that you would know.
    #     # lat_raw, lon_raw = struct.unpack('<ii', record_bytes[0:8])
    #     #
    #     # data = {
    #     #     'latitude': lat_raw / 1_000_000.0,
    #     #     'longitude': lon_raw / 1_000_000.0,
    #     #     ... other fields
    #     # }
    #     # return data
    #     pass