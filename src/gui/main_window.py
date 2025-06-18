"""
Main Window GUI Module for FENDER

This module contains the main GUI window class and all related GUI components,
including custom widgets, dialog handling, and user interaction logic.
"""

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
import logging
from datetime import datetime
from typing import List

from src.core.base_decoder import BaseDecoder, GPSEntry
from src.utils.file_operations import (
    validate_file_path, validate_folder_path, sanitize_filename,
    write_geojson, write_kml, filter_duplicate_entries, get_resource_path
)
from src.utils.system_info import get_system_info, get_extraction_info
from src.cli.cli_interface import DecoderRegistry

# Import version from main.py
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from main import FENDER_VERSION

# Duplicate filtering precision
decimals_of_prec = 4

logger = logging.getLogger(__name__)


class CustomRadiobutton(tk.Canvas):
    """Custom radiobutton that matches the dark theme"""
    def __init__(self, parent, text, variable, value, **kwargs):
        super().__init__(parent, highlightthickness=0, **kwargs)
        logger.debug(f"Creating CustomRadiobutton: text='{text}', value='{value}'")
        
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
        logger.debug(f"CustomRadiobutton clicked: {self.text} -> {self.value}")
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


class CustomToggleButton(tk.Canvas):
    """Custom toggle button that matches the dark theme"""
    def __init__(self, parent, text, variable, **kwargs):
        super().__init__(parent, highlightthickness=0, **kwargs)
        
        self.text = text
        self.variable = variable
        self.is_on = variable.get()
        
        # Colors
        self.bg_color = '#1a1a1a'
        self.off_color = '#666666'
        self.on_color = '#4a9eff'
        self.slider_color = '#ffffff'
        self.text_color = '#cccccc'
        self.text_on_color = '#ffffff'
        
        # Dimensions
        self.toggle_width = 50
        self.toggle_height = 24
        self.slider_size = 18
        
        # Calculate total width
        text_width = len(text) * 8 + 70  # Text + toggle + padding
        canvas_width = max(150, text_width)
        
        # Configure canvas
        self.configure(bg=self.bg_color, width=canvas_width, height=30)
        
        # Bind events
        self.bind('<Button-1>', self.toggle)
        self.bind('<Enter>', self.on_enter)
        self.bind('<Leave>', self.on_leave)
        
        # Watch variable changes
        self.variable.trace('w', self.on_variable_change)
        
        # Initial draw
        self.draw()
    
    def draw(self):
        """Draw the toggle button"""
        self.delete('all')

        # Update state
        self.is_on = self.variable.get()

        # Draw toggle background as a rounded rectangle
        toggle_x = 10
        toggle_y = (30 - self.toggle_height) // 2
        r = self.toggle_height // 2  # radius for rounded ends

        x1 = toggle_x
        y1 = toggle_y
        x2 = toggle_x + self.toggle_width
        y2 = toggle_y + self.toggle_height

        fill_color = self.on_color if self.is_on else self.off_color

        # Draw left arc
        self.create_arc(x1, y1, x1 + 2*r, y2, start=90, extent=180, fill=fill_color, outline=fill_color)
        # Draw right arc
        self.create_arc(x2 - 2*r, y1, x2, y2, start=270, extent=180, fill=fill_color, outline=fill_color)
        # Draw center rectangle
        self.create_rectangle(x1 + r, y1, x2 - r, y2, fill=fill_color, outline=fill_color, width=0)

        # Draw slider
        slider_margin = 3
        if self.is_on:
            slider_x = toggle_x + self.toggle_width - self.slider_size - slider_margin
        else:
            slider_x = toggle_x + slider_margin

        slider_y = toggle_y + slider_margin

        self.create_oval(slider_x, slider_y,
                         slider_x + self.slider_size,
                         slider_y + self.slider_size,
                         fill=self.slider_color, outline='', width=0)

        # Draw text
        text_x = toggle_x + self.toggle_width + 15
        text_color = self.text_on_color if self.is_on else self.text_color
        self.create_text(text_x, 15, text=self.text, anchor='w',
                         fill=text_color, font=('Segoe UI', 10))
    
    def toggle(self, event=None):
        """Toggle the button state"""
        self.variable.set(not self.variable.get())
    
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
    """Main GUI application class for FENDER"""
    
    def __init__(self, root):
        logger.info("Initializing VehicleGPSDecoder GUI")
        self.root = root
        self.root.title(f"FENDER v{FENDER_VERSION}")
        self.root.geometry("1200x800")
        self.root.configure(bg='#1a1a1a')
        self.processing_start_time = None
        self.execution_mode = "GUI"
        self.filter_duplicates = tk.BooleanVar(value=False)
        
        logger.debug("Setting up window properties")
        
        # Initialize decoder registry
        logger.info("Initializing decoder registry")
        self.decoder_registry = DecoderRegistry()
        decoder_names = self.decoder_registry.get_decoder_names()

        # Check if decoders were found
        if not decoder_names:
            logger.critical("No decoders found during initialization")
            self.root.withdraw()
            messagebox.showerror("Initialization Error",
                                 "No decoders found.\\n\\nPlease ensure decoder files are properly included.")
            self.root.destroy()
            return

        logger.info(f"Found {len(decoder_names)} decoders: {decoder_names}")
        
        self.current_decoder = None
        self.selected_decoder_name = decoder_names[0]
        self.decoder_buttons = {}
        self.export_format = tk.StringVar(value="xlsx")  # Default to XLSX
        
        # Case information variables
        self.examiner_name = tk.StringVar()
        self.case_number = tk.StringVar()

        self.setup_styles()
        self.input_file = None
        self.is_processing = False
        self.stop_event = threading.Event()

        self.setup_ui()
        self.setup_drag_drop()
        
        logger.info("GUI initialization complete")
    
    def decoder_supports_folders(self, decoder_name: str) -> bool:
        """Check if the decoder supports folder input instead of files"""
        logger.debug(f"Checking if decoder supports folders: {decoder_name}")
    
        try:
            decoder_class = self.decoder_registry.get_decoder(decoder_name)
            decoder_instance = decoder_class()
            # Check if get_supported_extensions returns empty list (indicates folder support)
            extensions = decoder_instance.get_supported_extensions()
            supports_folders = len(extensions) == 0
            logger.debug(f"Decoder {decoder_name} supports folders: {supports_folders}")
            return supports_folders
        except Exception as e:
            logger.error(f"Error checking folder support for {decoder_name}: {e}")
            return False

    def select_decoder(self, decoder_name: str):
        """Handle decoder selection from the button list."""
        logger.info(f"Selecting decoder: {decoder_name}")
        self.selected_decoder_name = decoder_name
        
        # Update button styles
        for name, button in self.decoder_buttons.items():
            if name == decoder_name:
                button.configure(style='Selected.TButton')
                logger.debug(f"Highlighted button for: {name}")
            else:
                button.configure(style='DecoderList.TButton')
        
        # Trigger updates
        self.on_decoder_changed()

    def setup_styles(self):
        """Setup GUI styles and themes"""
        logger.debug("Setting up GUI styles")
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
        
        logger.debug("GUI styles configured")
    
    def setup_ui(self):
        """Setup main UI components"""
        logger.info("Setting up main UI components")
        
        # Main container
        main_frame = ttk.Frame(self.root, style='Dark.TFrame')
        main_frame.pack(fill='both', expand=True, padx=20, pady=20)
        
        # Left Panel for Decoder Selection
        logger.debug("Creating left panel for decoder selection")
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
        logger.debug(f"Creating buttons for {len(self.decoder_registry.get_decoder_names())} decoders")
        for decoder_name in self.decoder_registry.get_decoder_names():
            btn = ttk.Button(scrollable_frame, text=decoder_name,
                             style='DecoderList.TButton',
                             command=lambda name=decoder_name: self.select_decoder(name))
            btn.pack(fill='x', expand=True, pady=2)
            self.decoder_buttons[decoder_name] = btn
            logger.debug(f"Created button for decoder: {decoder_name}")
            
        # Right Panel for Main Content
        logger.debug("Creating right panel for main content")
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
        logger.debug("Creating export format selection")
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

        kml_radio = CustomRadiobutton(format_frame, "KML (.kml)", 
                             self.export_format, "kml",
                             bg='#1a1a1a')
        kml_radio.pack(side='left')

        # Filter controls        # Combined Case Information and Filtering Options section
        logger.debug("Creating case information and filtering fields")
        case_filter_frame = ttk.Frame(right_panel, style='Dark.TFrame')
        case_filter_frame.pack(fill='x', pady=(15, 15))

        case_label = ttk.Label(case_filter_frame, text="Case Information:",
                              background='#1a1a1a', foreground='#ffffff',
                              font=('Segoe UI', 12, 'bold'))
        case_label.pack(anchor='w', pady=(0, 5))

        # Main horizontal container for case info and filter toggle
        main_container = ttk.Frame(case_filter_frame, style='Dark.TFrame')
        main_container.pack(fill='x', pady=(0, 5))

        # Left side - Case information fields
        case_info_frame = ttk.Frame(main_container, style='Dark.TFrame')
        case_info_frame.pack(side='left', fill='y', padx=(0, 30))        # Examiner Name field
        examiner_frame = ttk.Frame(case_info_frame, style='Dark.TFrame')
        examiner_frame.pack(fill='x', pady=(0, 5))
        
        examiner_label = ttk.Label(examiner_frame, text="Examiner Name:",
                                  background='#1a1a1a', foreground='#cccccc',
                                  font=('Segoe UI', 10))
        examiner_label.pack(anchor='w')
        
        examiner_entry = ttk.Entry(examiner_frame, textvariable=self.examiner_name,
                                  font=('Segoe UI', 10), width=25)
        examiner_entry.pack(anchor='w', pady=(2, 0))        # Case Number field
        case_num_frame = ttk.Frame(case_info_frame, style='Dark.TFrame')
        case_num_frame.pack(fill='x', pady=(5, 0))
        
        case_num_label = ttk.Label(case_num_frame, text="Case Number:",
                                  background='#1a1a1a', foreground='#cccccc',
                                  font=('Segoe UI', 10))
        case_num_label.pack(anchor='w')
        
        case_num_entry = ttk.Entry(case_num_frame, textvariable=self.case_number,
                                  font=('Segoe UI', 10), width=25)
        case_num_entry.pack(anchor='w', pady=(2, 0))

        # Right side - Filtering options
        filter_frame = ttk.Frame(main_container, style='Dark.TFrame')
        filter_frame.pack(side='left', fill='both', expand=True)

        filter_label = ttk.Label(filter_frame, text="Filtering Options:",
                                background='#1a1a1a', foreground='#ffffff',
                                font=('Segoe UI', 12, 'bold'))
        filter_label.pack(anchor='w', pady=(0, 5))

        toggle_frame = ttk.Frame(filter_frame, style='Dark.TFrame')
        toggle_frame.pack(anchor='w')

        # Filter duplicates toggle
        filter_toggle = CustomToggleButton(toggle_frame, "Filter Duplicate Entries",
                                         self.filter_duplicates,
                                         bg='#1a1a1a')
        filter_toggle.pack(side='left', padx=(0, 20))

        # Info label
        info_label = ttk.Label(case_filter_frame, 
                      text=f"When enabled, filter GPS entries with identical timestamps and coordinates within {decimals_of_prec} decimal places",
                      background='#1a1a1a', foreground='#888888',
                      font=('Segoe UI', 9))
        info_label.pack(anchor='w', pady=(5, 0))

        # Drop zone
        logger.debug("Creating file drop zone")
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
        logger.debug("Creating control buttons")
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
        logger.debug("Creating progress indicators")
        progress_frame = ttk.Frame(right_panel, style='Dark.TFrame')
        progress_frame.pack(fill='x')
        self.progress_label = ttk.Label(progress_frame, text="", background='#1a1a1a', foreground='#cccccc', font=('Segoe UI', 10))
        self.progress_label.pack(anchor='w', pady=(0, 5))
        self.progress = ttk.Progressbar(progress_frame, style='Horizontal.TProgressbar', mode='determinate', length=300)
        self.progress.pack(fill='x')

        # Results section
        logger.debug("Creating results display")
        results_frame = ttk.Frame(right_panel, style='Dark.TFrame')
        results_frame.pack(fill='x', pady=(20, 0))
        self.results_label = ttk.Label(results_frame, text="", background='#1a1a1a', foreground='#4a9eff', font=('Segoe UI', 11, 'bold'))
        self.results_label.pack(anchor='w')

        # Set initial state
        self.select_decoder(self.selected_decoder_name)
        
        logger.info("UI setup complete")
    
    def setup_drag_drop(self):
        """Setup drag and drop functionality"""
        logger.debug("Setting up drag and drop functionality")
        
        # Bind click event to drop zone
        self.drop_frame.bind("<Button-1>", lambda e: self.browse_file())
        self.drop_label.bind("<Button-1>", lambda e: self.browse_file())
        
        # Enable drag-and-drop
        self.drop_frame.drop_target_register(DND_FILES)
        self.drop_frame.dnd_bind('<<Drop>>', self.on_file_drop)
        
        logger.debug("Drag and drop setup complete")

    def apply_duplicate_filter(self, entries: List[GPSEntry]) -> List[GPSEntry]:
        """Apply duplicate filtering if enabled"""
        if self.filter_duplicates.get():
            precision = decimals_of_prec
            logger.info(f"Applying duplicate filter with precision={precision}")
            return filter_duplicate_entries(entries, precision, logger)
        else:
            logger.info("Duplicate filtering is disabled")
            return entries

    def on_decoder_changed(self):
        """Handle decoder type change"""
        logger.info(f"Decoder changed to: {self.selected_decoder_name}")
        
        decoder_class = self.decoder_registry.get_decoder(self.selected_decoder_name)
        decoder_instance = decoder_class()
        dropzone_text = decoder_instance.get_dropzone_text()
        self.drop_label.configure(text=dropzone_text)
        logger.debug(f"Updated dropzone text: {dropzone_text}")

        if self.input_file:
            logger.debug("Clearing current file due to decoder change")
            self.clear_file()

        # Update browse button text based on decoder type
        if self.decoder_supports_folders(self.selected_decoder_name):
            self.browse_btn.configure(text="Browse Folders")
        else:
            self.browse_btn.configure(text="Browse Files")
    
    def browse_file(self):
        """Handle file/folder browsing"""
        logger.info("Browse dialog opened")
    
        if self.is_processing:
            logger.warning("Browse attempted while processing")
            return
    
        # Check if decoder supports folders
        if self.decoder_supports_folders(self.selected_decoder_name):
            logger.info(f"Decoder {self.selected_decoder_name} requires folder selection")
        
            folder_path = filedialog.askdirectory(
                title=f"Select {self.selected_decoder_name} Data Folder"
            )
        
            if folder_path:
                logger.info(f"Folder selected: {folder_path}")
                self.set_input_file(folder_path)
            else:
                logger.debug("Folder selection cancelled")
        else:
            # Original file selection logic
            decoder_class = self.decoder_registry.get_decoder(self.selected_decoder_name)
            decoder_instance = decoder_class()
            extensions = decoder_instance.get_supported_extensions()
            logger.debug(f"Supported extensions for {self.selected_decoder_name}: {extensions}")
        
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
                logger.info(f"File selected: {file_path}")
                # Validate file path
                is_valid, result = validate_file_path(file_path, extensions)
                if is_valid:
                    self.set_input_file(result)
                else:
                    logger.error(f"File validation failed: {result}")
                    messagebox.showerror("File Validation Error", result)
            else:
                logger.debug("File selection cancelled")
    
    def set_input_file(self, file_path):
        """Set the input file/folder path"""
        logger.info(f"Setting input path: {file_path}")
    
        self.input_file = file_path
    
        # Check if it's a folder or file
        if os.path.isdir(file_path):
            folder_name = os.path.basename(file_path)
            # Count files in folder for size estimation
            total_size = 0
            file_count = 0
            for root, dirs, files in os.walk(file_path):
                for file in files:
                    file_count += 1
                    try:
                        total_size += os.path.getsize(os.path.join(root, file))
                    except:
                        pass
        
            size_mb = total_size / (1024 * 1024)
            logger.debug(f"Folder details - Name: {folder_name}, Files: {file_count}, Total size: {size_mb:.2f} MB")
        
            self.drop_label.configure(text=f"Selected Folder: {folder_name}")
            self.file_info_label.configure(text=f"Contains {file_count} files, Total size: {size_mb:.2f} MB")
        else:
            filename = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)
            size_mb = file_size / (1024 * 1024)
        
            logger.debug(f"File details - Name: {filename}, Size: {size_mb:.2f} MB")
        
            self.drop_label.configure(text=f"Selected: {filename}")
            self.file_info_label.configure(text=f"Size: {size_mb:.2f} MB")
    
        self.process_btn.configure(state='normal', style='Dark.TButton')
        self.clear_btn.configure(state='normal', style='Dark.TButton')
    
        logger.info("Input path set successfully")
    
    def clear_file(self):
        """Clear the current file selection"""
        logger.info("Clearing current file")
        
        if self.is_processing:
            logger.warning("Clear attempted while processing")
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
        
        logger.info("File cleared")
    
    def generate_timestamped_filename(self, base_path: str, decoder_name: str, format_ext: str) -> str:
        """Generate filename with timestamp"""
        base, _ = os.path.splitext(base_path)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_decoder_name = sanitize_filename(decoder_name)
        filename = f"{base}_{safe_decoder_name}_{timestamp}.{format_ext}"
        
        logger.debug(f"Generated timestamped filename: {filename}")
        return filename
    
    def process_file(self):
        """Start the file processing"""
        logger.info("Starting file processing")
        
        if not self.input_file or self.is_processing:
            logger.warning("Process attempted with no file or already processing")
            return
    
        self.stop_event.clear()
        
        self.processing_start_time = datetime.now()
        logger.debug(f"Processing start time: {self.processing_start_time}")
        
        self.is_processing = True
        self.process_btn.configure(state='disabled', text='Processing...')
        self.browse_btn.configure(state='disabled')
        self.clear_btn.configure(state='disabled')
        self.stop_btn.configure(state='normal', style='Dark.TButton')
    
        # Get decoder
        decoder_class = self.decoder_registry.get_decoder(self.selected_decoder_name)
        self.current_decoder = decoder_class()
        logger.info(f"Using decoder: {self.selected_decoder_name}")
    
        # Generate output path with timestamp and selected format
        format_ext = self.export_format.get()
        output_path = self.generate_timestamped_filename(self.input_file, self.selected_decoder_name, format_ext)
        logger.info(f"Output will be saved to: {output_path}")
    
        # Start processing in a separate thread
        thread = threading.Thread(target=self.process_in_background_with_filter,
            args=(self.input_file, output_path))
        thread.daemon = True
        thread.start()
        logger.debug("Started processing thread")

    def process_in_background_with_filter(self, input_path, output_path):
        """Modified version of process_in_background that includes filtering"""
        logger.info(f"Background processing started for: {input_path}")
    
        def progress_callback(status, percent):
            logger.debug(f"Progress update: {status} ({percent}%)")
            self.root.after(0, self.update_progress, status, percent)

        try:
            # Pass stop_event to decoder
            logger.info("Calling decoder extract_gps_data method")
            entries, error = self.current_decoder.extract_gps_data(
                input_path, progress_callback, stop_event=self.stop_event
            )
        
            if error:
                logger.error(f"Decoder returned error: {error}")
                self.root.after(0, self.processing_error, error)
            else:
                logger.info(f"Decoder extracted {len(entries)} entries")
            
                # Apply duplicate filter if enabled
                filtered_entries = self.apply_duplicate_filter(entries)
            
                # Update progress if filtering was applied
                if len(filtered_entries) < len(entries):
                    self.root.after(0, self.update_progress, 
                                   f"Filtered {len(entries) - len(filtered_entries)} duplicates...", 80)
            
                # Write to selected format
                format_type = self.export_format.get()
                logger.info(f"Writing output in {format_type} format")
                self.root.after(0, self.update_progress, f"Writing {format_type.upper()} file...", 85)
            
                if format_type == "xlsx":
                    self.write_xlsx(filtered_entries, output_path)
                elif format_type == "csv":
                    self.write_csv(filtered_entries, output_path)
                elif format_type == "json":
                    self.write_json(filtered_entries, output_path)
                elif format_type == "geojson":
                    # Get case information and system info for GeoJSON
                    examiner_name = self.examiner_name.get().strip() if self.examiner_name.get().strip() else None
                    case_number = self.case_number.get().strip() if self.case_number.get().strip() else None
                    
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
                        len(filtered_entries),
                        processing_time
                    )
                    
                    from src.utils.file_operations import write_geojson_report, log_report_hash
                    write_geojson_report(filtered_entries, output_path, self.selected_decoder_name, 
                                       system_info, extraction_info, examiner_name, case_number)
                    log_report_hash(output_path, logger)
                elif format_type == "kml":
                    write_kml(filtered_entries, output_path, self.selected_decoder_name)
                    from src.utils.file_operations import log_report_hash
                    log_report_hash(output_path, logger)
            
                # Report both original and filtered counts if filtering was applied
                if self.filter_duplicates.get() and len(filtered_entries) < len(entries):
                    result_info = {
                        'original_count': len(entries),
                        'filtered_count': len(filtered_entries),
                        'duplicates_removed': len(entries) - len(filtered_entries)
                    }
                    self.root.after(0, self.processing_complete_with_filter_info, 
                                  result_info, output_path)
                else:
                    self.root.after(0, self.processing_complete, len(filtered_entries), output_path)
                
        except Exception as e:
            logger.error(f"Exception during background processing: {e}", exc_info=True)
            self.root.after(0, self.processing_error, str(e))

    def processing_complete_with_filter_info(self, result_info, output_path):
        """Modified processing complete handler that shows filtering information"""
        logger.info(f"Processing completed with filtering. Original: {result_info['original_count']}, "
                    f"Filtered: {result_info['filtered_count']}, Output: {output_path}")
    
        self.is_processing = False
        self.process_btn.configure(state='normal', text='Process File', style='Dark.TButton')
        self.browse_btn.configure(state='normal')
        self.clear_btn.configure(state='normal', style='Dark.TButton')
        self.stop_btn.configure(state='disabled', style='Disabled.TButton')
    
        self.progress_label.configure(text="Processing complete!")
        self.progress['value'] = 100
    
        output_filename = os.path.basename(output_path)
        format_type = self.export_format.get().upper()
    
        result_text = (f"Successfully extracted {result_info['filtered_count']} GPS entries to {format_type}:\\n"
                       f" {output_filename}\\n"
                       f" ({result_info['duplicates_removed']} duplicates removed from {result_info['original_count']} total entries)")
    
        self.results_label.configure(text=result_text)
    
        processing_time = (datetime.now() - self.processing_start_time).total_seconds() if self.processing_start_time else 0
        logger.info(f"Total processing time: {processing_time:.2f} seconds")

    def write_xlsx(self, entries: List[GPSEntry], output_path: str):
        """Write GPS entries to XLSX file using updated file_operations function"""
        logger.info(f"Writing {len(entries)} entries to XLSX file: {output_path}")
        
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
        
        # Get case information
        examiner_name = self.examiner_name.get().strip() if self.examiner_name.get().strip() else None
        case_number = self.case_number.get().strip() if self.case_number.get().strip() else None
        
        # Use the updated file_operations function
        from src.utils.file_operations import write_excel_report, log_report_hash
        write_excel_report(entries, output_path, self.selected_decoder_name, 
                          system_info, extraction_info, self.current_decoder, 
                          examiner_name, case_number)
        
        # Log the SHA256 hash of the generated report
        logger.info("About to calculate and log SHA256 hash of Excel report")
        try:
            hash_result = log_report_hash(output_path, logger)
            logger.info(f"Excel report hash logging completed, result: {hash_result}")
        except Exception as e:
            logger.error(f"Error during Excel report hash logging: {e}", exc_info=True)

    def write_csv(self, entries: List[GPSEntry], output_path: str):
        """Write GPS entries to CSV file using updated file_operations function"""
        logger.info(f"Writing {len(entries)} entries to CSV file: {output_path}")
        
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
        
        # Get case information
        examiner_name = self.examiner_name.get().strip() if self.examiner_name.get().strip() else None
        case_number = self.case_number.get().strip() if self.case_number.get().strip() else None
        
        # Use the updated file_operations function
        from src.utils.file_operations import write_csv_report, log_report_hash
        write_csv_report(entries, output_path, self.selected_decoder_name, 
                        system_info, extraction_info, self.current_decoder, 
                        examiner_name, case_number)
        
        # Log the SHA256 hash of the generated report
        logger.info("About to calculate and log SHA256 hash of CSV report")
        try:
            hash_result = log_report_hash(output_path, logger)
            logger.info(f"CSV report hash logging completed, result: {hash_result}")
        except Exception as e:
            logger.error(f"Error during CSV report hash logging: {e}", exc_info=True)

    def write_json(self, entries: List[GPSEntry], output_path: str):
        """Write GPS entries to JSON file using updated file_operations function"""
        logger.info(f"Writing {len(entries)} entries to JSON file: {output_path}")
        
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
        
        # Get case information
        examiner_name = self.examiner_name.get().strip() if self.examiner_name.get().strip() else None
        case_number = self.case_number.get().strip() if self.case_number.get().strip() else None
        
        # Use the updated file_operations function
        from src.utils.file_operations import write_json_report, log_report_hash
        write_json_report(entries, output_path, self.selected_decoder_name, 
                         system_info, extraction_info, self.current_decoder, 
                         examiner_name, case_number)
        
        # Log the SHA256 hash of the generated report
        logger.info("About to calculate and log SHA256 hash of JSON report")
        try:
            hash_result = log_report_hash(output_path, logger)
            logger.info(f"JSON report hash logging completed, result: {hash_result}")
        except Exception as e:
            logger.error(f"Error during JSON report hash logging: {e}", exc_info=True)
    
    def update_progress(self, status, percent):
        """Update progress display"""
        logger.debug(f"UI progress update: {status} ({percent}%)")
        self.progress_label.configure(text=status)
        self.progress['value'] = percent
        self.root.update_idletasks()
    
    def processing_complete(self, entry_count, output_path):
        """Handle processing completion"""
        logger.info(f"Processing completed successfully. Entries: {entry_count}, Output: {output_path}")
        
        self.is_processing = False
        self.process_btn.configure(state='normal', text='Process File', style='Dark.TButton')
        self.browse_btn.configure(state='normal')
        self.clear_btn.configure(state='normal', style='Dark.TButton')
        self.stop_btn.configure(state='disabled', style='Disabled.TButton')
        
        self.progress_label.configure(text="Processing complete!")
        self.progress['value'] = 100
        
        output_filename = os.path.basename(output_path)
        format_type = self.export_format.get().upper()
        result_text = f"Successfully extracted {entry_count} GPS entries to {format_type}:\\n {output_filename}"
        
        self.results_label.configure(text=result_text)
        
        processing_time = (datetime.now() - self.processing_start_time).total_seconds() if self.processing_start_time else 0
        logger.info(f"Total processing time: {processing_time:.2f} seconds")
    
    def processing_error(self, error_msg):
        """Handle processing errors"""
        logger.error(f"Processing failed with error: {error_msg}")
        
        self.is_processing = False
        self.process_btn.configure(state='normal', text='Process File')
        self.browse_btn.configure(state='normal')
        self.clear_btn.configure(state='normal')
        self.stop_btn.configure(state='disabled', style='Disabled.TButton')
        
        self.progress_label.configure(text="Processing failed!")
        self.progress['value'] = 0
        self.results_label.configure(text=f"Error: {error_msg}")
        
        messagebox.showerror("Processing Error", f"Failed to process file:\\n\\n{error_msg}")
    
    def stop_processing(self):
        """Stop the current processing"""
        logger.info("Stop processing requested by user")
        
        if self.is_processing:
            self.stop_event.set()
            self.progress_label.configure(text="Stopping...")
            self.stop_btn.configure(state='disabled', style='Disabled.TButton')
            logger.debug("Stop event set")
    
    def on_file_drop(self, event):
        """Handle file drop events"""
        logger.info("Item dropped onto drop zone")
    
        if self.is_processing:
            logger.warning("Drop ignored - currently processing")
            return
        
        dropped_path = event.data.strip().strip('{}')  # Handle paths with spaces
        logger.debug(f"Dropped path: {dropped_path}")
    
        # Check if decoder supports folders
        if self.decoder_supports_folders(self.selected_decoder_name):
            if os.path.isdir(dropped_path):
                # Validate dropped folder
                is_valid, result = validate_folder_path(dropped_path)
                if is_valid:
                    self.set_input_file(result)
                else:
                    logger.error(f"Dropped folder validation failed: {result}")
                    messagebox.showerror("Folder Validation Error", result)
            else:
                logger.warning(f"Decoder {self.selected_decoder_name} requires a folder, not a file")
                messagebox.showwarning("Invalid Input", 
                                     f"{self.selected_decoder_name} decoder requires a folder, not a file.")
        else:
            if os.path.isfile(dropped_path):
                # Original file validation logic
                decoder_class = self.decoder_registry.get_decoder(self.selected_decoder_name)
                decoder_instance = decoder_class()
                extensions = decoder_instance.get_supported_extensions()
            
                is_valid, result = validate_file_path(dropped_path, extensions)
                if is_valid:
                    self.set_input_file(result)
                else:
                    logger.error(f"Dropped file validation failed: {result}")
                    messagebox.showerror("File Validation Error", result)
            else:
                logger.warning(f"Dropped item is not a file: {dropped_path}")
                messagebox.showwarning("Invalid Input", 
                                     f"{self.selected_decoder_name} decoder requires a file, not a folder.")


def run_gui():
    """Run the GUI version"""
    logger.info("Starting FENDER in GUI mode")
    
    root = TkinterDnD.Tk()
    
    # Set icon
    try:
        icon_path = get_resource_path("car.ico")
        if os.path.exists(icon_path):
            root.iconbitmap(icon_path)
            logger.debug(f"Application icon set from: {icon_path}")
    except tk.TclError as e:
        logger.warning(f"Failed to set application icon: {e}")
    
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
    
    logger.info(f"GUI window centered at position: {position_x}, {position_y}")
    logger.info("Starting GUI main loop")
    
    root.mainloop()
    
    logger.info("GUI closed by user")
