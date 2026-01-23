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

from config import Config
from src.constants import VERSION, LANGUAGES
from src.core.translation import TranslationService
from src.core.api_manager import AIAPIManager
from src.core.hotkey import HotkeyManager
from src.ui.settings import SettingsWindow
from src.ui.dialogs import APIErrorDialog
from src.utils.updates import check_for_updates


class TranslatorApp:
    """Main application class."""

    def __init__(self):
        # Initialize configuration
        self.config = Config()

        # Create root window
        if HAS_TTKBOOTSTRAP:
            self.root = ttk.Window(themename="darkly")
        else:
            self.root = tk.Tk()
        self.root.withdraw()

        # Handle root window close
        self.root.protocol("WM_DELETE_WINDOW", self.quit_app)

        # Initialize services
        self.translation_service = TranslationService(self.config)
        self.hotkey_manager = HotkeyManager(self.config, self._on_hotkey_translate)

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

    def _on_hotkey_translate(self, language: str):
        """Handle hotkey translation request."""
        # Capture mouse position immediately when hotkey is pressed
        self._last_mouse_x = self.root.winfo_pointerx()
        self._last_mouse_y = self.root.winfo_pointery()
        self.root.after(0, lambda: self.show_loading_tooltip(language))
        self.translation_service.do_translation(language)

    def show_loading_tooltip(self, target_lang: str):
        """Show loading indicator."""
        if self.tooltip:
            try:
                self.tooltip.destroy()
            except:
                pass

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
        except:
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
            except:
                pass

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
            except:
                pass
            self.tooltip = None

    def copy_from_tooltip(self):
        """Copy translation from tooltip to clipboard."""
        pyperclip.copy(self.current_translated)
        self.tooltip_copy_btn.configure(text="Copied!")
        if self.tooltip:
            self.tooltip.after(1000, lambda: self._reset_copy_btn())

    def _reset_copy_btn(self):
        """Reset copy button text."""
        if self.tooltip and self.tooltip_copy_btn:
            try:
                self.tooltip_copy_btn.configure(text="Copy")
            except:
                pass

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

        # Prevent double-calling by checking if popup is being shown
        if hasattr(self, '_showing_popup') and self._showing_popup:
            return
        self._showing_popup = True
        try:
            self.show_popup("", "", self.selected_language)
        finally:
            # Reset after a short delay
            self.root.after(500, lambda: setattr(self, '_showing_popup', False))

    def show_popup(self, original: str, translated: str, target_lang: str):
        """Show the full translator popup window."""
        if self.popup:
            try:
                self.popup.destroy()
            except:
                pass
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
            except:
                pass
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

        # ===== ORIGINAL TEXT =====
        ttk.Label(main_frame, text="Original:", font=('Segoe UI', 10)).pack(anchor='w')

        self.original_text = tk.Text(main_frame, height=6, wrap=tk.WORD,
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
        ttk.Label(main_frame, text="Translate to:", font=('Segoe UI', 10)).pack(anchor='w')

        # Search box
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(main_frame, textvariable=self.search_var,
                                      font=('Segoe UI', 10))
        self.search_entry.pack(fill=X, pady=(5, 5))
        self.search_entry.insert(0, "Search language...")
        self.search_entry.bind('<FocusIn>', self._on_search_focus_in)
        self.search_entry.bind('<FocusOut>', self._on_search_focus_out)
        self.search_var.trace_add('write', self._filter_languages)

        # Language listbox (no visible scrollbar)
        list_frame = ttk.Frame(main_frame)
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
        ttk.Label(main_frame, text="Custom prompt (optional):",
                  font=('Segoe UI', 10)).pack(anchor='w')

        self.custom_prompt_text = tk.Text(main_frame, height=2, wrap=tk.WORD,
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
        ttk.Label(main_frame, text="Translation:", font=('Segoe UI', 10)).pack(anchor='w')

        self.trans_text = tk.Text(main_frame, height=10, wrap=tk.WORD,
                                  bg='#2b2b2b', fg='#ffffff',
                                  font=('Segoe UI', 12), relief='flat',
                                  padx=10, pady=10)
        self.trans_text.insert('1.0', translated)
        self.trans_text.config(state='disabled')  # Make read-only
        self.trans_text.pack(fill=BOTH, expand=True, pady=(5, 15))
        self.trans_text.bind('<MouseWheel>',
            lambda e: self.trans_text.yview_scroll(int(-1*(e.delta/120)), "units"))

        # ===== BUTTONS =====
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=X)

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

        # Close button
        if HAS_TTKBOOTSTRAP:
            ttk.Button(btn_frame, text="Close", command=on_popup_close,
                       bootstyle="secondary", width=12).pack(side=RIGHT)
        else:
            ttk.Button(btn_frame, text="Close", command=on_popup_close,
                       width=12).pack(side=RIGHT)

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
        if not original:
            return

        # Get custom prompt
        custom_prompt = self.custom_prompt_text.get('1.0', tk.END).strip()
        placeholder = "E.g., 'Make it formal' or 'Use casual tone'"
        if custom_prompt == placeholder:
            custom_prompt = ""

        self.translate_btn.configure(text="⏳ Translating...", state='disabled')
        self.popup.update()

        def translate_thread():
            translated = self.translation_service.translate_text(
                original, self.selected_language, custom_prompt)
            if self.popup:
                self.popup.after(0, lambda: self._update_translation(translated))

        threading.Thread(target=translate_thread, daemon=True).start()

    def _update_translation(self, translated: str):
        """Update translation result in popup."""
        self.trans_text.config(state='normal')  # Enable to update
        self.trans_text.delete('1.0', tk.END)
        self.trans_text.insert('1.0', translated)
        self.trans_text.config(state='disabled')  # Make read-only again
        self.translate_btn.configure(text=f"Translate → {self.selected_language}",
                                     state='normal')

    def _copy_translation(self):
        """Copy translation to clipboard."""
        translated = self.trans_text.get('1.0', tk.END).strip()
        pyperclip.copy(translated)
        self.copy_btn.configure(text="Copied!")
        self.popup.after(1000, lambda: self.copy_btn.configure(text="Copy"))

    def _open_in_gemini(self):
        """Open Gemini web with translation prompt."""
        original = self.original_text.get('1.0', tk.END).strip()
        if not original:
            return

        prompt = f"Translate the following text to {self.selected_language}:\n\n{original}"
        pyperclip.copy(prompt)
        self.gemini_btn.configure(text="Copied! Opening...")
        webbrowser.open("https://gemini.google.com/app")
        self.popup.after(2000, lambda: self.gemini_btn.configure(text="✦ Open Gemini"))

    def show_settings(self, icon=None, item=None):
        """Show settings window."""
        # Ensure runs on main thread
        if threading.current_thread() is not threading.main_thread():
            self.root.after(0, lambda: self.show_settings(icon, item))
            return

        # Check if already open
        if self.settings_window and self.settings_window.window.winfo_exists():
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
            # Build new menu items
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
                    except:
                        self.config.api_status_cache[key] = False
        except Exception as e:
            logging.error(f"Startup API check failed: {e}")

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
        
        # Run one-time startup API check
        threading.Thread(target=self._startup_api_check, daemon=True).start()

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
