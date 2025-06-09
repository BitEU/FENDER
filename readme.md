# **FENDER \- Vehicle GPS Decoder**

FENDER (Forensic Extractor of Navigational Data and Electronic Records) is a powerful, user-friendly tool designed to extract and decode GPS data from vehicle telematics binary files. It supports multiple vehicle brands and provides output in a clean, easy-to-read XLSX format. The application features a simple drag-and-drop graphical user interface (GUI) as well as a command-line interface (CLI) for advanced users and automation.

## **Features**

* **Intuitive GUI:** A simple drag-and-drop interface for easy file processing.  
* **Command-Line Interface:** A CLI mode for scripting and batch processing.  
* **Extensible Decoder Architecture:** Easily add support for new vehicle makes and models by creating new decoder modules.  
* **Automatic Decoder Discovery:** The application automatically finds and registers new decoders placed in the decoders directory.  
* **XLSX Export:** Extracted GPS data is saved in a well-formatted .xlsx file for easy analysis in spreadsheet software.  
* **Cross-Platform:** Built with standard Python libraries to run on multiple operating systems.

## **Supported Decoders**

* **OnStar** (for .CE0, .CE0.001, .CE0.002 files)  
* **Toyota** (for .CE0 files)

## **Quick Start & Simple Usage (GUI)**

The easiest way to use the Vehicle GPS Decoder is through its graphical interface.

### **Running the Application**

To run the GUI, simply execute the main script without any command-line arguments:  
```python main\_gps\_decoder.py```

### **Step-by-Step Instructions**

1. **Select Decoder Type:**  
   * On the left-hand side, you will see a list of available decoders. Select the one that matches the vehicle brand of your binary file.  
2. **Choose Your File:**  
   * You can either **drag and drop** your vehicle's binary file directly onto the "Drop Zone" in the center of the application.  
   * Or, you can **click the "Browse Files" button** to open a file dialog and select your file manually.  
3. **Process the File:**  
   * Once you've selected a file, the "Process File" button will become active. Click it to begin the extraction and decoding process.  
   * You will see a progress bar and status updates as the application works.  
4. **Get Your Results:**  
   * When processing is complete, a success message will appear.  
   * An .xlsx file containing the extracted GPS data will be saved in the **same directory** as your input file. The output file will be named based on the original filename and the decoder used (e.g., YourFile\_OnStar.xlsx).

## **Advanced Usage & Developer Guide**

### **Command-Line Interface (CLI)**

For power users and for integrating the decoder into automated workflows, a full-featured CLI is available.

#### **Running the CLI**

Launch the application with the \--cli flag to enter command-line mode.  
```python main\_gps\_decoder.py \--cli```

#### **Step-by-Step Instructions**

1. **Select a Decoder:**  
   * The application will list the available decoders. Enter the number corresponding to your choice.  
2. **Provide File Path:**  
   * You will be prompted to enter the full path to the binary file you wish to process.  
3. **Processing and Output:**  
   * The tool will display the processing status directly in your terminal.  
   * Upon completion, an .xlsx file will be saved in the same directory as the input file, just like in the GUI version.

### **For Developers: Creating a New Decoder**

The application is designed to be highly extensible. You can add support for a new vehicle make by creating your own decoder class. The DecoderRegistry will automatically discover and load any valid decoder module placed in the decoders/ directory.  
A valid decoder file must:

1. Be placed in the decoders/ directory.  
2. Have a filename ending in \_decoder.py.  
3. Contain a class that inherits from BaseDecoder and implements all its abstract methods.

#### **The BaseDecoder Abstract Class**

Your custom decoder class **must** inherit from BaseDecoder and implement the following five methods:

1. get\_name(self) \-\> str  
   * **Purpose:** Returns the name of your decoder (e.g., "Ford", "Tesla"). This name will appear in the UI.  
   * **Example:** return "Ford"  
2. get\_supported\_extensions(self) \-\> List\[str\]  
   * **Purpose:** Returns a list of file extensions that this decoder supports (e.g., \['.BIN', '.DAT'\]). This is used to filter files in the "Browse" dialog.  
   * **Example:** return \['.BIN'\]  
3. extract\_gps\_data(self, file\_path: str, progress\_callback=None) \-\> Tuple\[List\[GPSEntry\], Optional\[str\]\]  
   * **Purpose:** This is the core logic of your decoder. It reads the file at file\_path, parses the binary data, and extracts the GPS records.  
   * **Return Value:** It must return a tuple containing two elements:  
     * A list of GPSEntry objects.  
     * An error message string if something goes wrong, or None if successful.  
   * **Progress Callback:** You can optionally call the progress\_callback function to update the GUI's progress bar. Call it with a status string and a percentage (0-100).  
4. get\_xlsx\_headers(self) \-\> List\[str\]  
   * **Purpose:** Defines the column headers for the output .xlsx file.  
   * **Example:** return \['Latitude', 'Longitude', 'Timestamp', 'Speed (km/h)'\]  
5. format\_entry\_for\_xlsx(self, entry: GPSEntry) \-\> List\[Any\]  
   * **Purpose:** Takes a single GPSEntry object and formats it into a list that can be written as a row in the output XLSX file. The order of items in the list must match the order of headers from get\_xlsx\_headers.

#### **The GPSEntry Dataclass**

When extracting data, each GPS record should be stored in a GPSEntry object. This standardizes the data structure across all decoders.  
from dataclasses import dataclass  
from typing import Dict, Any

@dataclass  
class GPSEntry:  
    lat: float  
    long: float  
    timestamp: str  
    extra\_data: Dict\[str, Any\] \= None \# Optional

* lat, long, timestamp: These are the mandatory, standardized fields.  
* extra\_data: This is an optional dictionary where you can store any additional, decoder-specific information (e.g., speed, altitude, vehicle status) that you want to use in your format\_entry\_for\_xlsx method.

### **Project Structure**

* main\_gps\_decoder.py: The main application entry point, containing the GUI, CLI, and DecoderRegistry logic.  
* base\_decoder.py: Defines the abstract BaseDecoder class and the GPSEntry dataclass.  
* onstar\_decoder.py: The decoder implementation for OnStar systems.  
* toyota\_decoder.py: The decoder implementation for Toyota systems.  
* decoders/: A directory where you can place custom decoders for auto-discovery.

### **Dependencies**

This project requires the following Python libraries:

* tkinter / tkinterdnd2: For the graphical user interface.  
* openpyxl: For writing data to .xlsx files.
