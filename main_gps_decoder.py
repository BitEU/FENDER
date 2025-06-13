import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import os
import sys
import json
import csv
from pathlib import Path
from tkinterdnd2 import DND_FILES, TkinterDnD
from openpyxl import Workbook
import platform
import argparse
from typing import List, Dict, Type
import importlib
import inspect
from datetime import datetime
import hashlib
import shutil
import locale
import socket
import subprocess
import tempfile
import secrets
import stat
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

# Import base decoder
from base_decoder import BaseDecoder, GPSEntry

# FENDER Version Information
FENDER_VERSION = "1.1.8"
FENDER_BUILD_DATE = "June 13 2025"

if platform.system() == "Windows":
    import ctypes
    from ctypes import windll

def get_system_info(input_file=None, output_file=None, execution_mode="GUI", decoder_registry=None):
    """Gather system and configuration information for reports"""
    
    # Get directory paths for permission checking
    output_dir = os.path.dirname(output_file) if output_file else os.getcwd()
    
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
    
    # Add file permission checks if files are provided
    if input_file:
        system_info["read_permissions_granted"] = check_read_permissions(input_file)
    
    if output_file:
        system_info["write_permissions_granted"] = check_write_permissions(output_dir)
    
    # Add CLI arguments if running in CLI mode
    if execution_mode == "CLI":
        system_info["cli_arguments"] = " ".join(sys.argv)
    
    # Add decoder information if registry is provided
    if decoder_registry:
        system_info["available_decoders"] = list(decoder_registry.get_decoder_names())
        system_info["decoder_details"] = get_decoder_info(decoder_registry)
        system_info["decoder_hashes"] = get_decoder_hashes(decoder_registry)
    
    # Add file hashes for main components
    try:
        main_script_path = os.path.abspath(__file__)
        system_info["main_script_hash"] = get_file_hash_safe(main_script_path)
        system_info["main_script_path"] = main_script_path
    except:
        system_info["main_script_hash"] = "Error getting main script hash"
    
    try:
        base_decoder_path = os.path.join(os.path.dirname(__file__), "base_decoder.py")
        if os.path.exists(base_decoder_path):
            system_info["base_decoder_hash"] = get_file_hash_safe(base_decoder_path)
            system_info["base_decoder_path"] = base_decoder_path
        else:
            system_info["base_decoder_hash"] = "base_decoder.py not found"
    except:
        system_info["base_decoder_hash"] = "Error getting base decoder hash"
    
    return system_info

def get_decoder_hashes(registry):
    """Get SHA256 hashes of all loaded decoder files for integrity verification"""
    decoder_hashes = {}
    
    for name in registry.get_decoder_names():
        try:
            decoder_class = registry.get_decoder(name)
            
            # Get the module file path
            module = inspect.getmodule(decoder_class)
            if module and hasattr(module, '__file__') and module.__file__:
                file_path = os.path.abspath(module.__file__)
                
                # Calculate hash
                decoder_hashes[name] = {
                    "file_path": file_path,
                    "sha256_hash": get_file_hash_safe(file_path),
                    "file_size": os.path.getsize(file_path) if os.path.exists(file_path) else 0,
                    "last_modified": datetime.fromtimestamp(
                        os.path.getmtime(file_path)
                    ).isoformat() if os.path.exists(file_path) else "Unknown"
                }
            else:
                decoder_hashes[name] = {
                    "error": "Could not determine decoder file path"
                }
                
        except Exception as e:
            decoder_hashes[name] = {
                "error": f"Error getting decoder hash: {str(e)}"
            }
    
    return decoder_hashes

def secure_temp_file(suffix="", prefix="fender_", dir=None):
    """Create a secure temporary file with restricted permissions"""
    # Create temporary file with secure permissions
    fd, path = tempfile.mkstemp(suffix=suffix, prefix=prefix, dir=dir)
    
    # Set restrictive permissions (owner read/write only)
    if platform.system() != "Windows":
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    
    return fd, path

def secure_temp_dir(prefix="fender_", dir=None):
    """Create a secure temporary directory with restricted permissions"""
    path = tempfile.mkdtemp(prefix=prefix, dir=dir)
    
    # Set restrictive permissions (owner only)
    if platform.system() != "Windows":
        os.chmod(path, stat.S_IRWXU)
    
    return path

def secure_file_copy(src, dst, chunk_size=65536):
    """Securely copy file with verification"""
    src_hash = hashlib.sha256()
    dst_hash = hashlib.sha256()
    
    with open(src, 'rb') as src_file, open(dst, 'wb') as dst_file:
        while True:
            chunk = src_file.read(chunk_size)
            if not chunk:
                break
            src_hash.update(chunk)
            dst_file.write(chunk)
    
    # Verify copy integrity
    with open(dst, 'rb') as dst_file:
        while True:
            chunk = dst_file.read(chunk_size)
            if not chunk:
                break
            dst_hash.update(chunk)
    
    if src_hash.hexdigest() != dst_hash.hexdigest():
        raise ValueError("File copy verification failed - checksums don't match")
    
    return dst_hash.hexdigest()

def sanitize_filename(filename):
    """Sanitize filename to prevent path traversal attacks"""
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
    
    return filename

