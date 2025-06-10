import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import os
import sys
from pathlib import Path
from tkinterdnd2 import DND_FILES, TkinterDnD
from openpyxl import Workbook
import platform
import argparse
from typing import List, Dict, Type
import importlib
import inspect

# Import base decoder
from base_decoder import BaseDecoder, GPSEntry

if platform.system() == "Windows":
    import ctypes
    from ctypes import windll

def get_resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
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
        # Handle both development and frozen (PyInstaller) environments
        if getattr(sys, 'frozen', False):
            # Running in a PyInstaller bundle
            decoders_dir = Path(get_resource_path("decoders"))
            # Add the resource path to sys.path temporarily
            resource_path = get_resource_path("")
            if resource_path not in sys.path:
                sys.path.insert(0, resource_path)
        else:
            # Running in development
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

class VehicleGPSDecoder:
    def __init__(self, root):
        self.root = root
        self.root.title("FENDER")
        self.root.geometry("1150x600")
        self.root.configure(bg='#1a1a1a')
        
        # Initialize decoder registry
        self.decoder_registry = DecoderRegistry()
        decoder_names = self.decoder_registry.get_decoder_names()

        # Check if decoders were found
        if not decoder_names:
            self.root.withdraw()  # Hide the empty window
            messagebox.showerror("Initialization Error",
                                 "No decoders found.\n\nPlease ensure decoder files are properly included.")
            self.root.destroy()
            return

        self.current_decoder = None
        self.selected_decoder_name = decoder_names[0]
        self.decoder_buttons = {}

        self.setup_styles()
        self.input_file = None
        self.is_processing = False

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
        
        self.style.configure('Dark.TRadiobutton',
                           background='#1a1a1a',
                           foreground='#cccccc',
                           font=('Segoe UI', 10),
                           focuscolor='none')
        
        self.style.map('Dark.TRadiobutton',
                      background=[('active', '#1a1a1a')],
                      foreground=[('active', '#ffffff')])

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
        
        # --- Left Panel for Decoder Selection ---
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
            
        # --- Right Panel for Main Content ---
        right_panel = ttk.Frame(main_frame, style='Dark.TFrame')
        right_panel.pack(side='right', fill='both', expand=True)
        
        # Header
        header_frame = ttk.Frame(right_panel, style='Dark.TFrame')
        header_frame.pack(fill='x', pady=(0, 20))
        title_label = ttk.Label(header_frame, text="Forensic Extraction of Navigational Data & Event Records", style='Title.TLabel')
        title_label.pack(anchor='w')
        subtitle_label = ttk.Label(header_frame, text="Extract and decode GPS data with timestamps from vehicle telematics binary files", style='Subtitle.TLabel')
        subtitle_label.pack(anchor='w', pady=(5, 0))

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

        # Clear current file if any
        if self.input_file:
            self.clear_file()
    
    def browse_file(self):
        if self.is_processing:
            return
        
        # Get selected decoder
        decoder_class = self.decoder_registry.get_decoder(self.selected_decoder_name)
        decoder_instance = decoder_class()
        extensions = decoder_instance.get_supported_extensions()
        
        # Build file types
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
            self.set_input_file(file_path)
    
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
        decoder_name = self.selected_decoder_name
        self.drop_label.configure(text=f"Drop {decoder_name} binary file here\nor click to browse")
        self.file_info_label.configure(text="")
        self.process_btn.configure(state='disabled', style='Disabled.TButton')
        self.progress_label.configure(text="")
        self.progress['value'] = 0
        self.results_label.configure(text="")
        self.clear_btn.configure(state='disabled', style='Disabled.TButton')
    
    def process_file(self):
        if not self.input_file or self.is_processing:
            return
        
        self.is_processing = True
        self.process_btn.configure(state='disabled', text='Processing...')
        self.browse_btn.configure(state='disabled')
        self.clear_btn.configure(state='disabled')
        
        # Get decoder
        decoder_class = self.decoder_registry.get_decoder(self.selected_decoder_name)
        self.current_decoder = decoder_class()
        
        # Generate output path
        base, _ = os.path.splitext(self.input_file)
        output_path = f"{base}_{self.selected_decoder_name}.xlsx"
        
        # Start processing in a separate thread
        thread = threading.Thread(target=self.process_in_background, 
                                args=(self.input_file, output_path))
        thread.daemon = True
        thread.start()
    
    def process_in_background(self, input_path, output_path):
        def progress_callback(status, percent):
            self.root.after(0, self.update_progress, status, percent)
        
        try:
            # Extract GPS data using the decoder
            entries, error = self.current_decoder.extract_gps_data(
                input_path, progress_callback
            )
            
            if error:
                self.root.after(0, self.processing_error, error)
            else:
                # Write to XLSX
                self.root.after(0, self.update_progress, "Writing XLSX file...", 85)
                self.write_xlsx(entries, output_path)
                self.root.after(0, self.processing_complete, len(entries), output_path)
                
        except Exception as e:
            self.root.after(0, self.processing_error, str(e))
    
    def write_xlsx(self, entries: List[GPSEntry], output_path: str):
        """Write GPS entries to XLSX file using decoder-specific format"""
        wb = Workbook()
        ws = wb.active
        ws.title = "GPS Data"
        
        # Get headers from decoder
        headers = self.current_decoder.get_xlsx_headers()
        ws.append(headers)
        
        # Write entries
        for entry in entries:
            row = self.current_decoder.format_entry_for_xlsx(entry)
            ws.append(row)
        
        wb.save(output_path)
    
    def update_progress(self, status, percent):
        self.progress_label.configure(text=status)
        self.progress['value'] = percent
        self.root.update_idletasks()
    
    def processing_complete(self, entry_count, output_path):
        self.is_processing = False
        self.process_btn.configure(state='normal', text='Process File', style='Dark.TButton')
        self.browse_btn.configure(state='normal')
        self.clear_btn.configure(state='normal', style='Dark.TButton')
        
        self.progress_label.configure(text="Processing complete!")
        self.progress['value'] = 100
        
        xlsx_filename = os.path.basename(output_path)
        result_text = f"✓ Successfully extracted {entry_count} GPS entries to:\n {xlsx_filename}"
        
        self.results_label.configure(text=result_text)
    
    def processing_error(self, error_msg):
        self.is_processing = False
        self.process_btn.configure(state='normal', text='Process File')
        self.browse_btn.configure(state='normal')
        self.clear_btn.configure(state='normal')
        
        self.progress_label.configure(text="Processing failed!")
        self.progress['value'] = 0
        self.results_label.configure(text=f"✗ Error: {error_msg}")
        
        messagebox.showerror("Processing Error", f"Failed to process file:\n\n{error_msg}")
    
    def on_file_drop(self, event):
        if self.is_processing:
            return
        file_path = event.data.strip().split()[0]
        if os.path.isfile(file_path):
            self.set_input_file(file_path)

def run_cli():
    """Run the CLI version"""
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
    
    # Get file path
    input_file = input(f"\nEnter the path to the {selected_decoder} file: ").strip()
    if not os.path.isfile(input_file):
        print(f"Error: File not found - {input_file}")
        return
    
    # Create decoder and process
    decoder_class = registry.get_decoder(selected_decoder)
    decoder = decoder_class()
    
    base, _ = os.path.splitext(input_file)
    output_file = f"{base}_{selected_decoder}.xlsx"
    
    print(f"\nProcessing {selected_decoder} file...")
    
    def progress_callback(status, percent):
        print(f"{status} ({percent}%)")
    
    entries, error = decoder.extract_gps_data(input_file, progress_callback)
    
    if error:
        print(f"Error: {error}")
    else:
        # Write XLSX
        wb = Workbook()
        ws = wb.active
        ws.title = "GPS Data"
        
        headers = decoder.get_xlsx_headers()
        ws.append(headers)
        
        for entry in entries:
            row = decoder.format_entry_for_xlsx(entry)
            ws.append(row)
        
        wb.save(output_file)
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
        pass  # Silently ignore if icon not found
    
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