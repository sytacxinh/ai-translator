"""
Main Application for AI Translator.
"""
import os
import sys
import time
import queue
import logging
import threading
import webbrowser
from typing import Dict, Tuple

import pyperclip
from pystray import Icon, MenuItem, Menu
from PIL import Image, ImageDraw

import tkinter as tk
from tkinter import BOTH, X, LEFT, RIGHT, END, BOTTOM, TOP
from tkinter import font

try:
    import ttkbootstrap as ttk
    from ttkbootstrap.dialogs import Messagebox
    HAS_TTKBOOTSTRAP = True
except ImportError:
    from tkinter import ttk
    HAS_TTKBOOTSTRAP = False

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    HAS_DND = True
except ImportError:
    HAS_DND = False
    DND_FILES = None

# windnd for Windows drag-and-drop (works better with Toplevel)
try:
    import windnd
    HAS_WINDND = True
except ImportError:
    HAS_WINDND = False

from config import Config
from src.constants import VERSION, LANGUAGES
from src.core.translation import TranslationService
from src.core.api_manager import AIAPIManager
from src.core.hotkey import HotkeyManager
from src.ui.settings import SettingsWindow
from src.ui.dialogs import APIErrorDialog
from src.ui.history_dialog import HistoryDialog
from src.ui.toast import ToastManager, ToastType
from src.utils.updates import check_for_updates
from src.core.screenshot import ScreenshotCapture
from src.core.file_processor import FileProcessor
from src.ui.attachments import AttachmentArea
from src.core.multimodal import MultimodalProcessor


