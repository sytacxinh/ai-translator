"""
Settings Window for AI Translator.
"""
import os
import sys
import gc
import logging
import threading
import webbrowser

import keyboard

import tkinter as tk
from tkinter import BOTH, X, LEFT, RIGHT, W, NW, END

try:
    import ttkbootstrap as ttk
    from ttkbootstrap.dialogs import Messagebox
    HAS_TTKBOOTSTRAP = True
except ImportError:
    from tkinter import ttk
    HAS_TTKBOOTSTRAP = False

from src.constants import VERSION, GITHUB_REPO, LANGUAGES, PROVIDERS_LIST
from src.core.api_manager import AIAPIManager
from src.utils.updates import check_for_updates, download_and_install_update, execute_update
from src.core.multimodal import MultimodalProcessor
from src.core.auth import require_auth


class SettingsWindow:
    """Settings dialog for configuring the application."""

    def __init__(self, parent, config, on_save_callback=None):
        self.config = config
        self.on_save_callback = on_save_callback
        self.hotkey_entries = {}
        self.custom_rows = []
        self.api_rows = []
        self.recording_language = None

        # Use tk.Toplevel for better compatibility
        self.window = tk.Toplevel(parent)
        self.window.title("Settings - AI Translator")
        self.window.geometry("1400x650")
        self.window.resizable(True, True)
        self.window.configure(bg='#2b2b2b')

        # Center on screen
        self.window.update_idletasks()
        x = (self.window.winfo_screenwidth() - 1400) // 2
        y = (self.window.winfo_screenheight() - 650) // 2
        self.window.geometry(f"+{x}+{y}")

        # Make window modal and handle close properly
        self.window.protocol("WM_DELETE_WINDOW", self.window.destroy)
        self.window.focus_force()

        try:
            self._create_widgets()
        except Exception as e:
            print(f"Error creating settings widgets: {e}")
            import traceback
            traceback.print_exc()

    def _create_widgets(self):
        """Create settings UI."""
        if HAS_TTKBOOTSTRAP:
            notebook = ttk.Notebook(self.window, bootstyle="dark")
        else:
            notebook = ttk.Notebook(self.window)
        notebook.pack(fill=BOTH, expand=True, padx=10, pady=10)

        # Tab 1: General (moved to first position)
        general_frame = ttk.Frame(notebook, padding=20) if HAS_TTKBOOTSTRAP else ttk.Frame(notebook)
        notebook.add(general_frame, text="  General  ")
        self._create_general_tab(general_frame)

        # Tab 2: Hotkeys
        hotkey_frame = ttk.Frame(notebook, padding=20) if HAS_TTKBOOTSTRAP else ttk.Frame(notebook)
        notebook.add(hotkey_frame, text="  Hotkeys  ")
        self._create_hotkey_tab(hotkey_frame)

        # Tab 3: API Key
        api_frame = ttk.Frame(notebook, padding=20) if HAS_TTKBOOTSTRAP else ttk.Frame(notebook)
        notebook.add(api_frame, text="  API Key  ")
        self._create_api_tab(api_frame)

        # Buttons
        btn_frame = ttk.Frame(self.window)
        btn_frame.pack(fill=X, padx=10, pady=(0, 10))

        if HAS_TTKBOOTSTRAP:
            ttk.Button(btn_frame, text="Save", command=self._save,
                       bootstyle="success", width=15).pack(side=RIGHT, padx=5)
            ttk.Button(btn_frame, text="Cancel", command=self.window.destroy,
                       bootstyle="secondary", width=15).pack(side=RIGHT)
        else:
            ttk.Button(btn_frame, text="Save", command=self._save,
                       width=15).pack(side=RIGHT, padx=5)
            ttk.Button(btn_frame, text="Cancel", command=self.window.destroy,
                       width=15).pack(side=RIGHT)

    def _create_api_tab(self, parent):
        """Create API key settings tab."""
        self.api_rows = []
        self.api_canvas = None
        self.api_container = None

        ttk.Label(parent, text="API Configuration", font=('Segoe UI', 12, 'bold')).pack(anchor=W)
        ttk.Label(parent, text="Configure multiple models and keys for failover redundancy.",
                  font=('Segoe UI', 9)).pack(anchor=W, pady=(5, 5))
        ttk.Label(parent, text="⚠ Note: Each 'Test' counts as 1 API request toward your quota.",
                  font=('Segoe UI', 9, 'italic'), foreground='#ff9900').pack(anchor=W, pady=(0, 10))

        # Scrollable container for API keys (no visible scrollbar)
        canvas = tk.Canvas(parent, highlightthickness=0, height=380)
        api_container = ttk.Frame(canvas)

        canvas.pack(fill=BOTH, expand=True)
        self.api_canvas = canvas
        self.api_container = api_container

        window_id = canvas.create_window((0, 0), window=api_container, anchor=NW)

        def _configure_canvas(event):
            canvas.itemconfig(window_id, width=event.width)
        canvas.bind('<Configure>', _configure_canvas)

        # Mousewheel scrolling only
        def _on_mousewheel(event):
            if canvas.winfo_exists() and canvas.winfo_ismapped():
                try:
                    canvas.yview_scroll(int(-1*(event.delta/120)), "units")
                except tk.TclError:
                    pass  # Canvas may have been destroyed
        canvas.bind("<MouseWheel>", _on_mousewheel)
        api_container.bind("<MouseWheel>", _on_mousewheel)

        # Container for API rows (to keep them separate from buttons/footer)
        self.api_list_frame = ttk.Frame(api_container)
        self.api_list_frame.pack(fill=X, expand=True)

        # Load existing keys (Primary row always exists, empty by default)
        saved_keys = self.config.get_api_keys()
        if not saved_keys:
            saved_keys = [{'model_name': '', 'api_key': ''}]

        # Render rows
        for i, config in enumerate(saved_keys):
            is_primary = (i == 0)
            self._add_api_row(self.api_list_frame, config.get('model_name', ''), config.get('api_key', ''), config.get('provider', 'Auto'), is_primary)

        # Buttons frame: Show All + Delete All (left) + Add Backup (right)
        btn_frame = ttk.Frame(api_container)
        btn_frame.pack(fill=X, pady=15)

        # Track show all state
        self.show_all_state = {'showing': False, 'authenticated': False}

        if HAS_TTKBOOTSTRAP:
            self.show_all_btn = ttk.Button(btn_frame, text="Show All API Keys",
                       command=self._toggle_show_all_keys,
                       bootstyle="secondary-outline", width=18)
            self.show_all_btn.pack(side=LEFT)
            ttk.Button(btn_frame, text="Delete All API Keys",
                       command=self._delete_all_keys,
                       bootstyle="danger", width=18).pack(side=LEFT, padx=(10, 0))
            self.add_api_btn = ttk.Button(btn_frame, text="+ Add Backup Key",
                                        command=lambda: self._add_new_api_row(self.api_list_frame, canvas),
                                        bootstyle="success-outline", width=18)
        else:
            self.show_all_btn = ttk.Button(btn_frame, text="Show All API Keys",
                       command=self._toggle_show_all_keys, width=18)
            self.show_all_btn.pack(side=LEFT)
            ttk.Button(btn_frame, text="Delete All API Keys",
                       command=self._delete_all_keys, width=18).pack(side=LEFT, padx=(10, 0))
            self.add_api_btn = ttk.Button(btn_frame, text="+ Add Backup Key",
                                        command=lambda: self._add_new_api_row(self.api_list_frame, canvas), width=18)
        self.add_api_btn.pack(side=LEFT, padx=10)

        ttk.Label(api_container, text="Delete All: Removes all API keys from storage permanently.",
                  font=('Segoe UI', 8), foreground='#888888').pack(anchor=W, pady=(5, 0))

        # ===== CAPABILITY STATUS (Auto-managed) =====
        ttk.Separator(api_container).pack(fill=X, pady=15)
        ttk.Label(api_container, text="API Capabilities (Auto-detected when you Test APIs):",
                  font=('Segoe UI', 10, 'bold')).pack(anchor=W)

        # Vision/Image capability
        vision_frame = ttk.Frame(api_container)
        vision_frame.pack(fill=X, pady=5)

        has_vision = self.config.has_any_vision_capable()
        self.vision_var = tk.BooleanVar(value=has_vision)

        if HAS_TTKBOOTSTRAP:
            self.vision_chk = ttk.Checkbutton(vision_frame, text="📷 Image Processing",
                                  variable=self.vision_var,
                                  bootstyle="success-round-toggle")
        else:
            self.vision_chk = ttk.Checkbutton(vision_frame, text="📷 Image Processing",
                                  variable=self.vision_var)
        self.vision_chk.pack(side=LEFT)
        self.vision_chk.configure(state='disabled')  # Display only
        status_text = "Available" if has_vision else "No capable API found"
        status_color = '#28a745' if has_vision else '#888888'
        ttk.Label(vision_frame, text=f"({status_text})", font=('Segoe UI', 8), foreground=status_color).pack(side=LEFT, padx=(5, 0))

        # File processing capability
        file_frame = ttk.Frame(api_container)
        file_frame.pack(fill=X, pady=5)

        has_file = self.config.has_any_file_capable()
        self.file_var = tk.BooleanVar(value=has_file)

        if HAS_TTKBOOTSTRAP:
            self.file_chk = ttk.Checkbutton(file_frame, text="📄 File Processing (.txt, .docx, .srt, .pdf)",
                                  variable=self.file_var,
                                  bootstyle="success-round-toggle")
        else:
            self.file_chk = ttk.Checkbutton(file_frame, text="📄 File Processing (.txt, .docx, .srt, .pdf)",
                                  variable=self.file_var)
        self.file_chk.pack(side=LEFT)
        self.file_chk.configure(state='disabled')  # Display only
        file_status = "Available" if has_file else "No capable API found"
        file_color = '#28a745' if has_file else '#888888'
        ttk.Label(file_frame, text=f"({file_status})", font=('Segoe UI', 8), foreground=file_color).pack(side=LEFT, padx=(5, 0))

        ttk.Label(api_container, text="💡 Tip: Click 'Test' on an API to detect its capabilities.",
                  font=('Segoe UI', 8), foreground='#888888').pack(anchor=W, pady=(5, 0))

        # Supported Providers Table
        ttk.Separator(api_container).pack(fill=X, pady=15)
        ttk.Label(api_container, text="Supported Providers & Models:", font=('Segoe UI', 10, 'bold')).pack(anchor=W)

        providers_text = (
            "• Google: Gemini models\n"
            "• OpenAI: GPT-4, o1, o3\n"
            "• Anthropic: Claude models\n"
            "• DeepSeek: DeepSeek-V3, R1\n"
            "• Groq: Llama, Mixtral\n"
            "• xAI: Grok models\n"
            "• Mistral AI: Mistral models\n"
            "• Perplexity: Sonar models\n"
            "• Cerebras: Llama models\n"
            "• SambaNova: Llama 405B\n"
            "• Together AI: Open source models\n"
            "• SiliconFlow: Qwen, Yi models\n"
            "• OpenRouter: All models"
        )

        ttk.Label(api_container, text=providers_text, font=('Segoe UI', 9),
                 foreground='#aaaaaa', justify=LEFT).pack(anchor=W, pady=(5, 10))

        # Update scroll region
        def update_scroll():
            api_container.update_idletasks()
            canvas.config(scrollregion=canvas.bbox("all"))
        self.window.after(100, update_scroll)

        # Note: Auto-test is now done once at app startup (see app.py _startup_api_check)
        # to avoid consuming API quota every time Settings is opened.

    def _add_api_row(self, parent, model, key, provider="Auto", is_primary=False):
        """Add a single API configuration row.

        Row format: Label + Model + API Key + Show + Test + Delete
        """
        row = ttk.Frame(parent)
        row.pack(fill=X, pady=5)

        # Row label (Primary or Backup #N)
        row_num = len(self.api_rows) + 1
        if is_primary:
            label_text = "Primary:"
        else:
            label_text = f"Backup {row_num - 1}:"
        ttk.Label(row, text=label_text, font=('Segoe UI', 9, 'bold'), width=10).pack(side=LEFT)

        # Provider Combobox
        provider_var = tk.StringVar(value=provider)
        ttk.Label(row, text="Provider:", font=('Segoe UI', 9)).pack(side=LEFT)
        provider_cb = ttk.Combobox(row, textvariable=provider_var, values=PROVIDERS_LIST, width=10, state="readonly")
        provider_cb.pack(side=LEFT, padx=(3, 8))

        # Model Name with placeholder
        model_var = tk.StringVar(value=model)
        ttk.Label(row, text="Model:", font=('Segoe UI', 9)).pack(side=LEFT)
        model_entry = ttk.Entry(row, textvariable=model_var, width=25)
        model_entry.pack(side=LEFT, padx=(3, 8))

        # Add placeholder for model entry
        model_placeholder = "gemini-2.0-flash"
        if not model:
            model_entry.insert(0, model_placeholder)
            model_entry.config(foreground='#888888')

        def on_model_focus_in(e):
            if model_entry.get() == model_placeholder:
                model_entry.delete(0, END)
                model_entry.config(foreground='white' if HAS_TTKBOOTSTRAP else 'black')

        def on_model_focus_out(e):
            if not model_entry.get():
                model_entry.insert(0, model_placeholder)
                model_entry.config(foreground='#888888')

        model_entry.bind('<FocusIn>', on_model_focus_in)
        model_entry.bind('<FocusOut>', on_model_focus_out)

        # API Key with placeholder
        key_var = tk.StringVar(value=key)
        ttk.Label(row, text="API Key:", font=('Segoe UI', 9)).pack(side=LEFT)

        key_entry = ttk.Entry(row, textvariable=key_var, width=70, show="*")
        key_entry.pack(side=LEFT, padx=(3, 5))

        # Store show state for this row
        show_state = {'showing': False, 'authenticated': False}

        # Show button (per-row)
        def toggle_show_key():
            if show_state['showing']:
                # Hide the key
                key_entry.config(show="*")
                show_btn.config(text="Show")
                if HAS_TTKBOOTSTRAP: show_btn.configure(bootstyle="secondary-outline")
                show_state['showing'] = False
            else:
                # Show the key - require authentication first
                # Skip auth if already authenticated via Show All or this row
                if not show_state['authenticated'] and not self.show_all_state.get('authenticated', False):
                    # Check if there's actually a key to show
                    if not key_var.get().strip():
                        return

                    # Require Windows authentication
                    if not require_auth(self.window):
                        return  # Auth failed or cancelled

                    # Mark as authenticated for this session (both row and global)
                    show_state['authenticated'] = True
                    self.show_all_state['authenticated'] = True

                key_entry.config(show="")
                show_btn.config(text="Hide")
                if HAS_TTKBOOTSTRAP: show_btn.configure(bootstyle="warning")
                show_state['showing'] = True

            # Sync "Show All" button state based on all rows
            self._sync_show_all_button_state()

        if HAS_TTKBOOTSTRAP:
            show_btn = ttk.Button(row, text="Show", command=toggle_show_key,
                                  bootstyle="secondary-outline", width=5)
        else:
            show_btn = ttk.Button(row, text="Show", command=toggle_show_key, width=5)
        show_btn.pack(side=LEFT, padx=2)

        # Test Button - width must accommodate "OK! Image OK | Files OK" (~24 chars)
        test_label = ttk.Label(row, text="", width=25, anchor='w')

        if HAS_TTKBOOTSTRAP:
            ttk.Button(row, text="Test",
                       command=lambda: self._test_single_api(model_var.get(), key_var.get(), provider_var.get(), test_label, model_placeholder),
                       bootstyle="info-outline", width=5).pack(side=LEFT, padx=2)
        else:
            ttk.Button(row, text="Test",
                       command=lambda: self._test_single_api(model_var.get(), key_var.get(), provider_var.get(), test_label, model_placeholder),
                       width=5).pack(side=LEFT, padx=2)

        # Delete Button (only for backups)
        if not is_primary:
            if HAS_TTKBOOTSTRAP:
                ttk.Button(row, text="Delete",
                           command=lambda r=row, kv=key_var: self._delete_api_row(r, kv),
                           bootstyle="danger-outline", width=6).pack(side=LEFT, padx=2)
            else:
                ttk.Button(row, text="Delete",
                           command=lambda r=row, kv=key_var: self._delete_api_row(r, kv),
                           width=6).pack(side=LEFT, padx=2)

        test_label.pack(side=LEFT, padx=3)

        # Display cached status from startup check (if available)
        if key:
            cached_status = self.config.api_status_cache.get(key, None)
            if cached_status is True:
                if HAS_TTKBOOTSTRAP:
                    test_label.config(text="OK (cached)", bootstyle="success")
                else:
                    test_label.config(text="OK (cached)", foreground="green")
            elif cached_status is False:
                if HAS_TTKBOOTSTRAP:
                    test_label.config(text="Error (cached)", bootstyle="danger")
                else:
                    test_label.config(text="Error (cached)", foreground="red")

        self.api_rows.append({
            'frame': row,
            'model_var': model_var,
            'provider_var': provider_var,
            'model_entry': model_entry,
            'model_placeholder': model_placeholder,
            'key_var': key_var,
            'key_entry': key_entry,
            'is_primary': is_primary,
            'test_label': test_label,
            'model_placeholder': model_placeholder,
            'show_btn': show_btn,
            'show_state': show_state
        })
        # Only update button if it exists (button is created after initial rows)
        if hasattr(self, 'add_api_btn'):
            self._update_api_add_button()

    def _add_new_api_row(self, container, canvas):
        """Add a new backup API row."""
        if len(self.api_rows) < 6: # 1 Primary + 5 Backups
            self._add_api_row(container, "", "")  # Empty model and key for new rows
            container.update_idletasks()
            canvas.config(scrollregion=canvas.bbox("all"))

    def _delete_api_row(self, row_frame, key_var):
        """Delete an API row from UI."""
        row_frame.destroy()
        self.api_rows = [r for r in self.api_rows if r['key_var'] != key_var]
        self._update_api_add_button()

    def _delete_all_keys(self):
        """Clear all API keys but keep models, and save immediately."""
        msg = "Are you sure you want to clear all API keys?\nThis will keep your model names but remove the keys.\nChanges will be saved immediately."
        if HAS_TTKBOOTSTRAP:
            result = Messagebox.yesno(msg, title="Confirm Clear", parent=self.window)
            if result != "Yes": return
        else:
            from tkinter import messagebox
            if not messagebox.askyesno("Confirm Clear", msg, parent=self.window): return

        # Clear keys in all rows
        for row in self.api_rows:
            row['key_var'].set("")

        # Save immediately as requested
        self._save_api_keys_to_config(secure=True)

        # Force garbage collection to clear strings from RAM immediately
        gc.collect()

        if HAS_TTKBOOTSTRAP:
            Messagebox.show_info("All API keys have been cleared and saved.", title="Keys Cleared", parent=self.window)
        else:
            from tkinter import messagebox
            messagebox.showinfo("Keys Cleared", "All API keys have been cleared and saved.", parent=self.window)

    def _toggle_show_all_keys(self):
        """Toggle showing/hiding all API keys with authentication."""
        if self.show_all_state['showing']:
            # Hide all keys
            for row in self.api_rows:
                row['key_entry'].config(show="*")
                # Update individual show button state and text
                if 'show_state' in row:
                    row['show_state']['showing'] = False
                if 'show_btn' in row:
                    row['show_btn'].config(text="Show")
                    if HAS_TTKBOOTSTRAP:
                        row['show_btn'].configure(bootstyle="secondary-outline")

            self.show_all_btn.config(text="Show All API Keys")
            if HAS_TTKBOOTSTRAP:
                self.show_all_btn.configure(bootstyle="secondary-outline")
            self.show_all_state['showing'] = False
        else:
            # Check if there are any keys to show
            has_keys = any(row['key_var'].get().strip() for row in self.api_rows)
            if not has_keys:
                if HAS_TTKBOOTSTRAP:
                    Messagebox.show_info("No API keys to show.", title="No Keys", parent=self.window)
                else:
                    from tkinter import messagebox
                    messagebox.showinfo("No Keys", "No API keys to show.", parent=self.window)
                return

            # Require authentication if not already authenticated
            if not self.show_all_state['authenticated']:
                if not require_auth(self.window):
                    return  # Auth failed or cancelled

                # Mark as authenticated for this session
                self.show_all_state['authenticated'] = True

            # Show all keys and update individual buttons
            for row in self.api_rows:
                row['key_entry'].config(show="")
                # Update individual show button state and text
                if 'show_state' in row:
                    row['show_state']['showing'] = True
                    row['show_state']['authenticated'] = True  # Mark row as authenticated too
                if 'show_btn' in row:
                    row['show_btn'].config(text="Hide")
                    if HAS_TTKBOOTSTRAP:
                        row['show_btn'].configure(bootstyle="warning")

            self.show_all_btn.config(text="Hide All API Keys")
            if HAS_TTKBOOTSTRAP:
                self.show_all_btn.configure(bootstyle="warning")
            self.show_all_state['showing'] = True

    def _sync_show_all_button_state(self):
        """Sync 'Show All' button state based on individual row states."""
        if not self.api_rows:
            return

        # Check if all rows with keys are showing
        rows_with_keys = [row for row in self.api_rows if row['key_var'].get().strip()]
        if not rows_with_keys:
            return

        all_showing = all(row.get('show_state', {}).get('showing', False) for row in rows_with_keys)
        all_hidden = all(not row.get('show_state', {}).get('showing', False) for row in rows_with_keys)

        if all_showing and not self.show_all_state['showing']:
            # All individual buttons are "Hide" -> update "Show All" to "Hide All"
            self.show_all_btn.config(text="Hide All API Keys")
            if HAS_TTKBOOTSTRAP:
                self.show_all_btn.configure(bootstyle="warning")
            self.show_all_state['showing'] = True
        elif all_hidden and self.show_all_state['showing']:
            # All individual buttons are "Show" -> update "Hide All" to "Show All"
            self.show_all_btn.config(text="Show All API Keys")
            if HAS_TTKBOOTSTRAP:
                self.show_all_btn.configure(bootstyle="secondary-outline")
            self.show_all_state['showing'] = False

    def _save_api_keys_to_config(self, secure=False):
        """Save current API keys to config."""
        try:
            api_keys_list = []
            for row in self.api_rows:
                model = row['model_var'].get().strip()
                key = row['key_var'].get().strip()
                provider = row['provider_var'].get()
                # Don't save placeholder as model name
                if model == row.get('model_placeholder', ''):
                    model = ''
                if model or key:  # Only save if there's actual data
                    api_keys_list.append({'model_name': model, 'api_key': key, 'provider': provider})
            self.config.set_api_keys(api_keys_list, secure=secure)
        except Exception as e:
            print(f"Error saving API keys to config: {e}")
            import traceback
            traceback.print_exc()

    def _update_api_add_button(self):
        """Enable/disable add button based on limit."""
        if len(self.api_rows) >= 6:
            self.add_api_btn.configure(state='disabled')
        else:
            self.add_api_btn.configure(state='normal')

    def _test_all_apis_async(self):
        """Test all API configurations asynchronously."""
        def run_tests():
            # Iterate through a copy of rows to avoid modification issues
            rows = list(self.api_rows)
            for row in rows:
                try:
                    # Call test function on main thread to update UI safely
                    self.window.after(0, lambda r=row: self._test_single_api(
                        r['model_var'].get(),
                        r['key_var'].get(),
                        r['provider_var'].get(),
                        r['test_label'],
                        r['model_placeholder'],
                        silent=True
                    ))
                except Exception:
                    pass
        
        threading.Thread(target=run_tests, daemon=True).start()

    def _test_single_api(self, model_name, api_key, provider, result_label, model_placeholder="gemini-2.0-flash", silent=False):
        """Test API connection."""
        model_name = model_name.strip()
        # Use placeholder as default if model is empty or is the placeholder text
        if not model_name or model_name == model_placeholder:
            model_name = model_placeholder
        api_key = api_key.strip()

        if HAS_TTKBOOTSTRAP:
            result_label.config(text="Testing...", bootstyle="warning")
        else:
            result_label.config(text="Testing...", foreground="orange")
        self.window.update()

        if not api_key:
            if HAS_TTKBOOTSTRAP:
                result_label.config(text="No API key", bootstyle="danger")
            else:
                result_label.config(text="No API key", foreground="red")
            return

        try:
            # Use the AIAPIManager to test, which now supports multi-provider logic
            api_manager = AIAPIManager()
            target_provider = api_manager._identify_provider(model_name, api_key) if provider == 'Auto' else provider.lower()
            api_manager.test_connection(model_name, api_key, provider)
            display_name = api_manager.get_display_name(target_provider)

            # Check Vision Capability (image processing)
            is_vision = MultimodalProcessor.is_vision_capable(model_name, target_provider)
            # Any working API can handle text files
            is_file_capable = True

            # Build capability status for label and message
            capability_parts = []
            if is_vision:
                capability_parts.append("Image OK")
            if is_file_capable:
                capability_parts.append("Files OK")
            capability_str = " | ".join(capability_parts) if capability_parts else ""
            label_text = f"OK! {capability_str}" if capability_str else "OK!"

            # Store capabilities in config
            self.config.update_api_capabilities(api_key, model_name, is_vision, is_file_capable)

            # Refresh toggle states (now auto-managed)
            self._refresh_vision_toggle_state()
            self._refresh_file_toggle_state()

            # Build detailed message
            capability_msg = ""
            if is_vision:
                capability_msg += "\n✓ Image Processing: Supported"
            if is_file_capable:
                capability_msg += "\n✓ File Processing: Supported"

            if HAS_TTKBOOTSTRAP:
                result_label.config(text=label_text, bootstyle="success")
                if not silent:
                    Messagebox.show_info(f"Connection Verified!\n\nProvider: {display_name}\nModel: {model_name}\nStatus: OK{capability_msg}", title="Test Result", parent=self.window)
            else:
                result_label.config(text=label_text, foreground="green")
                if not silent:
                    from tkinter import messagebox
                    messagebox.showinfo("Test Result", f"Connection Verified!\n\nProvider: {display_name}\nModel: {model_name}\nStatus: OK{capability_msg}", parent=self.window)
        except Exception as e:
            error = str(e)

            # Try to identify provider for error message
            provider_name = "UNKNOWN"
            try:
                code = (AIAPIManager()._identify_provider(model_name, api_key) if provider == 'Auto' else provider)
                provider_name = AIAPIManager().get_display_name(code)
            except Exception:
                pass  # Keep default UNKNOWN if identification fails

            if "API_KEY_INVALID" in error:
                if HAS_TTKBOOTSTRAP:
                    result_label.config(text="Invalid Key", bootstyle="danger")
                    if not silent:
                        Messagebox.show_error(f"Invalid API Key!\n\nProvider: {provider_name}\nModel: {model_name}\nError: {error}", title="Test Failed", parent=self.window)
                else:
                    result_label.config(text="Invalid Key", foreground="red")
                    if not silent:
                        from tkinter import messagebox
                        messagebox.showerror("Test Failed", f"Invalid API Key!\n\nProvider: {provider_name}\nModel: {model_name}\nError: {error}", parent=self.window)
            else:
                if HAS_TTKBOOTSTRAP:
                    result_label.config(text="Error", bootstyle="danger")
                    if not silent:
                        Messagebox.show_error(f"Connection Failed!\n\nProvider: {provider_name}\nModel: {model_name}\nError: {error}", title="Test Error", parent=self.window)
                else:
                    result_label.config(text="Error", foreground="red")
                    if not silent:
                        from tkinter import messagebox
                        messagebox.showerror("Test Error", f"Connection Failed!\n\nProvider: {provider_name}\nModel: {model_name}\nError: {error}", parent=self.window)

    def _refresh_vision_toggle_state(self):
        """Refresh vision toggle state based on API capabilities (auto-managed)."""
        try:
            has_vision = self.config.has_any_vision_capable()
            if hasattr(self, 'vision_var'):
                self.vision_var.set(has_vision)
            if hasattr(self, 'vision_chk'):
                # Toggle is display-only, always disabled
                self.vision_chk.configure(state='disabled')
        except Exception as e:
            logging.warning(f"Failed to refresh vision toggle: {e}")

    def _refresh_file_toggle_state(self):
        """Refresh file toggle state based on API capabilities (auto-managed)."""
        try:
            has_file = self.config.has_any_file_capable()
            if hasattr(self, 'file_var'):
                self.file_var.set(has_file)
            if hasattr(self, 'file_chk'):
                # Toggle is display-only, always disabled
                self.file_chk.configure(state='disabled')
        except Exception as e:
            logging.warning(f"Failed to refresh file toggle: {e}")

    def _create_hotkey_tab(self, parent):
        """Create hotkey settings tab."""
        # Clear previous entries
        self.hotkey_entries = {}
        self.custom_rows = []

        ttk.Label(parent, text="Keyboard Shortcuts", font=('Segoe UI', 12, 'bold')).pack(anchor=W)
        ttk.Label(parent, text="Click 'Edit' and press your desired key combination.",
                  font=('Segoe UI', 9)).pack(anchor=W, pady=(5, 15))

        # Scrollable frame for hotkeys
        canvas = tk.Canvas(parent, highlightthickness=0)
        hotkey_container = ttk.Frame(canvas)

        canvas.pack(side=LEFT, fill=BOTH, expand=True)

        window_id = canvas.create_window((0, 0), window=hotkey_container, anchor=NW)

        def _configure_canvas(event):
            canvas.itemconfig(window_id, width=event.width)
        canvas.bind('<Configure>', _configure_canvas)

        def _on_mousewheel(event):
            if canvas.winfo_exists() and canvas.winfo_ismapped():
                try:
                    x, y = canvas.winfo_pointerxy()
                    cx, cy = canvas.winfo_rootx(), canvas.winfo_rooty()
                    cw, ch = canvas.winfo_width(), canvas.winfo_height()
                    if cx <= x <= cx+cw and cy <= y <= cy+ch:
                        canvas.yview_scroll(int(-1*(event.delta/120)), "units")
                except tk.TclError:
                    pass  # Canvas may have been destroyed

        self.window.bind("<MouseWheel>", _on_mousewheel, add="+")

        # 1. Main Languages
        self.default_langs = ["Vietnamese", "English", "Japanese", "Chinese Simplified"]
        ttk.Label(hotkey_container, text="Main Languages", font=('Segoe UI', 10, 'bold')).pack(anchor=W, pady=(0, 10))

        saved_hotkeys = self.config.get_hotkeys()

        for lang in self.default_langs:
            current_key = saved_hotkeys.get(lang, self.config.DEFAULT_HOTKEYS.get(lang, ""))
            self._add_default_hotkey_row(hotkey_container, lang, current_key)

        ttk.Separator(hotkey_container).pack(fill=X, pady=20)

        # 2. Custom Languages
        ttk.Label(hotkey_container, text="Custom Languages", font=('Segoe UI', 10, 'bold')).pack(anchor=W, pady=(0, 10))

        self.custom_rows_frame = ttk.Frame(hotkey_container)
        self.custom_rows_frame.pack(fill=X)

        # Load existing custom hotkeys
        for lang, key in saved_hotkeys.items():
            if lang not in self.default_langs:
                self._add_custom_hotkey_row(self.custom_rows_frame, lang, key)

        # Add Button
        self.add_btn_frame = ttk.Frame(hotkey_container)
        self.add_btn_frame.pack(fill=X, pady=15)

        if HAS_TTKBOOTSTRAP:
            self.add_btn = ttk.Button(self.add_btn_frame, text="+ Add Language",
                                    command=lambda: self._add_new_custom_row(canvas, hotkey_container),
                                    bootstyle="success-outline")
        else:
            self.add_btn = ttk.Button(self.add_btn_frame, text="+ Add Language",
                                    command=lambda: self._add_new_custom_row(canvas, hotkey_container))
        self.add_btn.pack(side=LEFT)

        self._update_add_button_state()

        # Update scroll
        hotkey_container.update_idletasks()
        canvas.config(scrollregion=canvas.bbox("all"))

    def _add_default_hotkey_row(self, parent, language, hotkey):
        """Add a row for default languages with Restore button."""
        row = ttk.Frame(parent)
        row.pack(fill=X, pady=5, padx=5)

        ttk.Label(row, text=f"{language}:", width=22, anchor=W).pack(side=LEFT)

        entry_var = tk.StringVar(value=hotkey)
        entry = ttk.Entry(row, textvariable=entry_var, width=22, state='readonly')
        entry.pack(side=LEFT, padx=5)
        self.hotkey_entries[language] = entry_var

        if HAS_TTKBOOTSTRAP:
            ttk.Button(row, text="Edit", command=lambda: self._start_record(entry, entry_var),
                       bootstyle="info-outline", width=8).pack(side=LEFT, padx=2)
            ttk.Button(row, text="Restore",
                       command=lambda: entry_var.set(self.config.DEFAULT_HOTKEYS.get(language, "")),
                       bootstyle="secondary-outline", width=8).pack(side=LEFT, padx=2)
        else:
            ttk.Button(row, text="Edit", command=lambda: self._start_record(entry, entry_var),
                       width=8).pack(side=LEFT, padx=2)
            ttk.Button(row, text="Restore",
                       command=lambda: entry_var.set(self.config.DEFAULT_HOTKEYS.get(language, "")),
                       width=8).pack(side=LEFT, padx=2)

    def _add_custom_hotkey_row(self, parent, language, hotkey, is_new=False):
        """Add a row for custom languages with Delete button."""
        row = ttk.Frame(parent)
        row.pack(fill=X, pady=5, padx=5)

        lang_var = tk.StringVar(value=language)

        if is_new:
            # Filter available languages
            used_langs = self.default_langs + [r['lang_var'].get() for r in self.custom_rows]
            available = [l[0] for l in LANGUAGES if l[0] not in used_langs]
            all_langs = [l[0] for l in LANGUAGES]

            combo = ttk.Combobox(row, textvariable=lang_var, values=all_langs, width=20)
            combo.pack(side=LEFT)
            if available:
                combo.set(available[0])
        else:
            ttk.Label(row, text=f"{language}:", width=22, anchor=W).pack(side=LEFT)

        entry_var = tk.StringVar(value=hotkey)
        entry = ttk.Entry(row, textvariable=entry_var, width=22, state='readonly')
        entry.pack(side=LEFT, padx=5)

        if HAS_TTKBOOTSTRAP:
            ttk.Button(row, text="Edit", command=lambda: self._start_record(entry, entry_var),
                       bootstyle="info-outline", width=8).pack(side=LEFT, padx=2)
            ttk.Button(row, text="Delete",
                       command=lambda: self._delete_custom_row(row, lang_var),
                       bootstyle="danger-outline", width=8).pack(side=LEFT, padx=2)
        else:
            ttk.Button(row, text="Edit", command=lambda: self._start_record(entry, entry_var),
                       width=8).pack(side=LEFT, padx=2)
            ttk.Button(row, text="Delete",
                       command=lambda: self._delete_custom_row(row, lang_var),
                       width=8).pack(side=LEFT, padx=2)

        self.custom_rows.append({
            'frame': row,
            'lang_var': lang_var,
            'hotkey_var': entry_var
        })
        # Only update button if it exists (button is created after initial rows)
        if hasattr(self, 'add_btn'):
            self._update_add_button_state()

    def _add_new_custom_row(self, canvas, container):
        """Handle adding a new custom row."""
        if len(self.custom_rows) < 4:
            self._add_custom_hotkey_row(self.custom_rows_frame, "", "", is_new=True)
            container.update_idletasks()
            canvas.config(scrollregion=canvas.bbox("all"))

    def _delete_custom_row(self, row_frame, lang_var):
        """Delete a custom row."""
        row_frame.destroy()
        self.custom_rows = [r for r in self.custom_rows if r['lang_var'] != lang_var]
        self._update_add_button_state()

    def _update_add_button_state(self):
        """Enable/disable add button based on count."""
        if len(self.custom_rows) >= 4:
            self.add_btn.configure(state='disabled')
        else:
            self.add_btn.configure(state='normal')

    def _start_record(self, entry, entry_var):
        """Start recording hotkey."""
        entry.config(state='normal')
        entry.delete(0, END)
        entry.insert(0, "Press keys...")

        # Unhook any existing
        try:
            keyboard.unhook_all()
        except Exception:
            pass  # Keyboard hooks may not be active

        # Hook with specific callback for this entry
        keyboard.hook(lambda e: self._on_key_record(e, entry_var, entry))

    def _on_key_record(self, event, entry_var, entry=None):
        """Handle key press during recording."""
        if event.event_type == 'down':
            name = keyboard.get_hotkey_name()
            entry_var.set(name)

            # Check if it's a modifier key
            modifiers = getattr(keyboard, 'all_modifiers',
                              {'alt', 'alt gr', 'ctrl', 'left alt', 'left ctrl',
                               'left shift', 'left windows', 'right alt', 'right ctrl',
                               'right shift', 'right windows', 'shift', 'windows', 'cmd'})
            is_modifier = event.name in modifiers

            # If not a modifier, we assume the combo is complete
            if not is_modifier:
                keyboard.unhook_all()
                if entry:
                    entry.config(state='readonly')

    def _create_general_tab(self, parent):
        """Create general settings tab."""
        ttk.Label(parent, text="General Settings", font=('Segoe UI', 12, 'bold')).pack(anchor=W)

        # Auto-start
        ttk.Separator(parent).pack(fill=X, pady=15)
        self.autostart_var = tk.BooleanVar(value=self.config.is_autostart_enabled())
        if HAS_TTKBOOTSTRAP:
            ttk.Checkbutton(parent, text="Start AI Translator with Windows",
                            variable=self.autostart_var,
                            bootstyle="round-toggle-success").pack(anchor=W, pady=5)
        else:
            ttk.Checkbutton(parent, text="Start AI Translator with Windows",
                            variable=self.autostart_var).pack(anchor=W, pady=5)

        # Check for updates
        self.updates_var = tk.BooleanVar(value=self.config.get_check_updates())
        if HAS_TTKBOOTSTRAP:
            ttk.Checkbutton(parent, text="Check for updates on startup",
                            variable=self.updates_var,
                            bootstyle="round-toggle-success").pack(anchor=W, pady=5)
        else:
            ttk.Checkbutton(parent, text="Check for updates on startup",
                            variable=self.updates_var).pack(anchor=W, pady=5)

        # Check for updates button
        update_frame = ttk.Frame(parent)
        update_frame.pack(anchor=W, pady=(10, 0), fill=X)

        if HAS_TTKBOOTSTRAP:
            self.check_update_btn = ttk.Button(update_frame, text="Check for updates",
                                               command=self._check_for_updates_click,
                                               bootstyle="info-outline", width=18)
        else:
            self.check_update_btn = ttk.Button(update_frame, text="Check for updates",
                                               command=self._check_for_updates_click, width=18)
        self.check_update_btn.pack(side=LEFT)

        self.update_status_label = ttk.Label(update_frame, text="", font=('Segoe UI', 9))
        self.update_status_label.pack(side=LEFT, padx=(10, 0))

        # Restore Defaults button
        ttk.Separator(parent).pack(fill=X, pady=15)
        if HAS_TTKBOOTSTRAP:
            ttk.Button(parent, text="Restore Defaults", command=self._restore_defaults,
                       bootstyle="warning-outline", width=15).pack(anchor=W)
        else:
            ttk.Button(parent, text="Restore Defaults", command=self._restore_defaults,
                       width=15).pack(anchor=W)
        ttk.Label(parent, text="Reset hotkeys and settings to default values (keeps API keys)",
                  font=('Segoe UI', 8)).pack(anchor=W, pady=(2, 0))

        # About section
        ttk.Separator(parent).pack(fill=X, pady=20)
        ttk.Label(parent, text="About", font=('Segoe UI', 11, 'bold')).pack(anchor=W)
        ttk.Label(parent, text=f"AI Translator v{VERSION}").pack(anchor=W, pady=(5, 0))
        ttk.Label(parent, text="Supports multiple AI models with failover").pack(anchor=W)

        if HAS_TTKBOOTSTRAP:
            link_btn = ttk.Button(parent, text="View on GitHub",
                                  command=lambda: webbrowser.open(f"https://github.com/{GITHUB_REPO}"),
                                  bootstyle="link")
        else:
            link_btn = ttk.Button(parent, text="View on GitHub",
                                  command=lambda: webbrowser.open(f"https://github.com/{GITHUB_REPO}"))
        link_btn.pack(anchor=W, pady=5)

    def _save(self):
        """Save all settings."""
        # Save API keys list
        api_keys_list = []
        for row in self.api_rows:
            model = row['model_var'].get().strip()
            key = row['key_var'].get().strip()
            # Don't save placeholder as model name
            model_placeholder = row.get('model_placeholder', 'gemini-2.0-flash')
            if model == model_placeholder:
                model = ''
            api_keys_list.append({'model_name': model, 'api_key': key})
        self.config.set_api_keys(api_keys_list)

        # Save all hotkeys
        hotkeys = {}

        # 1. Default languages
        for lang, entry_var in self.hotkey_entries.items():
            value = entry_var.get().strip()
            if value and value != "Press keys...":
                hotkeys[lang] = value

        # 2. Custom languages
        for row in self.custom_rows:
            lang = row['lang_var'].get().strip()
            value = row['hotkey_var'].get().strip()
            if lang and value and value != "Press keys...":
                hotkeys[lang] = value

        self.config.set_hotkeys(hotkeys)

        # Save general settings
        self.config.set_autostart(self.autostart_var.get())
        self.config.set_check_updates(self.updates_var.get())

        if self.on_save_callback:
            self.on_save_callback()

    def _restore_defaults(self):
        """Restore all settings to defaults (except API keys)."""
        # Restore default hotkeys
        # Only for default languages
        for lang, entry_var in self.hotkey_entries.items():
            default_hotkey = self.config.DEFAULT_HOTKEYS.get(lang, "")
            entry_var.set(default_hotkey)

        # Note: We don't delete custom rows here to avoid data loss,
        # but user can delete them manually.

        # Restore general settings
        self.autostart_var.set(False)
        self.updates_var.set(False)

    def _check_for_updates_click(self):
        """Handle Check for updates button click."""
        self.check_update_btn.config(state='disabled')
        self.update_status_label.config(text="Checking...")

        def check_async():
            try:
                result = check_for_updates()
                self.window.after(0, lambda: self._show_update_result(result))
            except Exception as e:
                self.window.after(0, lambda: self._show_update_result({'error': str(e)}))

        threading.Thread(target=check_async, daemon=True).start()

    def _show_update_result(self, result):
        """Show update check result."""
        self.check_update_btn.config(state='normal')

        if result.get('error'):
            self.update_status_label.config(text=f"Error: {result['error']}", foreground='red')
        elif result.get('available'):
            new_version = result['version']
            exe_url = result.get('exe_url')
            self.update_status_label.config(text=f"v{new_version} available!", foreground='green')

            # Store for later use
            self._pending_update = result

            # Check if auto-update is possible (exe version and exe_url available)
            is_exe = getattr(sys, 'frozen', False)

            if is_exe and exe_url:
                # Can auto-update
                if HAS_TTKBOOTSTRAP:
                    answer = Messagebox.yesno(
                        f"A new version v{new_version} is available!\n\n"
                        f"Current version: v{VERSION}\n\n"
                        f"Do you want to download and install the update?\n"
                        f"The application will restart automatically.",
                        title="Update Available",
                        parent=self.window
                    )
                    if answer == "Yes":
                        self._start_download_update(exe_url, new_version)
                else:
                    from tkinter import messagebox
                    answer = messagebox.askyesno(
                        "Update Available",
                        f"A new version v{new_version} is available!\n\n"
                        f"Current version: v{VERSION}\n\n"
                        f"Do you want to download and install the update?\n"
                        f"The application will restart automatically.",
                        parent=self.window
                    )
                    if answer:
                        self._start_download_update(exe_url, new_version)
            else:
                # Running from source or no exe in release - open download page
                msg = f"A new version v{new_version} is available!\n\nCurrent version: v{VERSION}\n\n"
                if not is_exe:
                    msg += "You're running from source code.\n"
                msg += "Do you want to open the download page?"

                if HAS_TTKBOOTSTRAP:
                    answer = Messagebox.yesno(msg, title="Update Available", parent=self.window)
                    if answer == "Yes":
                        webbrowser.open(result['url'])
                else:
                    from tkinter import messagebox
                    answer = messagebox.askyesno("Update Available", msg, parent=self.window)
                    if answer:
                        webbrowser.open(result['url'])
        else:
            self.update_status_label.config(text=f"You're up to date (v{VERSION})", foreground='gray')

    def _start_download_update(self, exe_url: str, new_version: str):
        """Start downloading the update with progress dialog."""
        # Create progress dialog
        self.progress_window = tk.Toplevel(self.window)
        self.progress_window.title("Downloading Update")
        self.progress_window.geometry("400x150")
        self.progress_window.resizable(False, False)
        self.progress_window.transient(self.window)
        self.progress_window.grab_set()

        # Center
        self.progress_window.update_idletasks()
        x = self.window.winfo_x() + (self.window.winfo_width() - 400) // 2
        y = self.window.winfo_y() + (self.window.winfo_height() - 150) // 2
        self.progress_window.geometry(f"+{x}+{y}")

        frame = ttk.Frame(self.progress_window, padding=20)
        frame.pack(fill=BOTH, expand=True)

        ttk.Label(frame, text=f"Downloading AI Translator v{new_version}...",
                  font=('Segoe UI', 10, 'bold')).pack(anchor=W)

        self.progress_label = ttk.Label(frame, text="Starting download...")
        self.progress_label.pack(anchor=W, pady=(10, 5))

        if HAS_TTKBOOTSTRAP:
            self.progress_bar = ttk.Progressbar(frame, length=350, mode='determinate',
                                                 bootstyle="success-striped")
        else:
            self.progress_bar = ttk.Progressbar(frame, length=350, mode='determinate')
        self.progress_bar.pack(fill=X, pady=5)

        self.progress_percent = ttk.Label(frame, text="0%")
        self.progress_percent.pack(anchor='e')

        # Start download in thread
        def download_thread():
            def progress_callback(percent, downloaded, total):
                self.window.after(0, lambda: self._update_progress(percent, downloaded, total))

            result = download_and_install_update(exe_url, new_version, progress_callback)
            self.window.after(0, lambda: self._download_complete(result, new_version))

        threading.Thread(target=download_thread, daemon=True).start()

    def _update_progress(self, percent, downloaded, total):
        """Update progress bar."""
        if hasattr(self, 'progress_bar') and self.progress_window.winfo_exists():
            self.progress_bar['value'] = percent
            self.progress_percent.config(text=f"{percent}%")

            # Format size
            downloaded_mb = downloaded / (1024 * 1024)
            total_mb = total / (1024 * 1024)
            self.progress_label.config(text=f"Downloaded: {downloaded_mb:.1f} MB / {total_mb:.1f} MB")

    def _download_complete(self, result, new_version):
        """Handle download completion."""
        if hasattr(self, 'progress_window') and self.progress_window.winfo_exists():
            self.progress_window.destroy()

        if result.get('success'):
            # Ask to install now
            if HAS_TTKBOOTSTRAP:
                answer = Messagebox.yesno(
                    f"Download complete!\n\n"
                    f"AI Translator v{new_version} is ready to install.\n\n"
                    f"The application will close and restart automatically.\n"
                    f"Install now?",
                    title="Install Update",
                    parent=self.window
                )
                if answer == "Yes":
                    self._execute_update(result['script_path'])
            else:
                from tkinter import messagebox
                answer = messagebox.askyesno(
                    "Install Update",
                    f"Download complete!\n\n"
                    f"AI Translator v{new_version} is ready to install.\n\n"
                    f"The application will close and restart automatically.\n"
                    f"Install now?",
                    parent=self.window
                )
                if answer:
                    self._execute_update(result['script_path'])
        else:
            # Download failed
            error_msg = result.get('error', 'Unknown error')
            self.update_status_label.config(text="Download failed", foreground='red')

            if HAS_TTKBOOTSTRAP:
                Messagebox.show_error(
                    f"Failed to download update:\n\n{error_msg}\n\n"
                    f"Please try again or download manually from GitHub.",
                    title="Download Failed",
                    parent=self.window
                )
            else:
                from tkinter import messagebox
                messagebox.showerror(
                    "Download Failed",
                    f"Failed to download update:\n\n{error_msg}\n\n"
                    f"Please try again or download manually from GitHub.",
                    parent=self.window
                )

    def _execute_update(self, script_path: str):
        """Execute update and close application."""
        self.update_status_label.config(text="Installing update...", foreground='blue')

        # Close settings window
        self.window.destroy()

        # Execute update script (this will handle app restart)
        execute_update(script_path)

        # Exit the application - the batch script will restart it
        # Find the main app and quit
        try:
            # Get root window and quit
            root = self.window.master if hasattr(self, 'window') else None
            if root:
                root.after(500, lambda: os._exit(0))
            else:
                os._exit(0)
        except Exception:
            os._exit(0)  # Force exit even on error