def validate_file_path(file_path, allowed_extensions=None):
    """Validate file path for security"""
    try:
        # Resolve to absolute path to prevent traversal
        abs_path = os.path.abspath(file_path)
        
        # Check if file exists
        if not os.path.exists(abs_path):
            return False, "File does not exist"
        
        # Check if it's actually a file
        if not os.path.isfile(abs_path):
            return False, "Path is not a file"
        
        # Check file extension if provided
        if allowed_extensions:
            file_ext = os.path.splitext(abs_path)[1].lower()
            if file_ext not in [ext.lower() for ext in allowed_extensions]:
                return False, f"File extension not allowed. Allowed: {allowed_extensions}"
        
        # Check file size (prevent extremely large files)
        file_size = os.path.getsize(abs_path)
        max_size = 10 * 1024 * 1024 * 1024  # 10GB limit
        if file_size > max_size:
            return False, f"File too large. Maximum size: {max_size/1024/1024/1024:.1f}GB"
        
        return True, abs_path
        
    except Exception as e:
        return False, f"Path validation error: {str(e)}"

def write_geojson(entries: List[GPSEntry], output_path: str, decoder_name: str = "Unknown"):
    """Write GPS entries to GeoJSON format"""
    features = []
    
    for i, entry in enumerate(entries):
        # Skip invalid coordinates
        if (entry.latitude == 0 and entry.longitude == 0) or \
           not (-90 <= entry.latitude <= 90) or \
           not (-180 <= entry.longitude <= 180):
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
        
        features.append(feature)
    
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
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(geojson, f, indent=2, ensure_ascii=False)

def get_file_hash(file_path: str) -> str:
    """Calculate SHA256 hash of the input file"""
    try:
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            # Read file in chunks to handle large files
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()
    except Exception as e:
        return f"Error calculating hash: {str(e)}"

def get_extraction_info(decoder_name: str, input_file: str, output_file: str, entry_count: int, processing_time: float = None):
    """Gather extraction-specific information"""
    file_size = os.path.getsize(input_file) if os.path.exists(input_file) else 0
    
    extraction_info = {
        "input_file": {
            "path": input_file,
            "filename": os.path.basename(input_file),
            "size_bytes": file_size,
            "size_mb": round(file_size / (1024 * 1024), 2),
            "sha256_hash": get_file_hash(input_file)
        },
        "output_file": {
            "path": output_file,
            "filename": os.path.basename(output_file)
        },
        "extraction_details": {
            "decoder_used": decoder_name,
            "entries_extracted": entry_count,
            "processing_time_seconds": processing_time,
        }
    }
    
    return extraction_info

def get_system_ram():
    """Get system RAM information"""
    if PSUTIL_AVAILABLE:
        try:
            memory = psutil.virtual_memory()
            available_gb = memory.available / (1024**3)
            total_gb = memory.total / (1024**3)
            return f"{available_gb:.1f} GB / {total_gb:.1f} GB"
        except Exception as e:
            return f"psutil error: {str(e)}"
    else:
        return get_system_ram_fallback()

