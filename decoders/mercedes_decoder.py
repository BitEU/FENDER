import sqlite3
import struct
import pandas as pd
from datetime import datetime, timezone
import os

class MercedesGPSExtractor:
    def __init__(self, db_path):
        self.db_path = db_path
        self.INT32_MAX = 2147483647  # 2^31 - 1
    
    def decode_gps_coordinate(self, encoded_value):
        """
        Decode GPS coordinate from proprietary format
        Formula: decoded_value = encoded_value * 180 / Int32.MAX_VALUE
        """
        # Convert unsigned to signed if necessary
        if encoded_value > self.INT32_MAX:
            encoded_value = encoded_value - 2**32
        
        return (encoded_value * 180.0) / self.INT32_MAX
    
    def decode_bounding_box(self, bounding_data):
        """
        Decode the bounding box binary data
        Format: 01 01 01 00 + two sets of GPS coordinates (lon, lat, elevation)
        """
        if len(bounding_data) < 28:  # 4 byte header + 6*4 bytes for coordinates
            return None
        
        # Skip the 4-byte header (01 01 01 00)
        coords_data = bounding_data[4:]
        
        # Unpack 6 32-bit little-endian integers
        coords = struct.unpack('<6I', coords_data)
        
        # First set: longitude, latitude, elevation
        lon1 = self.decode_gps_coordinate(coords[0])
        lat1 = self.decode_gps_coordinate(coords[1])
        elev1 = coords[2]  # Elevation in centimeters
        
        # Second set: longitude, latitude, elevation  
        lon2 = self.decode_gps_coordinate(coords[3])
        lat2 = self.decode_gps_coordinate(coords[4])
        elev2 = coords[5]  # Elevation in centimeters
        
        # Removed bbox_* fields from output
        return {}
    
    def decode_path_events(self, path_data, start_timestamp):
        """
        Decode the path binary data to extract GPS events
        Format: 04 01 01 00 + segments with various event types
        """
        events = []
        
        if len(path_data) < 8:
            return events
        
        # Skip header (04 01 01 00) and get number of segments
        if len(path_data) < 6:
            return events
            
        num_segments = struct.unpack('<H', path_data[4:6])[0]
        offset = 6
        
        try:
            for segment_idx in range(num_segments):
                if offset + 4 > len(path_data):
                    break
                
                # Read segment size
                segment_size = struct.unpack('<I', path_data[offset:offset+4])[0]
                if offset + segment_size > len(path_data):
                    break
                
                segment_data = path_data[offset:offset+segment_size]
                
                # Parse events within this segment
                event_offset = 16  # Skip segment header (size + 3 words)
                
                while event_offset + 5 < len(segment_data):
                    # Read event ID and distance
                    event_id = segment_data[event_offset]
                    distance = struct.unpack('<I', segment_data[event_offset+1:event_offset+5])[0]
                    
                    event_offset += 5
                    
                    if event_id == 1:  # GPS coordinates
                        if event_offset + 12 <= len(segment_data):
                            coords = struct.unpack('<3I', segment_data[event_offset:event_offset+12])
                            lon = self.decode_gps_coordinate(coords[0])
                            lat = self.decode_gps_coordinate(coords[1])
                            elev = coords[2]  # Elevation in centimeters
                            
                            # Removed 'distance' and 'event_type' from event
                            events.append({
                                'longitude': lon,
                                'latitude': lat,
                                'elevation': elev
                            })
                            event_offset += 12
                    
                    elif event_id == 2:  # Milliseconds since start
                        if event_offset + 4 <= len(segment_data):
                            millis = struct.unpack('<I', segment_data[event_offset:event_offset+4])[0]
                            # Not used in output
                            event_offset += 4
                    
                    elif event_id == 3:  # Timestamp
                        if event_offset + 8 <= len(segment_data):
                            # Skip 4 zero bytes, then read timestamp
                            timestamp = struct.unpack('<I', segment_data[event_offset+4:event_offset+8])[0]
                            # Not used in output
                            event_offset += 8
                    
                    else:
                        # Skip unknown events
                        if event_id == 14 or event_id == 16:
                            pass  # No additional data
                        elif event_id == 15:
                            event_offset += 4
                        elif event_id == 18:
                            event_offset += 1
                        else:
                            break  # Unknown event, stop parsing
                
                offset += segment_size
                
        except struct.error:
            pass  # Handle malformed data gracefully
        
        return events
    
    def unix_to_iso(self, unix_timestamp):
        """Convert Unix timestamp to ISO formatted UTC string"""
        if unix_timestamp and unix_timestamp > 0:
            try:
                dt = datetime.fromtimestamp(unix_timestamp, tz=timezone.utc)
                return dt.isoformat()
            except (ValueError, OSError):
                return None
        return None
    
    def extract_gps_data(self):
        """Extract all GPS data from the database"""
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"Database file not found: {self.db_path}")
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get all trails
        cursor.execute("SELECT * FROM Trails")
        trails = cursor.fetchall()
        
        # Get column names
        column_names = [description[0] for description in cursor.description]
        
        all_data = []
        
        for trail in trails:
            trail_dict = dict(zip(column_names, trail))
            
            trail_id = trail_dict['TrailId']
            begin_time = trail_dict['BeginTime']
            end_time = trail_dict['EndTime']
            bounding_data = trail_dict['Bounding']
            path_data = trail_dict['Path']
            
            # Convert timestamps to ISO format
            begin_time_iso = self.unix_to_iso(begin_time)
            end_time_iso = self.unix_to_iso(end_time)
            
            # Decode bounding box
            bbox_info = self.decode_bounding_box(bounding_data) if bounding_data else {}
            
            # Decode path events
            events = self.decode_path_events(path_data, begin_time) if path_data else []
            
            # Create base record (DriverId removed)
            base_record = {
                'TrailId': trail_id,
                'BeginTime_ISO': begin_time_iso,
                'EndTime_ISO': end_time_iso
            }
            
            # Add bounding box info (now empty dict)
            base_record.update(bbox_info)
            
            # If no GPS events in path, just add the trail info
            if not events:
                all_data.append(base_record)
            else:
                # Add each GPS event as a separate row (GPS_Elevation_cm removed)
                for event in events:
                    record = base_record.copy()
                    record.update({
                        'GPS_Longitude': event['longitude'],
                        'GPS_Latitude': event['latitude']
                    })
                    all_data.append(record)
        
        conn.close()
        return all_data

    def export_to_excel(self, output_file='mercedes_gps_data.xlsx'):
        """Extract data and export to Excel"""
        print("Extracting GPS data from Mercedes NTG5*2 database...")
        data = self.extract_gps_data()
        
        if not data:
            print("No data found in database")
            return
        
        # Create DataFrame
        df = pd.DataFrame(data)
        
        # Reorder columns for better readability (DriverId and GPS_Elevation_cm removed)
        preferred_order = [
            'TrailId', 'BeginTime_ISO', 'EndTime_ISO',
            'GPS_Longitude', 'GPS_Latitude'
        ]
        
        # Add any remaining columns
        remaining_cols = [col for col in df.columns if col not in preferred_order]
        column_order = [col for col in preferred_order if col in df.columns] + remaining_cols
        
        df = df[column_order]
        
        # Export to Excel
        with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='GPS_Data', index=False)
            
            # Auto-adjust column widths
            worksheet = writer.sheets['GPS_Data']
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
                worksheet.column_dimensions[column_letter].width = adjusted_width
        
        print(f"Data exported to {output_file}")
        print(f"Total records: {len(df)}")
        print(f"Unique trails: {df['TrailId'].nunique()}")
        
        # Print summary statistics
        if 'GPS_Longitude' in df.columns:
            gps_records = df.dropna(subset=['GPS_Longitude', 'GPS_Latitude'])
            print(f"GPS coordinate records: {len(gps_records)}")
            if len(gps_records) > 0:
                print(f"Latitude range: {gps_records['GPS_Latitude'].min():.6f} to {gps_records['GPS_Latitude'].max():.6f}")
                print(f"Longitude range: {gps_records['GPS_Longitude'].min():.6f} to {gps_records['GPS_Longitude'].max():.6f}")
        
        return df

def main():
    # Update this path to your database location
    db_path = r"C:\Users\wcdaht\Downloads\QNX_2\Mercedes\NTG5HU-HDD\p2\nav\trails.sqlite"
    
    try:
        extractor = MercedesGPSExtractor(db_path)
        df = extractor.export_to_excel('mercedes_gps_extracted.xlsx')
        
        # Display first few rows
        print("\nFirst 5 rows of extracted data:")
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', None)
        print(df.head())
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()