class TranslatorApp:
    """Main application class."""

    def __init__(self):
        # Initialize configuration
        self.config = Config()

        # Log DnD library availability
        logging.info(f"DnD libraries: tkinterdnd2={HAS_DND}, windnd={HAS_WINDND}")

        # Create root window
        if HAS_TTKBOOTSTRAP:
            # If DND is available, we need to use TkinterDnD.Tk
            # ttkbootstrap.Window inherits from tk.Tk, so we can't easily mix them inheritance-wise
            # But we can use TkinterDnD.Tk and apply style manually
            if HAS_DND:
                self.root = TkinterDnD.Tk()
                self.style = ttk.Style(theme="darkly")
            else:
                self.root = ttk.Window(themename="darkly")
        else:
            self.root = TkinterDnD.Tk() if HAS_DND else tk.Tk()
        self.root.withdraw()

        # Handle root window close
        self.root.protocol("WM_DELETE_WINDOW", self.quit_app)

        # Initialize services
        self.translation_service = TranslationService(self.config)
        self.hotkey_manager = HotkeyManager(self.config, self._on_hotkey_translate)
        self.screenshot_capture = ScreenshotCapture(self.root)
        self.file_processor = FileProcessor(self.translation_service.api_manager)

        # UI state
        self.popup = None
        self.tooltip = None
        self.tray_icon = None
        self.running = True
        self.selected_language = "Vietnamese"
        self.filtered_languages = LANGUAGES.copy()

        # Current translation data
        self.current_original = ""
        self.current_translated = ""
        self.current_target_lang = ""
        self.settings_window = None

        # Dragging state
        self._drag_x = 0
        self._drag_y = 0
        self._last_mouse_x = 0
        self._last_mouse_y = 0

        # Thread-safe queue for windnd file drops (avoids GIL issues)
        self._drop_queue = queue.Queue()

        # Toast notification manager
        self.toast = ToastManager(self.root)

    def _on_hotkey_translate(self, language: str):
        """Handle hotkey translation request."""
        # Capture mouse position immediately when hotkey is pressed
        self._last_mouse_x = self.root.winfo_pointerx()
        self._last_mouse_y = self.root.winfo_pointery()
        
        if language == "Screenshot":
            self.root.after(0, self._start_screenshot_ocr)
            return

        self.root.after(0, lambda: self.show_loading_tooltip(language))
        self.translation_service.do_translation(language)

    def show_loading_tooltip(self, target_lang: str):
        """Show loading indicator."""
        if self.tooltip:
            try:
                self.tooltip.destroy()
            except tk.TclError:
                pass  # Tooltip already destroyed

        self.tooltip = tk.Toplevel(self.root)
        self.tooltip.overrideredirect(True)
        self.tooltip.configure(bg='#2b2b2b')
        self.tooltip.attributes('-topmost', True)

        frame = ttk.Frame(self.tooltip, padding=10)
        frame.pack(fill=BOTH, expand=True)

        ttk.Label(frame, text=f"⏳ Translating to {target_lang}...",
                 font=('Segoe UI', 10), foreground='#ffffff', background='#2b2b2b').pack()

        mouse_x = self._last_mouse_x
        mouse_y = self._last_mouse_y
        self.tooltip.geometry(f"+{mouse_x + 15}+{mouse_y + 20}")

    def calculate_tooltip_size(self, text: str) -> Tuple[int, int]:
        """Calculate optimal tooltip dimensions based on text content using font measurement."""
        MAX_WIDTH = 800
        MAX_HEIGHT = self.root.winfo_screenheight() - 80
        MIN_WIDTH = 320
        MIN_HEIGHT = 120
        
        # Padding configuration
        FRAME_PADDING = 30  # Total horizontal padding (15px * 2)
        TEXT_MARGIN = 10    # Extra margin for scrollbar/safety
        VERTICAL_PADDING = 100 # Increased: Header (20) + Footer (50) + Padding (30)
        
        # Create font object to measure text accurately
        try:
            ui_font = font.Font(family='Segoe UI', size=11)
        except tk.TclError:
            # Fallback if font creation fails
            ui_font = font.Font(family='Arial', size=11)
            
        line_height = ui_font.metrics("linespace") + 2 # +2px for line spacing

        # 1. Calculate Optimal Width
        # Measure the longest line to determine ideal width
        longest_line_width = 0
        for line in text.split('\n'):
            w = ui_font.measure(line)
            if w > longest_line_width:
                longest_line_width = w
        
        # Determine width: clamp between MIN and MAX
        # Add padding to text width to get window width
        ideal_width = longest_line_width + FRAME_PADDING + TEXT_MARGIN
        width = max(MIN_WIDTH, min(ideal_width, MAX_WIDTH))

        # 2. Calculate Height (Simulate Word Wrapping)
        available_text_width = width - FRAME_PADDING - TEXT_MARGIN
        
        total_lines = 0
        for paragraph in text.split('\n'):
            # Empty lines count as 1
            if not paragraph:
                total_lines += 1
                continue
                
            # Fast path: if paragraph fits in one line
            if ui_font.measure(paragraph) <= available_text_width:
                total_lines += 1
                continue
            
            # Slow path: simulate word wrapping
            current_line_width = 0
            lines_in_para = 1
            words = paragraph.split(' ')
            space_width = ui_font.measure(' ')
            
            for word in words:
                word_width = ui_font.measure(word)
                
                # Check if word fits on current line
                if current_line_width + word_width <= available_text_width:
                    current_line_width += word_width + space_width
                else:
                    # Word doesn't fit, wrap to next line
                    lines_in_para += 1
                    
                    # Handle case where a single word is wider than the box
                    if word_width > available_text_width:
                        # It will wrap multiple times
                        # Approximate extra lines for this huge word
                        extra_lines = int(word_width / available_text_width)
                        lines_in_para += extra_lines
                        current_line_width = word_width % available_text_width
                    else:
                        current_line_width = word_width + space_width
            
            total_lines += lines_in_para
        
        # Calculate final height
        height = (total_lines * line_height) + VERTICAL_PADDING

        return int(width), int(max(height, MIN_HEIGHT))

    def show_tooltip(self, original: str, translated: str, target_lang: str):
        """Show compact tooltip near mouse cursor with translation result."""
        self.current_original = original
        self.current_translated = translated
        self.current_target_lang = target_lang

        # Close existing tooltip
        if self.tooltip:
            try:
                self.tooltip.destroy()
            except tk.TclError:
                pass  # Tooltip already destroyed

        # Check if this is an error message
        is_error = translated.startswith("Error:") or translated.startswith("No text")

        # Calculate size
        width, height = self.calculate_tooltip_size(translated)
        if is_error:
            height = max(height, 120)  # Ensure error messages have enough space

        # Create tooltip window
        self.tooltip = tk.Toplevel(self.root)
        self.tooltip.overrideredirect(True)

        # Handle close properly
        def on_tooltip_close():
            self.close_tooltip()

        self.tooltip.protocol("WM_DELETE_WINDOW", on_tooltip_close)

        # Color based on error status
        if is_error:
            self.tooltip.configure(bg='#3d1f1f')  # Dark red background for errors
        else:
            self.tooltip.configure(bg='#2b2b2b')

        # Set topmost initially, then remove so it can go behind other windows
        self.tooltip.attributes('-topmost', True)
        self.tooltip.after(100, lambda: self.tooltip.attributes('-topmost', False) if self.tooltip else None)

        # Main frame
        main_frame = ttk.Frame(self.tooltip, padding=15)
        main_frame.pack(fill=BOTH, expand=True)

        # Bind dragging events to the main frame
        main_frame.bind("<Button-1>", self._start_move)
        main_frame.bind("<B1-Motion>", self._on_drag)

        # Button frame (Create FIRST to ensure it stays at BOTTOM)
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(side=BOTTOM, fill=X, pady=(12, 0))

        # Bind dragging events to the button frame
        btn_frame.bind("<Button-1>", self._start_move)
        btn_frame.bind("<B1-Motion>", self._on_drag)

        if not is_error:
            # Copy button (only show for success)
            copy_btn_kwargs = {"text": "Copy", "command": self.copy_from_tooltip, "width": 8}
            if HAS_TTKBOOTSTRAP:
                copy_btn_kwargs["bootstyle"] = "primary"
            self.tooltip_copy_btn = ttk.Button(btn_frame, **copy_btn_kwargs)
            self.tooltip_copy_btn.pack(side=LEFT)

            # Open Translator button (only show for success)
            open_btn_kwargs = {"text": "Open Translator", "command": self.open_full_translator, "width": 14}
            if HAS_TTKBOOTSTRAP:
                open_btn_kwargs["bootstyle"] = "success"
            ttk.Button(btn_frame, **open_btn_kwargs).pack(side=LEFT, padx=8)
        else:
            # For errors, show "Open Settings" button
            settings_btn_kwargs = {"text": "Open Settings", "command": self._open_settings_from_error, "width": 14}
            if HAS_TTKBOOTSTRAP:
                settings_btn_kwargs["bootstyle"] = "warning"
            ttk.Button(btn_frame, **settings_btn_kwargs).pack(side=LEFT, padx=8)

        # Close button
        close_btn_kwargs = {"text": "✕", "command": self.close_tooltip, "width": 3}
        if HAS_TTKBOOTSTRAP:
            close_btn_kwargs["bootstyle"] = "secondary"
        ttk.Button(btn_frame, **close_btn_kwargs).pack(side=RIGHT)

        # Translation text with color for errors
        text_height = max(1, (height - 80) // 26)
        text_fg = '#ff6b6b' if is_error else '#ffffff'  # Light red for errors

        self.tooltip_text = tk.Text(main_frame, wrap=tk.WORD,
                                    bg='#3d1f1f' if is_error else '#2b2b2b',
                                    fg=text_fg,
                                    font=('Segoe UI', 11), relief='flat',
                                    width=width // 9, height=text_height,
                                    borderwidth=0, highlightthickness=0)
        self.tooltip_text.insert('1.0', translated)
        self.tooltip_text.config(state='disabled') # Read-only but selectable
        self.tooltip_text.pack(side=TOP, fill=BOTH, expand=True)

        # Mouse wheel scroll
        self.tooltip_text.bind('<MouseWheel>',
            lambda e: self.tooltip_text.yview_scroll(int(-1*(e.delta/120)), "units"))

        # Position near mouse
        # Use captured position from when hotkey was pressed
        mouse_x = self._last_mouse_x
        mouse_y = self._last_mouse_y
        
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        taskbar_margin = 50  # Space for taskbar

        # 1. Calculate X (Horizontal)
        x = mouse_x + 15
        if x + width > screen_width - 10:
            x = mouse_x - width - 15
        x = max(10, min(x, screen_width - width - 10))

        # 2. Calculate Y (Vertical) and Adjust Height
        # Default preference: Below the mouse
        y = mouse_y + 20
        
        # Calculate safe area
        safe_top = 10
        safe_bottom = screen_height - taskbar_margin
        max_safe_height = safe_bottom - safe_top
        
        # Case 1: Content is taller than the entire safe screen area
        if height >= max_safe_height:
            height = max_safe_height
            y = safe_top
        
        # Case 2: Content fits on screen, but need to decide position relative to mouse
        else:
            space_below = safe_bottom - y
            
            if height <= space_below:
                # Fits below perfectly
                pass 
            else:
                # Try above
                y_above = mouse_y - height - 20
                if y_above >= safe_top:
                    y = y_above
                else:
                    # Doesn't fit cleanly above or below -> Pin to bottom safe edge
                    y = safe_bottom - height
                    # Double check top edge
                    if y < safe_top:
                        y = safe_top
                        height = max_safe_height

        self.tooltip.geometry(f"{width}x{height}+{int(x)}+{int(y)}")

        # Bindings
        self.tooltip.bind('<Escape>', lambda e: on_tooltip_close())

    def _start_move(self, event):
        """Record start position for dragging using screen coordinates."""
        self._drag_x = event.x_root
        self._drag_y = event.y_root

    def _on_drag(self, event):
        """Handle dragging of the tooltip using screen coordinates."""
        if not self.tooltip:
            return

        # Calculate delta using screen coordinates (x_root, y_root)
        deltax = event.x_root - self._drag_x
        deltay = event.y_root - self._drag_y

        # Update reference point
        self._drag_x = event.x_root
        self._drag_y = event.y_root

        # Move window
        x = self.tooltip.winfo_x() + deltax
        y = self.tooltip.winfo_y() + deltay
        self.tooltip.geometry(f"+{x}+{y}")

    def _on_tooltip_focus_out(self, event):
        """Handle tooltip losing focus."""
        if self.tooltip:
            # Immediately close instead of using after()
            self.close_tooltip()

    def close_tooltip(self):
        """Close the tooltip."""
        if self.tooltip:
            try:
                if self.tooltip.winfo_exists():
                    self.tooltip.destroy()
            except tk.TclError:
                pass  # Window already destroyed
            self.tooltip = None

    def copy_from_tooltip(self):
        """Copy translation from tooltip to clipboard."""
        pyperclip.copy(self.current_translated)
        self.tooltip_copy_btn.configure(text="Copied!")
        self.toast.show_success("Copied to clipboard!")
        if self.tooltip:
            self.tooltip.after(1000, lambda: self._reset_copy_btn())

    def _reset_copy_btn(self):
        """Reset copy button text."""
        if self.tooltip and self.tooltip_copy_btn:
            try:
                self.tooltip_copy_btn.configure(text="Copy")
            except tk.TclError:
                pass  # Widget destroyed

    def open_full_translator(self):
        """Close tooltip and open full translator window."""
        self.close_tooltip()
        self.show_popup(self.current_original, self.current_translated, self.current_target_lang)

    def show_main_window(self, icon=None, item=None):
        """Show main translator window from tray."""
        # Ensure runs on main thread
        if threading.current_thread() is not threading.main_thread():
            self.root.after(0, lambda: self.show_main_window(icon, item))
            return

        # If popup already exists, bring it to front instead of creating new one
        if self.popup:
            try:
                if self.popup.winfo_exists():
                    # Restore from minimized/iconified state
                    self.popup.deiconify()
                    # Force window to top using topmost trick
                    self.popup.attributes('-topmost', True)
                    self.popup.update()
                    self.popup.attributes('-topmost', False)
                    # Additional methods to ensure focus
                    self.popup.lift()
                    self.popup.focus_force()
                    return
            except tk.TclError:
                pass  # Window was destroyed, create new one

        # Prevent double-calling by checking if popup is being shown
        if hasattr(self, '_showing_popup') and self._showing_popup:
            return
        self._showing_popup = True
        try:
            self.show_popup("", "", self.selected_language)
        finally:
            # Reset after a short delay
            self.root.after(500, lambda: setattr(self, '_showing_popup', False))

    def show_popup(self, original: str, translated: str, target_lang: str, force_new: bool = False):
        """Show the full translator popup window.

        Args:
            original: Original text to display
            translated: Translated text to display
            target_lang: Target language
            force_new: If False and popup exists with content, just bring to front
        """
        # If popup exists with content and we're not forcing new, just bring it to front
        if not force_new and self.popup:
            try:
                if self.popup.winfo_exists():
                    # Check if there's existing content we shouldn't destroy
                    has_content = False
                    if hasattr(self, 'original_text') and self.original_text:
                        try:
                            existing_text = self.original_text.get('1.0', 'end-1c').strip()
                            has_content = bool(existing_text)
                        except:
                            pass
                    if hasattr(self, 'attachment_area') and self.attachment_area:
                        try:
                            has_content = has_content or len(self.attachment_area.get_attachments()) > 0
                        except:
                            pass

                    # If popup has content and we're just opening (empty params), bring to front
                    if has_content and not original and not translated:
                        self.popup.deiconify()
                        self.popup.attributes('-topmost', True)
                        self.popup.update()
                        self.popup.attributes('-topmost', False)
                        self.popup.lift()
                        self.popup.focus_force()
                        return
            except tk.TclError:
                pass

        # Destroy existing popup if present
        if self.popup:
            try:
                self.popup.destroy()
            except tk.TclError:
                pass  # Window already destroyed
            self.popup = None

        # Use tk.Toplevel for better compatibility
        self.popup = tk.Toplevel(self.root)
        self.popup.title("AI Translator")
        self.popup.configure(bg='#2b2b2b')

        # Focus handlers for topmost behavior
        def on_popup_focus_in(e):
            self.popup.attributes('-topmost', True)
            self.popup.after(100, lambda: self.popup.attributes('-topmost', False) if self.popup else None)

        self.popup.bind('<FocusIn>', on_popup_focus_in)

        # Handle close button properly
        def on_popup_close():
            try:
                if self.popup and self.popup.winfo_exists():
                    self.popup.destroy()
            except tk.TclError:
                pass  # Window already destroyed
            self.popup = None

        self.popup.protocol("WM_DELETE_WINDOW", on_popup_close)
        self.popup.bind('<Escape>', lambda e: on_popup_close())

        # Window size and position
        screen_width = self.popup.winfo_screenwidth()
        screen_height = self.popup.winfo_screenheight()
        window_width = 1400
        window_height = 850
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        self.popup.geometry(f"{window_width}x{window_height}+{x}+{y}")

        if HAS_TTKBOOTSTRAP:
            main_frame = ttk.Frame(self.popup, padding=20)
        else:
            main_frame = ttk.Frame(self.popup)
        main_frame.pack(fill=BOTH, expand=True, padx=20, pady=20)

        # ===== BUTTONS (Pack FIRST with side=BOTTOM to ensure always visible) =====
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(side=BOTTOM, fill=X, pady=(15, 0))

        # Define on_popup_close reference for buttons
        def on_popup_close_btn():
            try:
                if self.popup and self.popup.winfo_exists():
                    self.popup.destroy()
            except tk.TclError:
                pass  # Window already destroyed
            self.popup = None

        # Translate button
        if HAS_TTKBOOTSTRAP:
            self.translate_btn = ttk.Button(btn_frame,
                                            text=f"Translate → {self.selected_language}",
                                            command=self._do_retranslate,
                                            bootstyle="success", width=25)
        else:
            self.translate_btn = ttk.Button(btn_frame,
                                            text=f"Translate → {self.selected_language}",
                                            command=self._do_retranslate, width=25)
        self.translate_btn.pack(side=LEFT)

        # Copy button
        if HAS_TTKBOOTSTRAP:
            self.copy_btn = ttk.Button(btn_frame, text="Copy",
                                       command=self._copy_translation,
                                       bootstyle="primary", width=12)
        else:
            self.copy_btn = ttk.Button(btn_frame, text="Copy",
                                       command=self._copy_translation, width=12)
        self.copy_btn.pack(side=LEFT, padx=10)

        # Open Gemini button
        if HAS_TTKBOOTSTRAP:
            self.gemini_btn = ttk.Button(btn_frame, text="✦ Open Gemini",
                                         command=self._open_in_gemini,
                                         bootstyle="info", width=15)
        else:
            self.gemini_btn = ttk.Button(btn_frame, text="✦ Open Gemini",
                                         command=self._open_in_gemini, width=15)
        self.gemini_btn.pack(side=LEFT)

        # Screenshot button (if vision enabled)
        if self.config.get('vision_enabled', False):
            if HAS_TTKBOOTSTRAP:
                ttk.Button(btn_frame, text="📷 Screenshot", command=self._start_screenshot_ocr,
                           bootstyle="warning-outline", width=12).pack(side=LEFT, padx=10)
            else:
                ttk.Button(btn_frame, text="📷 Screenshot", command=self._start_screenshot_ocr,
                           width=12).pack(side=LEFT, padx=10)

        # History button
        if HAS_TTKBOOTSTRAP:
            ttk.Button(btn_frame, text="History", command=self._open_history,
                       bootstyle="light-outline", width=10).pack(side=LEFT, padx=10)
        else:
            ttk.Button(btn_frame, text="History", command=self._open_history,
                       width=10).pack(side=LEFT, padx=10)

        # Close button
        if HAS_TTKBOOTSTRAP:
            ttk.Button(btn_frame, text="Close", command=on_popup_close_btn,
                       bootstyle="secondary", width=12).pack(side=RIGHT)
        else:
            ttk.Button(btn_frame, text="Close", command=on_popup_close_btn,
                       width=12).pack(side=RIGHT)

        # ===== CONTENT FRAME (Pack after buttons to fill remaining space) =====
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(side=TOP, fill=BOTH, expand=True)

        # ===== ATTACHMENT AREA =====
        # Only show if features are enabled
        vision_enabled = self.config.get('vision_enabled', False)
        file_enabled = self.config.get('file_processing_enabled', False)

        if vision_enabled or file_enabled:
            try:
                # Ensure popup window is fully realized before creating DnD widgets
                self.popup.update_idletasks()
                self.attachment_area = AttachmentArea(content_frame, self.config, on_change=None)
                self.attachment_area.pack(fill=X, pady=(0, 10))
            except Exception as e:
                logging.error(f"Error initializing AttachmentArea: {e}")
                self.attachment_area = None
        else:
            self.attachment_area = None

        # ===== ORIGINAL TEXT =====
        ttk.Label(content_frame, text="Original:", font=('Segoe UI', 10)).pack(anchor='w')

        self.original_text = tk.Text(content_frame, height=6, wrap=tk.WORD,
                                     bg='#2b2b2b', fg='#cccccc',
                                     font=('Segoe UI', 11), relief='flat',
                                     padx=10, pady=10, insertbackground='white',
                                     undo=True, maxundo=-1)
        self.original_text.insert('1.0', original)
        self.original_text.pack(fill=X, pady=(5, 15))
        self.original_text.bind('<MouseWheel>',
            lambda e: self.original_text.yview_scroll(int(-1*(e.delta/120)), "units"))

        # Undo/Redo bindings
        self.original_text.bind('<Control-z>', lambda e: self.original_text.edit_undo() or "break")
        self.original_text.bind('<Control-Z>', lambda e: self.original_text.edit_undo() or "break")
        self.original_text.bind('<Control-Shift-z>', lambda e: self.original_text.edit_redo() or "break")
        self.original_text.bind('<Control-Shift-Z>', lambda e: self.original_text.edit_redo() or "break")

        # ===== LANGUAGE SELECTOR =====
        ttk.Label(content_frame, text="Translate to:", font=('Segoe UI', 10)).pack(anchor='w')

        # Search box
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(content_frame, textvariable=self.search_var,
                                      font=('Segoe UI', 10))
        self.search_entry.pack(fill=X, pady=(5, 5))
        self.search_entry.insert(0, "Search language...")
        self.search_entry.bind('<FocusIn>', self._on_search_focus_in)
        self.search_entry.bind('<FocusOut>', self._on_search_focus_out)
        self.search_var.trace_add('write', self._filter_languages)

        # Language listbox (no visible scrollbar)
        list_frame = ttk.Frame(content_frame)
        list_frame.pack(fill=X, pady=(0, 15))

        self.lang_listbox = tk.Listbox(list_frame, height=2, bg='#2b2b2b', fg='#ffffff',
                                       font=('Segoe UI', 10), relief='flat',
                                       selectbackground='#0d6efd', selectforeground='white',
                                       activestyle='none', highlightthickness=0,
                                       borderwidth=0)
        self.lang_listbox.pack(fill=X)
        self.lang_listbox.bind('<MouseWheel>',
            lambda e: self.lang_listbox.yview_scroll(int(-1*(e.delta/120)), "units"))

        self._populate_language_list()
        self.lang_listbox.bind('<<ListboxSelect>>', self._on_language_select)
        self._select_language_in_list(target_lang)

        # ===== CUSTOM PROMPT =====
        ttk.Label(content_frame, text="Custom prompt (optional):",
                  font=('Segoe UI', 10)).pack(anchor='w')

        self.custom_prompt_text = tk.Text(content_frame, height=2, wrap=tk.WORD,
                                          bg='#2b2b2b', fg='#cccccc',
                                          font=('Segoe UI', 10), relief='flat',
                                          padx=10, pady=10, insertbackground='white',
                                          undo=True, maxundo=-1)
        self.custom_prompt_text.pack(fill=X, pady=(5, 15))
        self.custom_prompt_text.bind('<MouseWheel>',
            lambda e: self.custom_prompt_text.yview_scroll(int(-1*(e.delta/120)), "units"))

        # Undo/Redo bindings for custom prompt
        self.custom_prompt_text.bind('<Control-z>', lambda e: self.custom_prompt_text.edit_undo() or "break")
        self.custom_prompt_text.bind('<Control-Z>', lambda e: self.custom_prompt_text.edit_undo() or "break")
        self.custom_prompt_text.bind('<Control-Shift-z>', lambda e: self.custom_prompt_text.edit_redo() or "break")
        self.custom_prompt_text.bind('<Control-Shift-Z>', lambda e: self.custom_prompt_text.edit_redo() or "break")

        # Placeholder for custom prompt
        placeholder = "E.g., 'Make it formal' or 'Use casual tone'"
        self.custom_prompt_text.insert('1.0', placeholder)
        self.custom_prompt_text.config(fg='#666666')

        def on_custom_focus_in(e):
            if self.custom_prompt_text.get('1.0', 'end-1c') == placeholder:
                self.custom_prompt_text.delete('1.0', tk.END)
                self.custom_prompt_text.config(fg='#cccccc')

        def on_custom_focus_out(e):
            if not self.custom_prompt_text.get('1.0', 'end-1c').strip():
                self.custom_prompt_text.insert('1.0', placeholder)
                self.custom_prompt_text.config(fg='#666666')

        self.custom_prompt_text.bind('<FocusIn>', on_custom_focus_in)
        self.custom_prompt_text.bind('<FocusOut>', on_custom_focus_out)

        # ===== TRANSLATION OUTPUT =====
        ttk.Label(content_frame, text="Translation:", font=('Segoe UI', 10)).pack(anchor='w')

        self.trans_text = tk.Text(content_frame, height=10, wrap=tk.WORD,
                                  bg='#2b2b2b', fg='#ffffff',
                                  font=('Segoe UI', 12), relief='flat',
                                  padx=10, pady=10)
        self.trans_text.insert('1.0', translated)
        self.trans_text.config(state='disabled')  # Make read-only
        self.trans_text.pack(fill=BOTH, expand=True, pady=(5, 0))
        self.trans_text.bind('<MouseWheel>',
            lambda e: self.trans_text.yview_scroll(int(-1*(e.delta/120)), "units"))

        # Enable DnD for popup window
        self.popup.update_idletasks()  # Ensure window is fully realized

        # Debug: Log DnD availability
        logging.info(f"HAS_DND={HAS_DND}, HAS_WINDND={HAS_WINDND}")

        # Use windnd - it's the most reliable for Windows Toplevel windows
        if HAS_WINDND:
            def setup_windnd():
                if not self.popup or not self.popup.winfo_exists():
                    return
                try:
                    # Force window to be fully realized
                    self.popup.update()
                    hwnd = self.popup.winfo_id()
                    logging.info(f"Setting up windnd for popup HWND: {hwnd}")

                    # Hook using windnd - callback will put files in queue
                    windnd.hook_dropfiles(self.popup, self._on_windnd_drop_direct)
                    logging.info("windnd drag-and-drop enabled for popup")

                    # Start queue checker on main thread to process dropped files
                    self.root.after(50, self._check_drop_queue)
                    logging.info("Drop queue checker started")

                except Exception as e:
                    logging.error(f"Failed to setup windnd: {e}")
                    import traceback
                    traceback.print_exc()

            # Delay to ensure window is fully realized
            self.popup.after(300, setup_windnd)

        self.popup.focus_force()

    def _populate_language_list(self):
        """Populate language listbox."""
        if not hasattr(self, 'lang_listbox'):
            return
        self.lang_listbox.delete(0, tk.END)
        for lang_name, lang_code, _ in self.filtered_languages:
            self.lang_listbox.insert(tk.END, f"{lang_name} ({lang_code})")

    def _filter_languages(self, *args):
        """Filter language list based on search."""
        if not hasattr(self, 'lang_listbox'):
            return

        search_term = self.search_var.get().lower()
        if search_term in ("", "search language..."):
            self.filtered_languages = LANGUAGES.copy()
        else:
            self.filtered_languages = []
            for lang_name, lang_code, lang_aliases in LANGUAGES:
                searchable = f"{lang_name} {lang_code} {lang_aliases}".lower()
                if search_term in searchable:
                    self.filtered_languages.append((lang_name, lang_code, lang_aliases))

        self._populate_language_list()

        if self.filtered_languages:
            self.lang_listbox.selection_set(0)
            self.selected_language = self.filtered_languages[0][0]
            self._update_translate_button()

    def _on_search_focus_in(self, event):
        """Handle search box focus in."""
        if self.search_entry.get() == "Search language...":
            self.search_entry.delete(0, tk.END)

    def _on_search_focus_out(self, event):
        """Handle search box focus out."""
        if not self.search_entry.get():
            self.search_entry.insert(0, "Search language...")

    def _on_language_select(self, event):
        """Handle language selection."""
        selection = self.lang_listbox.curselection()
        if selection:
            index = selection[0]
            if index < len(self.filtered_languages):
                self.selected_language = self.filtered_languages[index][0]
                self._update_translate_button()

    def _select_language_in_list(self, lang_name: str):
        """Select a language in the listbox."""
        if not hasattr(self, 'lang_listbox'):
            return
        for i, (name, _, _) in enumerate(self.filtered_languages):
            if name == lang_name:
                self.lang_listbox.selection_clear(0, tk.END)
                self.lang_listbox.selection_set(i)
                self.lang_listbox.see(i)
                self.selected_language = name
                break
        self._update_translate_button()

    def _update_translate_button(self):
        """Update translate button text."""
        if hasattr(self, 'translate_btn'):
            self.translate_btn.configure(text=f"Translate → {self.selected_language}")

    def _do_retranslate(self):
        """Perform translation from popup."""
        original = self.original_text.get('1.0', tk.END).strip()
        
        # Check for attachments
        attachments = self.attachment_area.get_attachments() if (hasattr(self, 'attachment_area') and self.attachment_area) else []
        has_attachments = len(attachments) > 0

        if not original and not has_attachments:
            return

        # Get custom prompt
        custom_prompt = self.custom_prompt_text.get('1.0', tk.END).strip()
        placeholder = "E.g., 'Make it formal' or 'Use casual tone'"
        if custom_prompt == placeholder:
            custom_prompt = ""

        self.translate_btn.configure(text="⏳ Translating...", state='disabled')
        self.popup.update()

        def translate_thread():
            translated = ""
            extracted_original = ""

            if has_attachments:
                # Collect all attachments for single API call
                image_paths = []
                file_contents = {}  # {filename: content}
                image_filenames = []  # Track image filenames for response format

                for att in attachments:
                    path = att['path']
                    filename = os.path.basename(path)

                    # Skip missing files
                    if not os.path.exists(path):
                        logging.warning(f"Skipping missing file: {path}")
                        continue

                    if att['type'] == 'image':
                        image_paths.append(path)
                        image_filenames.append(filename)
                    elif att['type'] == 'file':
                        try:
                            content = self.file_processor.extract_text(path)
                            file_contents[filename] = content
                        except Exception as e:
                            file_contents[filename] = f"[Error reading file: {str(e)}]"

                # Build prompt for multimodal translation
                try:
                    # Build file list for prompt
                    file_list_text = ""
                    if image_filenames:
                        file_list_text += "Images: " + ", ".join(image_filenames) + "\n"
                    if file_contents:
                        file_list_text += "Text files: " + ", ".join(file_contents.keys()) + "\n"

                    base_instruction = f"Translate to {self.selected_language}."
                    if custom_prompt:
                        base_instruction += f" {custom_prompt}"

                    prompt = f"""{base_instruction}

You have received the following files:
{file_list_text}
{f'Additional context from user: {original}' if original else ''}

CRITICAL INSTRUCTIONS:
1. For IMAGES: Perform OCR - extract ALL visible text EXACTLY as it appears.
   - Do NOT describe the image
   - Do NOT say "The image shows..." or "This appears to be..."
   - ONLY output the actual text you can read
   - Preserve the original formatting, line breaks, and structure

2. For TEXT FILES: Use the provided content directly.

3. Then translate all extracted text.

=== EXAMPLE (CORRECT) ===
If image shows a restaurant menu:
**[menu.jpg]:**
Today's Special
Grilled Salmon $18.99
Caesar Salad $12.50
---
NOT: "The image shows a restaurant menu with prices listed."

=== EXAMPLE (CORRECT) ===
If image shows a business document:
**[document.png]:**
Meeting Notes - January 15, 2026
Attendees: John, Mary, Bob
Action Items:
1. Review budget proposal
2. Schedule follow-up
---
NOT: "This is a business document containing meeting notes."

Return your response in this EXACT format:

===ORIGINAL===
**[filename1]:**
[For images: ALL text extracted via OCR, exactly as written]
[For text files: the original content]

**[filename2]:**
[extracted text]

===TRANSLATION===
**[filename1]:**
[translated text]

**[filename2]:**
[translated text]

Process ALL files. Extract actual text from images (OCR), do not describe them."""

                    # Single API call with all images + file contents
                    result = self.translation_service.api_manager.translate_multimodal(
                        prompt, image_paths, file_contents
                    )

                    # Parse result to separate Original and Translation sections
                    if "===ORIGINAL===" in result and "===TRANSLATION===" in result:
                        try:
                            # Split by the markers
                            parts = result.split("===TRANSLATION===")
                            original_section = parts[0].replace("===ORIGINAL===", "").strip()
                            translation_section = parts[1].strip() if len(parts) > 1 else ""

                            extracted_original = original_section
                            translated = translation_section
                        except (IndexError, ValueError):
                            # If parsing fails, put everything in translation
                            translated = result
                    else:
                        # AI didn't follow format, use full result as translation
                        translated = result

                except Exception as e:
                    translated = f"Error processing attachments: {str(e)}"
            else:
                # Standard text translation (no attachments)
                translated = self.translation_service.translate_text(
                    original, self.selected_language, custom_prompt)

            if self.popup:
                self.popup.after(0, lambda: self._update_translation_with_original(translated, extracted_original))

        threading.Thread(target=translate_thread, daemon=True).start()

    def _update_translation(self, translated: str):
        """Update translation result in popup."""
        self._update_translation_with_original(translated, "")

    def _update_translation_with_original(self, translated: str, extracted_original: str = ""):
        """Update translation result and optionally the original text in popup."""
        # Update original text box if extracted_original is provided
        if extracted_original:
            self.original_text.delete('1.0', tk.END)
            self.original_text.insert('1.0', extracted_original)

        # Update translation text box
        self.trans_text.config(state='normal')  # Enable to update
        self.trans_text.delete('1.0', tk.END)
        self.trans_text.insert('1.0', translated)
        self.trans_text.config(state='disabled')  # Make read-only again
        self.translate_btn.configure(text=f"Translate → {self.selected_language}",
                                     state='normal')

    def _copy_translation(self):
        """Copy translation to clipboard."""
        translated = self.trans_text.get('1.0', tk.END).strip()
        if not translated:
            self.toast.show_warning("No translation to copy")
            return
        pyperclip.copy(translated)
        self.copy_btn.configure(text="Copied!")
        self.toast.show_success("Copied to clipboard!")
        self.popup.after(1000, lambda: self.copy_btn.configure(text="Copy"))

    def _open_in_gemini(self):
        """Open Gemini web with translation prompt."""
        original = self.original_text.get('1.0', tk.END).strip()
        if not original:
            self.toast.show_warning("No text to translate")
            return

        prompt = f"Translate the following text to {self.selected_language}:\n\n{original}"
        pyperclip.copy(prompt)
        self.gemini_btn.configure(text="Copied! Opening...")
        self.toast.show_info("Prompt copied! Opening Gemini...")
        webbrowser.open("https://gemini.google.com/app")
        self.popup.after(2000, lambda: self.gemini_btn.configure(text="✦ Open Gemini"))

    def _open_history(self):
        """Open history dialog."""
        if self.popup:
            HistoryDialog(self.popup, self.translation_service.history_manager, self._load_history_item)

    def _load_history_item(self, item):
        """Load a history item into the translator."""
        if not self.popup:
            return
            
        self.original_text.delete('1.0', tk.END)
        self.original_text.insert('1.0', item.get('original', ''))
        
        self._select_language_in_list(item.get('target_lang', 'English'))
        
        self._update_translation(item.get('translated', ''))

    def _start_screenshot_ocr(self):
        """Start screenshot capture process."""
        if not self.config.get('vision_enabled', False):
            self.show_tooltip("", "Error: Vision Mode is disabled.\nPlease enable it in Settings to use Screenshot Translate.", "Error")
            return
            
        # Hide windows to capture clean screenshot
        if self.popup: self.popup.withdraw()
        if self.tooltip: self.tooltip.withdraw()
        if self.settings_window and self.settings_window.window.winfo_exists():
            self.settings_window.window.withdraw()
            
        # Delay slightly to allow withdraw
        self.root.after(200, lambda: self.screenshot_capture.capture_region(self._on_screenshot_captured))

    def _on_screenshot_captured(self, image_path):
        """Handle captured screenshot - add to attachments for user to process."""
        # Restore settings window if it was open
        if self.settings_window and self.settings_window.window.winfo_exists():
            self.settings_window.window.deiconify()

        if not image_path:
            # Restore popup if it existed
            if self.popup:
                self.popup.deiconify()
            return

        # Check if popup already exists with attachment_area
        popup_exists = (self.popup and
                        hasattr(self, 'attachment_area') and
                        self.attachment_area)

        if popup_exists:
            # Popup exists - just restore it and add screenshot (don't recreate)
            try:
                self.popup.deiconify()
                self.popup.attributes('-topmost', True)
                self.popup.update()
                self.popup.attributes('-topmost', False)
                self.popup.lift()
                self.popup.focus_force()
            except tk.TclError:
                popup_exists = False  # Window was destroyed, need to create new

        if not popup_exists:
            # Create new popup
            self.show_popup("", "", self.selected_language, force_new=True)

        # Add screenshot to attachments
        if hasattr(self, 'attachment_area') and self.attachment_area:
            try:
                self.attachment_area.add_file(image_path, show_warning=False)
                logging.info(f"Screenshot added to attachments: {image_path}")
            except Exception as e:
                logging.error(f"Failed to add screenshot to attachments: {e}")

    def _process_screenshot(self, image_path):
        """Process screenshot with AI."""
        try:
            target_lang = self.selected_language
            prompt = f"""
1. Extract all text from this image
2. Translate to {target_lang}

Response format:
**Original:**
[extracted text]

**Translation:**
[translated text]
"""
            result = self.translation_service.api_manager.translate_image(prompt, image_path)
            
            # Simple parsing (fallback to full result if format doesn't match)
            original = "Image Text"
            translated = result
            
            if "**Original:**" in result and "**Translation:**" in result:
                try:
                    parts = result.split("**Translation:**")
                    original = parts[0].replace("**Original:**", "").strip()
                    translated = parts[1].strip()
                except (IndexError, ValueError):
                    pass  # Keep default values on parse failure

            # Update UI
            self.root.after(0, lambda: self.show_popup(original, translated, target_lang))

            # Clean up temp file
            try:
                os.remove(image_path)
            except OSError:
                pass  # File may already be deleted or locked
                
        except Exception as e:
            self.root.after(0, lambda: self.show_popup("Error processing image", str(e), self.selected_language))

    def _setup_wm_dropfiles_handler(self, hwnd):
        """Setup Windows message handler for WM_DROPFILES using ctypes subclassing."""
        import ctypes
        from ctypes import wintypes

        # Windows constants
        WM_DROPFILES = 0x0233
        GWL_WNDPROC = -4

        # Function signatures
        WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_long, wintypes.HWND, wintypes.UINT,
                                      wintypes.WPARAM, wintypes.LPARAM)

        user32 = ctypes.windll.user32
        shell32 = ctypes.windll.shell32

        # Get original window procedure
        SetWindowLongPtrW = user32.SetWindowLongPtrW
        SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, WNDPROC]
        SetWindowLongPtrW.restype = WNDPROC

        CallWindowProcW = user32.CallWindowProcW
        CallWindowProcW.argtypes = [WNDPROC, wintypes.HWND, wintypes.UINT,
                                    wintypes.WPARAM, wintypes.LPARAM]
        CallWindowProcW.restype = ctypes.c_long

        # DragQueryFileW
        DragQueryFileW = shell32.DragQueryFileW
        DragQueryFileW.argtypes = [wintypes.HANDLE, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
        DragQueryFileW.restype = wintypes.UINT

        DragFinish = shell32.DragFinish
        DragFinish.argtypes = [wintypes.HANDLE]

        # Store original wndproc
        self._original_wndproc = None

        def wndproc(hwnd, msg, wparam, lparam):
            if msg == WM_DROPFILES:
                logging.info("WM_DROPFILES received!")
                hdrop = wparam
                try:
                    # Get number of files
                    file_count = DragQueryFileW(hdrop, 0xFFFFFFFF, None, 0)
                    logging.info(f"Dropped {file_count} files")

                    paths = []
                    for i in range(file_count):
                        # Get required buffer size
                        length = DragQueryFileW(hdrop, i, None, 0)
                        buffer = ctypes.create_unicode_buffer(length + 1)
                        DragQueryFileW(hdrop, i, buffer, length + 1)
                        paths.append(buffer.value)
                        logging.info(f"  File {i}: {buffer.value}")

                    DragFinish(hdrop)

                    # Process files on main thread
                    if paths:
                        self.root.after(0, lambda p=paths: self._process_dropped_files_direct(p))

                except Exception as e:
                    logging.error(f"Error processing WM_DROPFILES: {e}")
                    import traceback
                    traceback.print_exc()

                return 0

            # Call original window procedure
            return CallWindowProcW(self._original_wndproc, hwnd, msg, wparam, lparam)

        # Keep reference to prevent garbage collection
        self._wndproc_callback = WNDPROC(wndproc)

        # Subclass the window
        self._original_wndproc = SetWindowLongPtrW(hwnd, GWL_WNDPROC, self._wndproc_callback)
        logging.info(f"Window subclassed, original wndproc: {self._original_wndproc}")

    def _process_dropped_files_direct(self, paths):
        """Process files dropped via WM_DROPFILES."""
        logging.info(f"Processing {len(paths)} dropped files (direct)")

        if not self.popup or not self.popup.winfo_exists():
            logging.warning("Popup window no longer exists")
            return

        if not hasattr(self, 'attachment_area') or not self.attachment_area:
            logging.warning("No attachment area available")
            if HAS_TTKBOOTSTRAP:
                from ttkbootstrap.dialogs import Messagebox
                Messagebox.show_warning(
                    "Cannot add files.\n\n"
                    "Upload features are not enabled.\n"
                    "Please go to Settings > API Key tab and test your API to enable upload features.",
                    title="Upload Disabled",
                    parent=self.popup
                )
            else:
                from tkinter import messagebox
                messagebox.showwarning(
                    "Upload Disabled",
                    "Cannot add files.\n\n"
                    "Upload features are not enabled.\n"
                    "Please go to Settings > API Key tab and test your API to enable upload features.",
                    parent=self.popup
                )
            return

        for path in paths:
            try:
                result = self.attachment_area.add_file(path, show_warning=True)
                logging.info(f"add_file result for {path}: {result}")
            except Exception as e:
                logging.warning(f"Error adding dropped file {path}: {e}")

    def _on_tkdnd_drop(self, event):
        """Handle file drops via tkinterdnd2.

        This runs on the main Tkinter thread, so we can directly call Tkinter methods.
        """
        logging.info(f"tkinterdnd2 drop received: {event.data}")

        if not event.data:
            logging.warning("Drop event has no data")
            return

        # Parse file paths from tkinterdnd2 format
        # Handles paths with spaces wrapped in braces {}
        raw_data = event.data
        paths = []

        if '{' in raw_data:
            # Parse braced paths
            current = ""
            in_brace = False
            for char in raw_data:
                if char == '{':
                    in_brace = True
                elif char == '}':
                    in_brace = False
                    if current:
                        paths.append(current)
                        current = ""
                elif char == ' ' and not in_brace:
                    if current:
                        paths.append(current)
                        current = ""
                else:
                    current += char
            if current:
                paths.append(current)
        else:
            paths = raw_data.split()

        logging.info(f"Parsed paths: {paths}")

        # Process directly since we're on main thread
        self._process_tkdnd_files(paths)

    def _process_tkdnd_files(self, paths):
        """Process files dropped via tkinterdnd2."""
        if not self.popup or not self.popup.winfo_exists():
            logging.warning("Popup window no longer exists")
            return

        if not hasattr(self, 'attachment_area') or not self.attachment_area:
            logging.warning("No attachment area available")
            if HAS_TTKBOOTSTRAP:
                from ttkbootstrap.dialogs import Messagebox
                Messagebox.show_warning(
                    "Cannot add files.\n\n"
                    "Upload features are not enabled.\n"
                    "Please go to Settings > API Key tab and test your API to enable upload features.",
                    title="Upload Disabled",
                    parent=self.popup
                )
            else:
                from tkinter import messagebox
                messagebox.showwarning(
                    "Upload Disabled",
                    "Cannot add files.\n\n"
                    "Upload features are not enabled.\n"
                    "Please go to Settings > API Key tab and test your API to enable upload features.",
                    parent=self.popup
                )
            return

        for path in paths:
            try:
                result = self.attachment_area.add_file(path, show_warning=True)
                logging.info(f"add_file result for {path}: {result}")
            except Exception as e:
                logging.warning(f"Error adding dropped file {path}: {e}")

    def _on_windnd_drop_direct(self, file_paths):
        """Handle file drops via windnd.

        CRITICAL: This callback runs on a WINDOWS THREAD, not the Python main thread.
        We MUST NOT call ANY Tkinter methods here (including root.after()).
        Only use thread-safe operations: logging and queue.put().
        """
        try:
            # logging is thread-safe
            logging.info(f"windnd drop received: {len(file_paths)} files")

            # Decode paths (windnd returns bytes)
            paths = []
            for fp in file_paths:
                if isinstance(fp, bytes):
                    path = fp.decode('utf-8', errors='replace')
                else:
                    path = str(fp)
                paths.append(path)
                logging.info(f"  Dropped file: {path}")

            # Put in thread-safe queue - DO NOT call any Tkinter methods!
            self._drop_queue.put(paths)
            logging.info("Files added to drop queue")

        except Exception as e:
            logging.error(f"Error in windnd drop handler: {e}")

    def _on_windnd_drop(self, file_paths):
        """Handle file drops via windnd - use queue to avoid GIL issues.

        IMPORTANT: This callback runs from a Windows thread, NOT the main Python thread.
        We MUST NOT call any Tkinter methods here (including root.after()).
        Instead, we put the files in a thread-safe queue that the main thread checks.
        """
        # Just put files in queue - no Tkinter calls allowed here!
        try:
            # Note: logging is thread-safe in Python
            logging.info(f"windnd drop received: {len(file_paths)} files")
            self._drop_queue.put(file_paths)
        except Exception as e:
            logging.error(f"Error in windnd drop handler: {e}")

    def _check_drop_queue(self):
        """Check drop queue for files (runs on main Tkinter thread)."""
        try:
            while True:
                paths = self._drop_queue.get_nowait()
                logging.info(f"Processing drop queue: {len(paths)} files")
                # Paths are already decoded strings from _on_windnd_drop_direct
                self._process_dropped_files_direct(paths)
        except queue.Empty:
            pass
        except Exception as e:
            logging.error(f"Error checking drop queue: {e}")
            import traceback
            traceback.print_exc()

        # Schedule next check if running and popup exists
        if self.running and self.popup:
            try:
                if self.popup.winfo_exists():
                    self.root.after(50, self._check_drop_queue)
            except tk.TclError:
                pass  # Popup was closed
            except Exception as e:
                logging.debug(f"Error scheduling next queue check: {e}")

    def _process_dropped_files(self, file_paths):
        """Process dropped files on main thread."""
        logging.info(f"Processing {len(file_paths)} dropped files")
        try:
            # Verify popup and attachment_area still exist
            if not self.popup or not self.popup.winfo_exists():
                logging.warning("Popup window no longer exists")
                return
            if not hasattr(self, 'attachment_area') or not self.attachment_area:
                logging.warning("No attachment area available - vision/file features may be disabled")
                # Show user-friendly message
                if HAS_TTKBOOTSTRAP:
                    from ttkbootstrap.dialogs import Messagebox
                    Messagebox.show_warning(
                        "Cannot add files.\n\n"
                        "Upload features are not enabled.\n"
                        "Please go to Settings > API Key tab and test your API to enable upload features.",
                        title="Upload Disabled",
                        parent=self.popup
                    )
                else:
                    from tkinter import messagebox
                    messagebox.showwarning(
                        "Upload Disabled",
                        "Cannot add files.\n\n"
                        "Upload features are not enabled.\n"
                        "Please go to Settings > API Key tab and test your API to enable upload features.",
                        parent=self.popup
                    )
                return

            # windnd returns list of bytes, decode to strings
            paths = []
            for fp in file_paths:
                if isinstance(fp, bytes):
                    paths.append(fp.decode('utf-8', errors='replace'))
                else:
                    paths.append(str(fp))

            logging.info(f"Decoded paths: {paths}")

            # Add files to attachment area
            for path in paths:
                try:
                    result = self.attachment_area.add_file(path, show_warning=True)
                    logging.info(f"add_file result for {path}: {result}")
                except Exception as e:
                    logging.warning(f"Error adding dropped file {path}: {e}")
        except Exception as e:
            logging.error(f"Error processing dropped files: {e}")

    def show_settings(self, icon=None, item=None):
        """Show settings window."""
        # Ensure runs on main thread
        if threading.current_thread() is not threading.main_thread():
            self.root.after(0, lambda: self.show_settings(icon, item))
            return

        # Check if already open
        if self.settings_window and self.settings_window.window.winfo_exists():
            # Restore from minimized state
            self.settings_window.window.deiconify()
            # Force window to top using topmost trick
            self.settings_window.window.attributes('-topmost', True)
            self.settings_window.window.update()
            self.settings_window.window.attributes('-topmost', False)
            # Additional methods to ensure focus
            self.settings_window.window.lift()
            self.settings_window.window.focus_force()
            return

        def on_settings_save():
            self.translation_service.reconfigure()
            self.hotkey_manager.unregister_all()  # Restarts thread with new hotkeys
            self._refresh_tray_menu()

            if HAS_TTKBOOTSTRAP:
                Messagebox.show_info("Settings saved successfully!", title="Saved", parent=self.settings_window.window)
            else:
                from tkinter import messagebox
                messagebox.showinfo("Saved", "Settings saved successfully!", parent=self.settings_window.window)

        self.settings_window = SettingsWindow(self.root, self.config, on_settings_save)

    def _open_settings_from_error(self):
        """Open settings from error tooltip."""
        self.close_tooltip()
        self.show_settings()

    def _refresh_tray_menu(self):
        """Refresh tray menu to reflect updated hotkeys."""
        if self.tray_icon:
            # Build new menu items - Settings is right below Open Translator
            menu_items = [
                MenuItem('Open Translator', self.show_main_window, default=True),
                MenuItem('Settings', self.show_settings),
                MenuItem('─────────────', lambda: None, enabled=False),
            ]

            # Add all hotkeys (default + custom) from config
            all_hotkeys = self.config.get_all_hotkeys()
            for language, hotkey in all_hotkeys.items():
                display_hotkey = '+'.join(part.capitalize() for part in hotkey.split('+'))
                menu_items.append(
                    MenuItem(f'{display_hotkey} → {language}', lambda: None, enabled=False)
                )

            # Quit is at the bottom, separated from hotkeys
            menu_items.extend([
                MenuItem('─────────────', lambda: None, enabled=False),
                MenuItem('Quit', self.quit_app)
            ])

            self.tray_icon.menu = Menu(*menu_items)

    def _create_tray_icon(self):
        """Create system tray icon."""
        # Create icon image
        image = Image.new('RGB', (64, 64), color='#0d6efd')
        draw = ImageDraw.Draw(image)
        draw.text((18, 18), "T", fill='white')

        # Build menu items dynamically from config
        menu_items = [
            MenuItem('Open Translator', self.show_main_window, default=True),
            MenuItem('Settings', self.show_settings),
            MenuItem('─────────────', lambda: None, enabled=False),
        ]

        # Add all hotkeys (default + custom) from config
        all_hotkeys = self.config.get_all_hotkeys()
        for language, hotkey in all_hotkeys.items():
            # Format hotkey for display (e.g., "win+alt+v" → "Win+Alt+V")
            display_hotkey = '+'.join(part.capitalize() for part in hotkey.split('+'))
            menu_items.append(
                MenuItem(f'{display_hotkey} → {language}', lambda: None, enabled=False)
            )

        menu_items.extend([
            MenuItem('─────────────', lambda: None, enabled=False),
            MenuItem('Quit', self.quit_app)
        ])

        menu = Menu(*menu_items)

        self.tray_icon = Icon("AI Translator", image,
                             f"AI Translator v{VERSION}", menu)
        return self.tray_icon

    def quit_app(self, icon=None, item=None):
        """Quit the application with proper cleanup."""
        logging.info("Quitting application...")
        self.running = False

        # Cleanup hotkeys
        try:
            self.hotkey_manager.cleanup()
        except Exception as e:
            logging.error(f"Error cleaning up hotkeys: {e}")

        # Close tooltip
        self.close_tooltip()

        # Close popup
        if self.popup:
            try:
                if self.popup.winfo_exists():
                    self.popup.destroy()
            except Exception as e:
                logging.warning(f"Error destroying popup: {e}")

        # Stop tray icon
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception as e:
                logging.warning(f"Error stopping tray: {e}")

        # Quit root window
        try:
            if self.root.winfo_exists():
                self.root.quit()
        except Exception as e:
            logging.warning(f"Error quitting root: {e}")

        logging.info("Application shutdown complete")
        os._exit(0)

    def _check_queue(self):
        """Check translation queue for results with error handling."""
        try:
            while True:
                original, translated, target_lang = self.translation_service.translation_queue.get_nowait()
                if self.running:
                    self.show_tooltip(original, translated, target_lang)
        except queue.Empty:
            pass
        except Exception as e:
            logging.error(f"Error processing queue: {e}")

        # Schedule next check if still running
        if self.running:
            try:
                if self.root.winfo_exists():
                    self.root.after(100, self._check_queue)
            except Exception as e:
                logging.error(f"Error scheduling queue check: {e}")

    def _watchdog_check(self):
        """Lightweight watchdog to monitor app health."""
        if not self.running:
            return

        try:
            # Log heartbeat every 5 minutes
            current_time = time.time()
            if not hasattr(self, '_last_heartbeat'):
                self._last_heartbeat = current_time

            if current_time - self._last_heartbeat >= 300:  # 5 minutes
                logging.info(f"Heartbeat: App running for {int((current_time - self._app_start_time) / 60)} minutes")
                self._last_heartbeat = current_time

            # Schedule next watchdog check (every 60 seconds)
            self.root.after(60000, self._watchdog_check)
        except Exception as e:
            logging.error(f"Watchdog error: {e}")

    def _check_updates_async(self):
        """Check for updates asynchronously."""
        if not self.config.get_check_updates():
            return

        update_info = check_for_updates()
        if update_info['available']:
            self.root.after(0, lambda: self._show_update_notification(update_info))

    def _show_update_notification(self, update_info: Dict):
        """Show update notification."""
        if HAS_TTKBOOTSTRAP:
            result = Messagebox.yesno(
                f"A new version ({update_info['version']}) is available!\n\n"
                f"Current version: {VERSION}\n\n"
                "Would you like to download it?",
                title="Update Available",
                parent=self.root
            )
            if result == "Yes":
                webbrowser.open(update_info['url'])
        else:
            from tkinter import messagebox
            result = messagebox.askyesno(
                "Update Available",
                f"A new version ({update_info['version']}) is available!\n\n"
                f"Current version: {VERSION}\n\n"
                "Would you like to download it?"
            )
            if result:
                webbrowser.open(update_info['url'])

    def _show_api_error(self):
        """Show API error dialog."""
        APIErrorDialog(self.root, on_open_settings=self.show_settings)

    def _startup_api_check(self):
        """Perform a one-time API check on startup and cache results."""
        try:
            has_working_api = False
            has_vision_api = False
            
            api_keys = self.config.get_api_keys()
            manager = AIAPIManager()
            
            for config in api_keys:
                key = config.get('api_key', '').strip()
                model = config.get('model_name', '').strip()
                provider = config.get('provider', 'Auto')
                
                if key:
                    try:
                        manager.test_connection(model, key, provider)
                        self.config.api_status_cache[key] = True
                        has_working_api = True

                        # Check vision capability for this working key
                        target_provider = manager._identify_provider(model, key) if provider == 'Auto' else provider.lower()
                        if MultimodalProcessor.is_vision_capable(model, target_provider):
                            has_vision_api = True

                    except Exception as e:
                        logging.debug(f"API check failed for {model}: {e}")
                        self.config.api_status_cache[key] = False
            
            # Update runtime capabilities
            self.config.runtime_capabilities['file'] = has_working_api # Any working API can handle text files
            self.config.runtime_capabilities['vision'] = has_vision_api
            
            logging.info(f"Startup Check Results - Vision Capable: {has_vision_api}, File Capable: {has_working_api}")
            
        except Exception as e:
            logging.error(f"Startup API check failed: {e}")
            # Keep defaults (False) if check fails

    def run(self):
        """Run the application."""
        print("=" * 50)
        logging.info(f"AI Translator v{VERSION}")
        print(f"AI Translator v{VERSION}")
        print("=" * 50)
        print()
        print("Hotkeys:")
        for lang, hotkey in self.config.get_hotkeys().items():
            print(f"  {hotkey} → {lang}")
            logging.info(f"Hotkey: {hotkey} -> {lang}")
        print()
        print("Select any text, then press a hotkey to translate!")
        print()
        print("Listening...")
        print("-" * 50)

        # Track app start time for watchdog
        self._app_start_time = time.time()

        # Check API key
        if not self.config.get_api_key():
            self.root.after(500, self._show_api_error)

        # Start hotkey manager thread (registers hotkeys internally)
        self.hotkey_manager.start()
        self.hotkey_manager._ready_event.wait(timeout=2.0)  # Wait for hotkeys to be registered

        # Setup tray icon - use non-blocking approach
        self._create_tray_icon()

        # Run tray icon on separate thread with proper exception handling
        def run_tray_safe():
            try:
                self.tray_icon.run()
            except Exception as e:
                logging.error(f"Tray icon error: {e}")

        tray_thread = threading.Thread(target=run_tray_safe, daemon=True)
        tray_thread.start()

        # Check for updates
        threading.Thread(target=self._check_updates_async, daemon=True).start()
        
        # Run one-time startup API check (temporarily disabled)
        # threading.Thread(target=self._startup_api_check, daemon=True).start()

        # Start queue checker
        self.root.after(100, self._check_queue)

        # Start watchdog
        self.root.after(60000, self._watchdog_check)

        # Run main loop
        try:
            logging.info("Starting main loop")
            self.root.mainloop()
        except KeyboardInterrupt:
            logging.info("Keyboard interrupt received")
        except Exception as e:
            logging.critical(f"Main loop error: {e}", exc_info=True)
        finally:
            self.quit_app()