def get_system_ram_fallback():
    """Get system RAM information using platform-specific commands"""
    try:
        if platform.system() == "Windows":
            result = subprocess.run(['wmic', 'computersystem', 'get', 'TotalPhysicalMemory'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                if len(lines) > 1:
                    total_bytes = int(lines[1].strip())
                    total_gb = total_bytes / (1024**3)
                    return f"Total: {total_gb:.1f} GB (Available: Unknown)"
        elif platform.system() == "Linux":
            with open('/proc/meminfo', 'r') as f:
                lines = f.readlines()
                mem_total = mem_available = None
                for line in lines:
                    if line.startswith('MemTotal:'):
                        mem_total = int(line.split()[1]) * 1024
                    elif line.startswith('MemAvailable:'):
                        mem_available = int(line.split()[1]) * 1024
                
                if mem_total:
                    total_gb = mem_total / (1024**3)
                    if mem_available:
                        available_gb = mem_available / (1024**3)
                        return f"{available_gb:.1f} GB / {total_gb:.1f} GB"
                    else:
                        return f"Total: {total_gb:.1f} GB (Available: Unknown)"
        
        return "RAM info not available on this platform"
    except Exception as e:
        return f"Error getting RAM info: {str(e)}"

def get_disk_space(path):
    """Get available disk space for a given path"""
    try:
        usage = shutil.disk_usage(os.path.dirname(path))
        available_gb = usage.free / (1024**3)
        return f"{available_gb:.1f} GB"
    except Exception as e:
        return f"Error getting disk space: {str(e)}"

def check_read_permissions(file_path):
    """Check if file is readable"""
    try:
        return "Yes" if os.access(file_path, os.R_OK) else "No"
    except Exception:
        return "Error checking permissions"

def check_write_permissions(directory_path):
    """Check if directory is writable"""
    try:
        return "Yes" if os.access(directory_path, os.W_OK) else "No"
    except Exception:
        return "Error checking permissions"

def get_system_locale():
    """Get system locale information using modern locale methods"""
    try:
        current_locale = locale.getlocale()
        if current_locale[0]:
            locale_info = current_locale[0]
        else:
            try:
                locale.setlocale(locale.LC_ALL, '')
                locale_info = locale.getlocale()[0] or "Unknown"
            except locale.Error:
                try:
                    encoding = locale.getencoding()
                    locale_info = f"Default encoding: {encoding}"
                except:
                    locale_info = "Unknown"
        
        try:
            encoding = locale.getencoding()
            return f"{locale_info} (Encoding: {encoding})"
        except:
            return locale_info
            
    except Exception as e:
        return f"Error getting locale: {str(e)}"

def check_network_status():
    """Check if system has network connectivity"""
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return "Online"
    except Exception:
        return "Offline"

def get_file_hash_safe(file_path):
    """Get file hash with error handling"""
    try:
        return get_file_hash(file_path)
    except Exception as e:
        return f"Error: {str(e)}"

def get_decoder_info(registry):
    """Get information about available decoders"""
    decoder_info = {}
    for name in registry.get_decoder_names():
        try:
            decoder_class = registry.get_decoder(name)
            decoder_instance = decoder_class()
            decoder_info[name] = {
                "supported_extensions": decoder_instance.get_supported_extensions(),
                "class_name": decoder_class.__name__,
                "module": decoder_class.__module__
            }
        except Exception as e:
            decoder_info[name] = {"error": str(e)}
    return decoder_info

def get_resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class DecoderRegistry:
    """Registry for managing available decoders"""
    def __init__(self):
        self.decoders: Dict[str, Type[BaseDecoder]] = {}
        self.auto_discover_decoders()

    def register(self, decoder_class: Type[BaseDecoder]):
        """Register a new decoder"""
        instance = decoder_class()
        self.decoders[instance.get_name()] = decoder_class

    def auto_discover_decoders(self):
        """Automatically discover and register decoders from the decoders directory"""
        if getattr(sys, 'frozen', False):
            decoders_dir = Path(get_resource_path("decoders"))
            resource_path = get_resource_path("")
            if resource_path not in sys.path:
                sys.path.insert(0, resource_path)
        else:
            decoders_dir = Path("decoders")
            sys.path.append(str(decoders_dir.parent))

        if not decoders_dir.exists():
            print(f"Decoders directory not found: {decoders_dir}")
            return

        print(f"Looking for decoders in: {decoders_dir}")

        for file_path in decoders_dir.glob("*_decoder.py"):
            module_name = f"decoders.{file_path.stem}"
            print(f"Attempting to load: {module_name}")
            try:
                module = importlib.import_module(module_name)
                for name, obj in inspect.getmembers(module):
                    if (inspect.isclass(obj) and
                        issubclass(obj, BaseDecoder) and
                        obj != BaseDecoder):
                        print(f"Registered decoder: {obj}")
                        self.register(obj)
            except Exception as e:
                print(f"Failed to load decoder from {file_path}: {e}")
                import traceback
                traceback.print_exc()

    def get_decoder_names(self) -> List[str]:
        """Get list of available decoder names"""
        return sorted(self.decoders.keys())

    def get_decoder(self, name: str) -> Type[BaseDecoder]:
        """Get decoder class by name"""
        return self.decoders.get(name)

class CustomRadiobutton(tk.Canvas):
    """Custom radiobutton that matches the dark theme"""
    def __init__(self, parent, text, variable, value, **kwargs):
        super().__init__(parent, highlightthickness=0, **kwargs)
        self.text = text
        self.variable = variable
        self.value = value
        self.selected = False
        
        # Colors
        self.bg_color = '#1a1a1a'
        self.border_color = '#666666'
        self.selected_color = '#4a9eff'
        self.text_color = '#cccccc'
        self.text_selected_color = '#ffffff'
        
        # Calculate width based on text length
        text_width = len(text) * 8 + 40  # Rough estimate: 8px per char + padding
        canvas_width = max(120, text_width)  # Minimum 120px
        
        # Configure canvas
        self.configure(bg=self.bg_color, width=canvas_width, height=30)
        
        # Bind events
        self.bind('<Button-1>', self.on_click)
        self.bind('<Enter>', self.on_enter)
        self.bind('<Leave>', self.on_leave)
        
        # Watch variable changes
        self.variable.trace('w', self.on_variable_change)
        
        # Initial draw
        self.draw()
    
    def draw(self):
        """Draw the radiobutton"""
        self.delete('all')
        
        # Check if selected
        self.selected = (self.variable.get() == self.value)
        
        # Draw circle
        circle_x = 10
        circle_y = 15
        circle_r = 6
        
        if self.selected:
            # Selected state - filled circle
            self.create_oval(circle_x - circle_r, circle_y - circle_r,
                           circle_x + circle_r, circle_y + circle_r,
                           outline=self.selected_color, fill=self.selected_color, width=2)
            # Inner circle
            self.create_oval(circle_x - 3, circle_y - 3,
                           circle_x + 3, circle_y + 3,
                           outline='white', fill='white', width=1)
        else:
            # Unselected state - empty circle
            self.create_oval(circle_x - circle_r, circle_y - circle_r,
                           circle_x + circle_r, circle_y + circle_r,
                           outline=self.border_color, fill=self.bg_color, width=2)
        
        # Draw text
        text_color = self.text_selected_color if self.selected else self.text_color
        self.create_text(25, 15, text=self.text, anchor='w', 
                        fill=text_color, font=('Segoe UI', 10))
    
    def on_click(self, event):
        """Handle click event"""
        self.variable.set(self.value)
    
    def on_enter(self, event):
        """Handle mouse enter"""
        self.configure(cursor='hand2')
    
    def on_leave(self, event):
        """Handle mouse leave"""
        self.configure(cursor='')
    
    def on_variable_change(self, *args):
        """Handle variable change"""
        self.draw()

class VehicleGPSDecoder:
    def __init__(self, root):
        self.root = root
        self.root.title(f"FENDER v{FENDER_VERSION}")
        self.root.geometry("1200x700")
        self.root.configure(bg='#1a1a1a')
        self.processing_start_time = None
        self.execution_mode = "GUI"
        
        # Initialize decoder registry
        self.decoder_registry = DecoderRegistry()
        decoder_names = self.decoder_registry.get_decoder_names()

        # Check if decoders were found
        if not decoder_names:
            self.root.withdraw()
            messagebox.showerror("Initialization Error",
                                 "No decoders found.\n\nPlease ensure decoder files are properly included.")
            self.root.destroy()
            return

        self.current_decoder = None
        self.selected_decoder_name = decoder_names[0]
        self.decoder_buttons = {}
        self.export_format = tk.StringVar(value="xlsx")  # Default to XLSX

        self.setup_styles()
        self.input_file = None
        self.is_processing = False
        self.stop_event = threading.Event()

        self.setup_ui()
        self.setup_drag_drop()
    
    def select_decoder(self, decoder_name: str):
        """Handle decoder selection from the button list."""
        self.selected_decoder_name = decoder_name
        
        # Update button styles
        for name, button in self.decoder_buttons.items():
            if name == decoder_name:
                button.configure(style='Selected.TButton')
            else:
                button.configure(style='DecoderList.TButton')
        
        # Trigger updates
        self.on_decoder_changed()

    def setup_styles(self):
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        # Configure styles
        self.style.configure('Title.TLabel', 
                           background='#1a1a1a', 
                           foreground='#ffffff', 
                           font=('Segoe UI', 24, 'bold'))
        
        self.style.configure('Subtitle.TLabel', 
                   background='#1a1a1a', 
                   foreground='#cccccc', 
                   font=('Segoe UI', 13))
        
        self.style.configure('Dark.TFrame', 
                           background='#1a1a1a', 
                           relief='flat')
        
        self.style.configure('DropZone.TFrame', 
                           background='#252525',
                           relief='solid', 
                           borderwidth=1,
                           bordercolor='#333333')
        
        self.style.configure('Dark.TButton',
                   background='#4a9eff',
                   foreground='white',
                   font=('Segoe UI', 11),
                   borderwidth=0,
                   focuscolor='none',
                   padding=(12, 8))
        
        self.style.map('Dark.TButton',
                      background=[('active', '#3d8ce6'),
                                ('pressed', '#2d7acc')])
        
        self.style.configure('Disabled.TButton',
                   background='#888888',
                   foreground='#cccccc',
                   font=('Segoe UI', 11),
                   borderwidth=0,
                   focuscolor='none',
                   padding=(12, 8))
        
        self.style.map('Disabled.TButton',
                      background=[('active', '#888888'), ('disabled', '#888888')],
                      foreground=[('disabled', '#cccccc')])
        
        self.style.configure('Progress.TProgressbar',
                           background='#4a9eff',
                           troughcolor='#333333',
                           borderwidth=0,
                           lightcolor='#4a9eff',
                           darkcolor='#4a9eff')
        
        self.style.configure('Horizontal.TProgressbar',
                           background='#4a9eff',
                           troughcolor='#333333',
                           borderwidth=0,
                           lightcolor='#4a9eff',
                           darkcolor='#4a9eff')

        self.style.configure('DecoderList.TButton',
                   background='#252525',
                   foreground='#cccccc',
                   font=('Segoe UI', 12),
                   borderwidth=1,
                   focuscolor='none',
                   bordercolor='#1a1a1a',
                   padding=(15, 10))
        
        self.style.map('DecoderList.TButton',
                      background=[('active', '#333333')])
        
        self.style.configure('Selected.TButton',
                           background='#4a9eff',
                           foreground='white',
                           font=('Segoe UI', 11, 'bold'),
                           borderwidth=1,
                           bordercolor='#1a1a1a',
                           focuscolor='none',
                           padding=(15, 10))
        
        self.style.map('Selected.TButton',
                      background=[('active', '#3d8ce6')])
    
    def setup_ui(self):
        # Main container
        main_frame = ttk.Frame(self.root, style='Dark.TFrame')
        main_frame.pack(fill='both', expand=True, padx=20, pady=20)
        
        # Left Panel for Decoder Selection
        left_panel = ttk.Frame(main_frame, style='Dark.TFrame', width=190)
        left_panel.pack_propagate(False)
        left_panel.pack(side='left', fill='y', padx=(0, 20))
        
        decoder_label = ttk.Label(left_panel, text="Select Decoder",
                                  background='#1a1a1a', foreground='#ffffff',
                                  font=('Segoe UI', 14, 'bold'))
        decoder_label.pack(anchor='w', pady=(10, 15))
        
        # Scrollable area for decoder buttons
        canvas = tk.Canvas(left_panel, bg='#1a1a1a', highlightthickness=0)
        scrollbar = ttk.Scrollbar(left_panel, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas, style='Dark.TFrame')
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Populate decoder buttons
        for decoder_name in self.decoder_registry.get_decoder_names():
            btn = ttk.Button(scrollable_frame, text=decoder_name,
                             style='DecoderList.TButton',
                             command=lambda name=decoder_name: self.select_decoder(name))
            btn.pack(fill='x', expand=True, pady=2)
            self.decoder_buttons[decoder_name] = btn
            
        # Right Panel for Main Content
        right_panel = ttk.Frame(main_frame, style='Dark.TFrame')
        right_panel.pack(side='right', fill='both', expand=True)
        
        # Header
        header_frame = ttk.Frame(right_panel, style='Dark.TFrame')
        header_frame.pack(fill='x', pady=(0, 20))
        title_label = ttk.Label(header_frame, text="Forensic Extraction of Navigational Data & Event Records", style='Title.TLabel')
        title_label.pack(anchor='w')
        subtitle_label = ttk.Label(header_frame, text="Extract and decode GPS data with timestamps from vehicle telematics binary files", style='Subtitle.TLabel')
        subtitle_label.pack(anchor='w', pady=(5, 0))

        # Export format selection with custom radio buttons
        export_frame = ttk.Frame(right_panel, style='Dark.TFrame')
        export_frame.pack(fill='x', pady=(0, 15))
        
        export_label = ttk.Label(export_frame, text="Export Format:",
                                background='#1a1a1a', foreground='#ffffff',
                                font=('Segoe UI', 12, 'bold'))
        export_label.pack(anchor='w', pady=(0, 5))
        
        format_frame = ttk.Frame(export_frame, style='Dark.TFrame')
        format_frame.pack(anchor='w')
        
        # Custom radio buttons for export format
        xlsx_radio = CustomRadiobutton(format_frame, "Excel (.xlsx)", 
                                      self.export_format, "xlsx",
                                      bg='#1a1a1a')
        xlsx_radio.pack(side='left', padx=(0, 20))
        
        csv_radio = CustomRadiobutton(format_frame, "CSV (.csv)", 
                                     self.export_format, "csv",
                                     bg='#1a1a1a')
        csv_radio.pack(side='left', padx=(0, 20))
        
        json_radio = CustomRadiobutton(format_frame, "JSON (.json)", 
                                      self.export_format, "json",
                                      bg='#1a1a1a')
        json_radio.pack(side='left', padx=(0, 20))
        
        geojson_radio = CustomRadiobutton(format_frame, "GeoJSON (.geojson)", 
                                         self.export_format, "geojson",
                                         bg='#1a1a1a')
        geojson_radio.pack(side='left')

        # Drop zone
        self.drop_frame = ttk.Frame(right_panel, style='DropZone.TFrame')
        self.drop_frame.pack(fill='both', expand=True, pady=(0, 20))
        drop_content = tk.Frame(self.drop_frame, bg='#252525')
        drop_content.place(relx=0.5, rely=0.5, anchor='center')
        icon_label = tk.Label(drop_content, text="📁", bg='#252525', fg='#4a9eff', font=('Segoe UI', 48))
        icon_label.pack(pady=(0, 10))
        self.drop_label = tk.Label(drop_content, text="", bg='#252525', fg='#cccccc', font=('Segoe UI', 14), justify='center')
        self.drop_label.pack()
        self.file_info_label = tk.Label(drop_content, text="", bg='#252525', fg='#888888', font=('Segoe UI', 10))
        self.file_info_label.pack(pady=(10, 0))

        # Buttons frame
        button_frame = ttk.Frame(right_panel, style='Dark.TFrame')
        button_frame.pack(fill='x', pady=(0, 20))
        self.browse_btn = ttk.Button(button_frame, text="Browse Files", style='Dark.TButton', command=self.browse_file)
        self.browse_btn.pack(side='left', padx=(0, 10))
        self.process_btn = ttk.Button(button_frame, text="Process File", style='Disabled.TButton', command=self.process_file, state='disabled')
        self.process_btn.pack(side='left')
        self.clear_btn = ttk.Button(button_frame, text="Clear", style='Disabled.TButton', command=self.clear_file, state='disabled')
        self.clear_btn.pack(side='right')
        self.stop_btn = ttk.Button(button_frame, text="Stop Processing", style='Disabled.TButton', command=self.stop_processing, state='disabled')
        self.stop_btn.pack(side='right', padx=(0, 10))

        # Progress section
        progress_frame = ttk.Frame(right_panel, style='Dark.TFrame')
        progress_frame.pack(fill='x')
        self.progress_label = ttk.Label(progress_frame, text="", background='#1a1a1a', foreground='#cccccc', font=('Segoe UI', 10))
        self.progress_label.pack(anchor='w', pady=(0, 5))
        self.progress = ttk.Progressbar(progress_frame, style='Horizontal.TProgressbar', mode='determinate', length=300)
        self.progress.pack(fill='x')

        # Results section
        results_frame = ttk.Frame(right_panel, style='Dark.TFrame')
        results_frame.pack(fill='x', pady=(20, 0))
        self.results_label = ttk.Label(results_frame, text="", background='#1a1a1a', foreground='#4a9eff', font=('Segoe UI', 11, 'bold'))
        self.results_label.pack(anchor='w')

        # Set initial state
        self.select_decoder(self.selected_decoder_name)
    
    def setup_drag_drop(self):
        # Bind click event to drop zone
        self.drop_frame.bind("<Button-1>", lambda e: self.browse_file())
        self.drop_label.bind("<Button-1>", lambda e: self.browse_file())
        
        # Enable drag-and-drop
        self.drop_frame.drop_target_register(DND_FILES)
        self.drop_frame.dnd_bind('<<Drop>>', self.on_file_drop)
    
    def on_decoder_changed(self):
        """Handle decoder type change"""
        decoder_class = self.decoder_registry.get_decoder(self.selected_decoder_name)
        decoder_instance = decoder_class()
        self.drop_label.configure(text=decoder_instance.get_dropzone_text())

        if self.input_file:
            self.clear_file()
    
    def browse_file(self):
        if self.is_processing:
            return
        
        decoder_class = self.decoder_registry.get_decoder(self.selected_decoder_name)
        decoder_instance = decoder_class()
        extensions = decoder_instance.get_supported_extensions()
        
        filetypes = []
        if extensions:
            ext_str = ";".join([f"*{ext}" for ext in extensions])
            filetypes.append((f"{self.selected_decoder_name} files", ext_str))
        filetypes.append(("All files", "*.*"))
        
        file_path = filedialog.askopenfilename(
            title=f"Select {self.selected_decoder_name} Binary File",
            filetypes=filetypes
        )
        
        if file_path:
            # Validate file path
            is_valid, result = validate_file_path(file_path, extensions)
            if is_valid:
                self.set_input_file(result)
            else:
                messagebox.showerror("File Validation Error", result)
    
    def set_input_file(self, file_path):
        self.input_file = file_path
        filename = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        size_mb = file_size / (1024 * 1024)
        
        self.drop_label.configure(text=f"Selected: {filename}")
        self.file_info_label.configure(text=f"Size: {size_mb:.2f} MB")
        self.process_btn.configure(state='normal', style='Dark.TButton')
        self.clear_btn.configure(state='normal', style='Dark.TButton')
    
    def clear_file(self):
        if self.is_processing:
            return
        
        self.input_file = None
        decoder_class = self.decoder_registry.get_decoder(self.selected_decoder_name)
        decoder_instance = decoder_class()
        self.drop_label.configure(text=decoder_instance.get_dropzone_text())
        self.file_info_label.configure(text="")
        self.process_btn.configure(state='disabled', style='Disabled.TButton')
        self.progress_label.configure(text="")
        self.progress['value'] = 0
        self.results_label.configure(text="")
        self.clear_btn.configure(state='disabled', style='Disabled.TButton')
    
    def generate_timestamped_filename(self, base_path: str, decoder_name: str, format_ext: str) -> str:
        """Generate filename with timestamp"""
        base, _ = os.path.splitext(base_path)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_decoder_name = sanitize_filename(decoder_name)
        return f"{base}_{safe_decoder_name}_{timestamp}.{format_ext}"
    
    def process_file(self):
        if not self.input_file or self.is_processing:
            return
    
        self.stop_event.clear()
        
        self.processing_start_time = datetime.now()
        self.is_processing = True
        self.process_btn.configure(state='disabled', text='Processing...')
        self.browse_btn.configure(state='disabled')
        self.clear_btn.configure(state='disabled')
        self.stop_btn.configure(state='normal', style='Dark.TButton')
    
        # Get decoder
        decoder_class = self.decoder_registry.get_decoder(self.selected_decoder_name)
        self.current_decoder = decoder_class()
    
        # Generate output path with timestamp and selected format
        format_ext = self.export_format.get()
        output_path = self.generate_timestamped_filename(self.input_file, self.selected_decoder_name, format_ext)
    
        # Start processing in a separate thread
        thread = threading.Thread(target=self.process_in_background, 
                                args=(self.input_file, output_path))
        thread.daemon = True
        thread.start()
    
    def process_in_background(self, input_path, output_path):
        def progress_callback(status, percent):
            self.root.after(0, self.update_progress, status, percent)

        try:
            # Pass stop_event to decoder
            entries, error = self.current_decoder.extract_gps_data(
                input_path, progress_callback, stop_event=self.stop_event
            )
            
            if error:
                self.root.after(0, self.processing_error, error)
            else:
                # Write to selected format
                format_type = self.export_format.get()
                self.root.after(0, self.update_progress, f"Writing {format_type.upper()} file...", 85)
                
                if format_type == "xlsx":
                    self.write_xlsx(entries, output_path)
                elif format_type == "csv":
                    self.write_csv(entries, output_path)
                elif format_type == "json":
                    self.write_json(entries, output_path)
                elif format_type == "geojson":
                    write_geojson(entries, output_path, self.selected_decoder_name)
                
                self.root.after(0, self.processing_complete, len(entries), output_path)
                
        except Exception as e:
            self.root.after(0, self.processing_error, str(e))
    
    def write_xlsx(self, entries: List[GPSEntry], output_path: str):
        """Write GPS entries to XLSX file using decoder-specific format with extraction details"""
        wb = Workbook()
    
        # Main GPS Data worksheet
        ws_data = wb.active
        ws_data.title = "GPS Data"
    
        # Get headers from decoder
        headers = self.current_decoder.get_xlsx_headers()
        ws_data.append(headers)
    
        # Write entries
        for entry in entries:
            row = self.current_decoder.format_entry_for_xlsx(entry)
            ws_data.append(row)
    
        # Create Extraction Details worksheet
        ws_details = wb.create_sheet("Extraction Details")
    
        # Get system and extraction info
        system_info = get_system_info(
            input_file=self.input_file,
            output_file=output_path,
            execution_mode=self.execution_mode,
            decoder_registry=self.decoder_registry
        )
        processing_time = (datetime.now() - self.processing_start_time).total_seconds() if self.processing_start_time else None
        extraction_info = get_extraction_info(
            self.selected_decoder_name, 
            self.input_file, 
            output_path, 
            len(entries),
            processing_time
        )
    
        # Write extraction details
        ws_details.append(["FENDER Extraction Report"])
        ws_details.append([])
    
        # System Information
        ws_details.append(["System Information"])
        ws_details.append(["Field", "Value"])
        for key, value in system_info.items():
            if key != "decoder_hashes":  # Handle separately
                ws_details.append([key.replace("_", " ").title(), str(value)])
    
        ws_details.append([])
    
        # Decoder Hashes
        if "decoder_hashes" in system_info:
            ws_details.append(["Decoder Integrity Verification"])
            ws_details.append(["Decoder", "File Path", "SHA256 Hash", "File Size", "Last Modified"])
            for decoder_name, hash_info in system_info["decoder_hashes"].items():
                if "error" in hash_info:
                    ws_details.append([decoder_name, "Error", hash_info["error"], "", ""])
                else:
                    ws_details.append([
                        decoder_name,
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
        if processing_time:
            ws_details.append(["Processing Time (seconds)", round(processing_time, 2)])
    
        # Format the details worksheet
        ws_details.column_dimensions['A'].width = 25
        ws_details.column_dimensions['B'].width = 50
        ws_details.column_dimensions['C'].width = 70
    
        wb.save(output_path)
    
    def write_csv(self, entries: List[GPSEntry], output_path: str):
        """Write GPS entries to CSV file with extraction details"""
        headers = self.current_decoder.get_xlsx_headers()
    
        # Get system and extraction info
        system_info = get_system_info(
            input_file=self.input_file,
            output_file=output_path,
            execution_mode=self.execution_mode,
            decoder_registry=self.decoder_registry
        )
        processing_time = (datetime.now() - self.processing_start_time).total_seconds() if self.processing_start_time else None
        extraction_info = get_extraction_info(
            self.selected_decoder_name, 
            self.input_file, 
            output_path, 
            len(entries),
            processing_time
        )
    
        with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
        
            # Write headers
            writer.writerow(headers)
        
            # Write entries
            for entry in entries:
                row = self.current_decoder.format_entry_for_xlsx(entry)
                writer.writerow(row)
        
            # Add separator
            for _ in range(5):
                writer.writerow([])
        
            # Write extraction details
            writer.writerow(["FENDER Extraction Report"])
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
                for decoder_name, hash_info in system_info["decoder_hashes"].items():
                    if "error" in hash_info:
                        writer.writerow([decoder_name, "Error", hash_info["error"], "", ""])
                    else:
                        writer.writerow([
                            decoder_name,
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
            if processing_time:
                writer.writerow(["Processing Time (seconds)", round(processing_time, 2)])
    
    def write_json(self, entries: List[GPSEntry], output_path: str):
        """Write GPS entries to JSON file with extraction details"""
        # Get system and extraction info
        system_info = get_system_info(
            input_file=self.input_file,
            output_file=output_path,
            execution_mode=self.execution_mode,
            decoder_registry=self.decoder_registry
        )
        processing_time = (datetime.now() - self.processing_start_time).total_seconds() if self.processing_start_time else None
        extraction_info = get_extraction_info(
            self.selected_decoder_name, 
            self.input_file, 
            output_path, 
            len(entries),
            processing_time
        )
    
        json_data = {
            "metadata": {
                "decoder": self.selected_decoder_name,
                "extraction_timestamp": datetime.now().isoformat(),
                "total_entries": len(entries)
            },
            "system_information": system_info,
            "extraction_information": extraction_info,
            "gps_entries": []
        }
    
        headers = self.current_decoder.get_xlsx_headers()
    
        for entry in entries:
            row = self.current_decoder.format_entry_for_xlsx(entry)
            entry_dict = {}
        
            # Map row data to headers
            for i, header in enumerate(headers):
                if i < len(row):
                    entry_dict[header] = row[i]
        
            # Add core GPS data
            entry_dict.update({
                "latitude": entry.latitude,
                "longitude": entry.longitude,
                "timestamp": entry.timestamp,
                "extra_data": entry.extra_data
            })
        
            json_data["gps_entries"].append(entry_dict)
    
        with open(output_path, 'w', encoding='utf-8') as jsonfile:
            json.dump(json_data, jsonfile, indent=2, ensure_ascii=False, default=str)
    
    def update_progress(self, status, percent):
        self.progress_label.configure(text=status)
        self.progress['value'] = percent
        self.root.update_idletasks()
    
    def processing_complete(self, entry_count, output_path):
        self.is_processing = False
        self.process_btn.configure(state='normal', text='Process File', style='Dark.TButton')
        self.browse_btn.configure(state='normal')
        self.clear_btn.configure(state='normal', style='Dark.TButton')
        self.stop_btn.configure(state='disabled', style='Disabled.TButton')
        
        self.progress_label.configure(text="Processing complete!")
        self.progress['value'] = 100
        
        output_filename = os.path.basename(output_path)
        format_type = self.export_format.get().upper()
        result_text = f"✓ Successfully extracted {entry_count} GPS entries to {format_type}:\n {output_filename}"
        
        self.results_label.configure(text=result_text)
    
    def processing_error(self, error_msg):
        self.is_processing = False
        self.process_btn.configure(state='normal', text='Process File')
        self.browse_btn.configure(state='normal')
        self.clear_btn.configure(state='normal')
        self.stop_btn.configure(state='disabled', style='Disabled.TButton')
        
        self.progress_label.configure(text="Processing failed!")
        self.progress['value'] = 0
        self.results_label.configure(text=f"✗ Error: {error_msg}")
        
        messagebox.showerror("Processing Error", f"Failed to process file:\n\n{error_msg}")
    
    def stop_processing(self):
        if self.is_processing:
            self.stop_event.set()
            self.progress_label.configure(text="Stopping...")
            self.stop_btn.configure(state='disabled', style='Disabled.TButton')
    
    def on_file_drop(self, event):
        if self.is_processing:
            return
        file_path = event.data.strip().split()[0]
        if os.path.isfile(file_path):
            # Validate dropped file
            decoder_class = self.decoder_registry.get_decoder(self.selected_decoder_name)
            decoder_instance = decoder_class()
            extensions = decoder_instance.get_supported_extensions()
            
            is_valid, result = validate_file_path(file_path, extensions)
            if is_valid:
                self.set_input_file(result)
            else:
                messagebox.showerror("File Validation Error", result)

def run_cli():
    """Run the CLI version with enhanced export options"""
    print("Vehicle GPS Decoder - CLI Mode")
    print("=" * 40)
    
    # Initialize registry
    registry = DecoderRegistry()
    decoder_names = registry.get_decoder_names()
    
    if not decoder_names:
        print("Error: No decoders found!")
        return
    
    # Select decoder
    print("\nAvailable decoders:")
    for i, name in enumerate(decoder_names, 1):
        print(f"{i}. {name}")
    
    while True:
        try:
            choice = int(input("\nSelect decoder (enter number): "))
            if 1 <= choice <= len(decoder_names):
                selected_decoder = decoder_names[choice - 1]
                break
            else:
                print("Invalid choice. Please try again.")
        except ValueError:
            print("Please enter a valid number.")
    
    # Select export format
    print("\nExport formats:")
    print("1. Excel (.xlsx)")
    print("2. CSV (.csv)")
    print("3. JSON (.json)")
    print("4. GeoJSON (.geojson)")
    
    format_map = {1: "xlsx", 2: "csv", 3: "json", 4: "geojson"}
    while True:
        try:
            format_choice = int(input("\nSelect export format (enter number): "))
            if 1 <= format_choice <= 4:
                export_format = format_map[format_choice]
                break
            else:
                print("Invalid choice. Please try again.")
        except ValueError:
            print("Please enter a valid number.")
    
    # Get file path
    input_file = input(f"\nEnter the path to the {selected_decoder} file: ").strip()
    
    # Validate file
    decoder_class = registry.get_decoder(selected_decoder)
    decoder_instance = decoder_class()
    extensions = decoder_instance.get_supported_extensions()
    
    is_valid, result = validate_file_path(input_file, extensions)
    if not is_valid:
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
    
    print(f"\nProcessing {selected_decoder} file...")
    
    def progress_callback(status, percent):
        print(f"{status} ({percent}%)")
    
    entries, error = decoder.extract_gps_data(input_file, progress_callback)

    if error:
        print(f"Error: {error}")
    else:
        # Write to selected format
        if export_format == "xlsx":
            wb = Workbook()
            ws = wb.active
            ws.title = "GPS Data"
            
            headers = decoder.get_xlsx_headers()
            ws.append(headers)
            
            for entry in entries:
                row = decoder.format_entry_for_xlsx(entry)
                ws.append(row)
            
            wb.save(output_file)
            
        elif export_format == "csv":
            headers = decoder.get_xlsx_headers()
            
            with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(headers)
                
                for entry in entries:
                    row = decoder.format_entry_for_xlsx(entry)
                    writer.writerow(row)
                    
        elif export_format == "json":
            json_data = {
                "metadata": {
                    "decoder": selected_decoder,
                    "extraction_timestamp": datetime.now().isoformat(),
                    "total_entries": len(entries)
                },
                "gps_entries": []
            }
            
            headers = decoder.get_xlsx_headers()
            
            for entry in entries:
                row = decoder.format_entry_for_xlsx(entry)
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
            
            with open(output_file, 'w', encoding='utf-8') as jsonfile:
                json.dump(json_data, jsonfile, indent=2, ensure_ascii=False, default=str)
        
        elif export_format == "geojson":
            write_geojson(entries, output_file, selected_decoder)
        
        print(f"\nSuccessfully extracted {len(entries)} GPS entries.")
        print(f"Results written to: {output_file}")

def run_gui():
    """Run the GUI version"""
    root = TkinterDnD.Tk()
    
    # Set icon
    try:
        icon_path = get_resource_path("car.ico")
        if os.path.exists(icon_path):
            root.iconbitmap(icon_path)
    except tk.TclError:
        pass
    
    app = VehicleGPSDecoder(root)
    
    # Center window
    root.update_idletasks()
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    window_width = root.winfo_width()
    window_height = root.winfo_height()
    position_x = (screen_width // 2) - (window_width // 2)
    position_y = (screen_height // 2) - (window_height // 2)
    root.geometry(f"+{position_x}+{position_y}")
    
    root.mainloop()

def main():
    parser = argparse.ArgumentParser(
        description='Vehicle GPS Decoder - Extract GPS data from vehicle telematics binary files'
    )
    parser.add_argument('--cli', action='store_true', help='Run in command line interface mode')
    
    args = parser.parse_args()
    
    if args.cli:
        run_cli()
    else:
        run_gui()

if __name__ == "__main__":
    main()