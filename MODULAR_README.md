# FENDER Modular Architecture

FENDER has been successfully modularized into the following components:

## Core Modules

### 1. `main_gps_decoder.py`
- **Purpose**: Main entry point for the application
- **Contents**: 
  - Logging setup
  - Command line argument parsing
  - Application initialization
  - Import and execution of GUI or CLI modes

### 2. `main_window.py`
- **Purpose**: GUI components and user interface
- **Contents**:
  - `VehicleGPSDecoder` class - Main GUI application
  - `CustomRadiobutton` and `CustomToggleButton` classes - Custom UI widgets
  - GUI setup, styling, event handling
  - File processing workflow for GUI mode
  - Drag-and-drop functionality
  - Progress reporting and error handling

### 3. `cli_interface.py`
- **Purpose**: Command-line interface logic
- **Contents**:
  - `DecoderRegistry` class - Manages available decoders
  - `run_cli()` function - Main CLI workflow
  - User interaction for decoder/format selection
  - CLI-specific processing and output
  - Helper functions for CLI operation

### 4. `file_operations.py`
- **Purpose**: File handling and export operations
- **Contents**:
  - File validation and security functions
  - Export format writers (Excel, CSV, JSON, GeoJSON, KML)
  - Secure file operations (temp files, copying, etc.)
  - Duplicate entry filtering
  - File path sanitization and validation

### 5. `system_info.py`
- **Purpose**: System information gathering
- **Contents**:
  - Hardware and OS information collection
  - Decoder integrity verification
  - Network connectivity checks
  - Permission validation
  - Extraction metadata generation

## Benefits of Modularization

### 1. **Improved Maintainability**
- Each module has a clear, single responsibility
- Easier to locate and fix bugs
- Changes to one component don't affect others

### 2. **Better Code Organization**
- Related functionality is grouped together
- Cleaner separation of concerns
- More readable and understandable codebase

### 3. **Enhanced Testability**
- Individual modules can be tested in isolation
- Easier to write unit tests for specific functionality
- Better debugging capabilities

### 4. **Simplified Development**
- Developers can focus on specific components
- Parallel development of different modules possible
- Easier onboarding for new developers

### 5. **Reusability**
- Modules can be reused in other projects
- Common functionality is extracted and shared
- Easier to extend with new features

## Module Dependencies

```
main_gps_decoder.py
├── main_window.py
│   ├── cli_interface.py (DecoderRegistry)
│   ├── file_operations.py
│   ├── system_info.py
│   └── base_decoder.py
└── cli_interface.py
    ├── file_operations.py
    ├── system_info.py
    └── base_decoder.py
```

## Usage

The modular structure maintains backward compatibility:

```bash
# GUI mode (default)
python main_gps_decoder.py

# CLI mode
python main_gps_decoder.py --cli
```

## File Structure

```
FENDER/
├── main_gps_decoder.py          # Main entry point
├── main_window.py               # GUI components
├── cli_interface.py             # CLI interface
├── file_operations.py           # File handling
├── system_info.py               # System information
├── base_decoder.py              # Base decoder class
├── main_gps_decoder_original.py # Original monolithic file (backup)
├── decoders/                    # Decoder implementations
│   ├── __init__.py
│   ├── honda_decoder.py
│   ├── mercedes_decoder.py
│   ├── onstar_decoder.py
│   ├── stellantis_decoder.py
│   └── toyota_decoder.py
└── logs/                        # Log files
    └── fender.log
```

## Future Enhancements

The modular architecture makes it easier to:

1. **Add new decoders**: Simply add them to the `decoders/` directory
2. **Support new export formats**: Add functions to `file_operations.py`
3. **Enhance the GUI**: Modify only `main_window.py`
4. **Improve CLI**: Work only with `cli_interface.py`
5. **Add new system checks**: Extend `system_info.py`

This modular approach provides a solid foundation for future development and maintenance of FENDER.
