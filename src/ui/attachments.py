"""
Attachment Area Widget for AI Translator.
Handles file and image attachments with drag-and-drop support.
"""
import os
import logging
import tkinter as tk
from tkinter import ttk, filedialog
from PIL import Image, ImageTk

try:
    from tkinterdnd2 import DND_FILES
    HAS_DND = True
except ImportError:
    HAS_DND = False

try:
    import ttkbootstrap
    HAS_TTKBOOTSTRAP = True
except ImportError:
    HAS_TTKBOOTSTRAP = False


class AttachmentArea(ttk.Frame):
    """Widget to display and manage attachments."""

    def __init__(self, parent, config, on_change=None):
        super().__init__(parent)
        self.config = config
        self.on_change = on_change
        self.attachments = []  # List of {'type': 'image'|'file', 'path': str}
        self.thumbnails = []   # Keep references to avoid GC

        self._create_ui()

    def _create_ui(self):
        """Create the UI layout."""
        # Top bar
        self.top_frame = ttk.Frame(self)
        self.top_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(self.top_frame, text="Attachments:", font=('Segoe UI', 9, 'bold')).pack(side=tk.LEFT)

        self.clear_btn = ttk.Button(self.top_frame, text="Clear Attachments", command=self.clear, width=15)
        # Pack clear_btn later when items exist

        # Container for items
        self.items_frame = ttk.Frame(self)
        self.items_frame.pack(fill=tk.BOTH, expand=True)

        # Add button (Menu dropdown) - style based on enabled features
        if HAS_TTKBOOTSTRAP:
            self.add_btn = ttk.Button(self.items_frame, text="+", command=self._show_add_menu, width=3)
        else:
            self.add_btn = ttk.Button(self.items_frame, text="+", command=self._show_add_menu, width=3)

        # Create Menu with icons
        self.add_menu = tk.Menu(self, tearoff=0, font=('Segoe UI', 10))

        # Update visibility and style based on current config
        self._update_add_button_style()

        # Register for drag-and-drop with tkinterdnd2 if available
        self._setup_dnd()

    def _setup_dnd(self):
        """Setup drag-and-drop bindings with tkinterdnd2."""
        if not HAS_DND:
            logging.debug("tkinterdnd2 not available, skipping DnD setup for AttachmentArea")
            return

        try:
            # Check if DnD methods are available on this widget
            if not hasattr(self, 'drop_target_register'):
                logging.debug("Widget does not have DnD methods, skipping")
                return

            # Register the entire frame as a drop target
            self.drop_target_register(DND_FILES)
            self.dnd_bind('<<DropEnter>>', self._on_drag_enter)
            self.dnd_bind('<<DropLeave>>', self._on_drag_leave)
            self.dnd_bind('<<Drop>>', self._on_drop)

            # Also register the items_frame for better drop area
            if hasattr(self.items_frame, 'drop_target_register'):
                self.items_frame.drop_target_register(DND_FILES)
                self.items_frame.dnd_bind('<<DropEnter>>', self._on_drag_enter)
                self.items_frame.dnd_bind('<<DropLeave>>', self._on_drag_leave)
                self.items_frame.dnd_bind('<<Drop>>', self._on_drop)

            logging.info("tkinterdnd2 drag-and-drop enabled for AttachmentArea")
        except Exception as e:
            logging.warning(f"Could not setup tkinterdnd2 for AttachmentArea: {e}")

    def _update_add_button_style(self):
        """Update the add button visibility and style based on config."""
        vision_enabled = self.config.get('vision_enabled', False)
        file_enabled = self.config.get('file_processing_enabled', False)

        # Always show button, but change style based on state
        if not vision_enabled and not file_enabled:
            # Gray/inactive style - no features enabled
            if HAS_TTKBOOTSTRAP:
                self.add_btn.configure(bootstyle="secondary")
            self.add_btn.pack(side=tk.LEFT, padx=(0, 5), anchor='n')
        else:
            # Light blue/active style - at least one feature enabled
            if HAS_TTKBOOTSTRAP:
                self.add_btn.configure(bootstyle="info")
            self.add_btn.pack(side=tk.LEFT, padx=(0, 5), anchor='n')

    def _update_add_button_visibility(self):
        """Alias for backwards compatibility."""
        self._update_add_button_style()

    def _show_add_menu(self):
        """Show the add menu with options based on enabled features."""
        self.add_menu.delete(0, tk.END)

        vision_enabled = self.config.get('vision_enabled', False)
        file_enabled = self.config.get('file_processing_enabled', False)

        if not vision_enabled and not file_enabled:
            # Show warning that no upload features are enabled
            self.add_menu.add_command(label="⚠ No upload features enabled", state='disabled')
            self.add_menu.add_separator()
            self.add_menu.add_command(label="Open Settings to enable", command=self._open_settings_hint)
        else:
            if vision_enabled:
                self.add_menu.add_command(label="📷  Upload Images", command=self._browse_images)

            if file_enabled:
                self.add_menu.add_command(label="📄  Upload Files (.txt, .docx, .srt)", command=self._browse_documents)

        # Position menu below button
        try:
            self.add_menu.tk_popup(self.add_btn.winfo_rootx(), self.add_btn.winfo_rooty() + self.add_btn.winfo_height())
        finally:
            self.add_menu.grab_release()

    def _open_settings_hint(self):
        """Hint to open settings - just shows a message for now."""
        from tkinter import messagebox
        messagebox.showinfo("Enable Upload Features",
                           "To enable upload features:\n\n"
                           "1. Open Settings from the system tray\n"
                           "2. Go to 'API Key' tab\n"
                           "3. Enable 'Upload Image Mode' or 'Upload File Mode'\n\n"
                           "Note: These options require a working API key.",
                           parent=self)

    def add_file(self, file_path, show_warning=False):
        """Add a file attachment."""
        if not os.path.exists(file_path):
            return False

        ext = os.path.splitext(file_path)[1].lower()
        is_image = ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp']
        is_supported_doc = ext in ['.txt', '.docx', '.srt', '.pdf']

        # Check permissions based on config
        vision_enabled = self.config.get('vision_enabled', False)
        file_enabled = self.config.get('file_processing_enabled', False)

        if is_image and not vision_enabled:
            if show_warning:
                from tkinter import messagebox
                messagebox.showwarning("Upload Image Disabled",
                                      "Upload Image Mode is not enabled.\n\n"
                                      "Please enable it in Settings > API Key tab.",
                                      parent=self)
            return False

        if not is_image and not file_enabled:
            if show_warning:
                from tkinter import messagebox
                messagebox.showwarning("Upload File Disabled",
                                      "Upload File Mode is not enabled.\n\n"
                                      "Please enable it in Settings > API Key tab.",
                                      parent=self)
            return False

        if not is_image and not is_supported_doc:
            if show_warning:
                from tkinter import messagebox
                messagebox.showwarning("Unsupported File",
                                      f"File type '{ext}' is not supported.\n\n"
                                      "Supported formats:\n"
                                      "• Images: .jpg, .jpeg, .png, .webp, .gif, .bmp\n"
                                      "• Documents: .txt, .docx, .srt",
                                      parent=self)
            return False

        # Add to list
        att_type = 'image' if is_image else 'file'
        self.attachments.append({'type': att_type, 'path': file_path})

        self._render_item(file_path, is_image)
        self._update_visibility()
        if self.on_change:
            self.on_change()
        return True

    def _render_item(self, file_path, is_image):
        """Render a single attachment item."""
        frame = ttk.Frame(self.items_frame, borderwidth=1, relief="solid")
        frame.pack(side=tk.LEFT, padx=5, anchor='n')

        # Content
        if is_image:
            try:
                img = Image.open(file_path)
                img.thumbnail((60, 60))
                photo = ImageTk.PhotoImage(img)
                self.thumbnails.append(photo)
                lbl = ttk.Label(frame, image=photo)
                lbl.pack(padx=2, pady=2)
            except:
                ttk.Label(frame, text="IMG").pack(padx=5, pady=15)
        else:
            # File icon/text
            ext = os.path.splitext(file_path)[1].lower()
            ttk.Label(frame, text=ext, font=('Segoe UI', 10, 'bold')).pack(padx=5, pady=5)
            name = os.path.basename(file_path)
            if len(name) > 10: name = name[:7] + "..."
            ttk.Label(frame, text=name, font=('Segoe UI', 7)).pack(padx=2, pady=(0, 2))

        # Remove button (overlay or below)
        # Simple 'x' button below
        x_btn = ttk.Label(frame, text="✕", foreground="red", cursor="hand2")
        x_btn.pack(side=tk.BOTTOM, pady=1)
        x_btn.bind("<Button-1>", lambda e, p=file_path: self._remove_item(p, frame))

    def _remove_item(self, path, widget):
        """Remove an attachment."""
        self.attachments = [a for a in self.attachments if a['path'] != path]
        widget.destroy()
        self._update_visibility()
        if self.on_change:
            self.on_change()

    def clear(self):
        """Clear all attachments."""
        self.attachments = []
        self.thumbnails = []
        for widget in self.items_frame.winfo_children():
            if widget != self.add_btn:
                widget.destroy()
        self._update_visibility()
        if self.on_change:
            self.on_change()

    def get_attachments(self):
        """Get list of attachments."""
        return self.attachments

    def _update_visibility(self):
        """Update UI state."""
        if self.attachments:
            self.clear_btn.pack(side=tk.RIGHT)
        else:
            self.clear_btn.pack_forget()

    def _browse_images(self):
        """Browse for images."""
        if not self.config.get('vision_enabled', False):
            from tkinter import messagebox
            messagebox.showwarning("Upload Image Disabled",
                                  "Upload Image Mode is not enabled.\n\n"
                                  "Please enable it in Settings > API Key tab.",
                                  parent=self)
            return

        filetypes = [("Images", "*.jpg *.jpeg *.png *.webp *.gif *.bmp")]
        files = filedialog.askopenfilenames(filetypes=filetypes, parent=self)
        for f in files:
            self.add_file(f, show_warning=True)

    def _browse_documents(self):
        """Browse for documents."""
        if not self.config.get('file_processing_enabled', False):
            from tkinter import messagebox
            messagebox.showwarning("Upload File Disabled",
                                  "Upload File Mode is not enabled.\n\n"
                                  "Please enable it in Settings > API Key tab.",
                                  parent=self)
            return

        filetypes = [("Documents", "*.txt *.docx *.srt")]
        files = filedialog.askopenfilenames(filetypes=filetypes, parent=self)
        for f in files:
            self.add_file(f, show_warning=True)

    def _browse_files(self):
        """Deprecated, kept for compatibility if needed."""
        self._show_add_menu()

    def _on_drag_enter(self, event):
        """Visual feedback when dragging over the drop zone."""
        logging.debug("Drag enter detected on AttachmentArea")
        try:
            if HAS_TTKBOOTSTRAP:
                self.add_btn.configure(bootstyle="success")
            else:
                self.add_btn.configure(text="↓", relief="sunken")
            # Change background to indicate drop zone
            self.configure(style="DragOver.TFrame")
        except Exception as e:
            logging.debug(f"Error in drag_enter: {e}")
        return event.action

    def _on_drag_leave(self, event):
        """Reset visual feedback when leaving drop zone."""
        logging.debug("Drag leave detected on AttachmentArea")
        try:
            self._update_add_button_style()
            if not HAS_TTKBOOTSTRAP:
                self.add_btn.configure(text="+", relief="raised")
            # Reset background
            self.configure(style="TFrame")
        except Exception as e:
            logging.debug(f"Error in drag_leave: {e}")
        return event.action

    def _on_drop(self, event):
        """Handle drag and drop."""
        logging.info(f"Drop detected on AttachmentArea, data: {event.data[:100] if event.data else 'None'}...")

        # Reset visual feedback
        self._update_add_button_style()
        if not HAS_TTKBOOTSTRAP:
            self.add_btn.configure(text="+", relief="raised")
        self.configure(style="TFrame")

        if not event.data:
            logging.warning("Drop event has no data")
            return

        # Parse file paths (tkinterdnd2 returns a string list)
        # Handling braces {} for paths with spaces
        raw_data = event.data
        paths = []

        # Basic parsing for Windows paths in DND
        if '{' in raw_data:
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

        # Track rejected files to show warning once
        rejected_images = []
        rejected_files = []
        rejected_unsupported = []

        vision_enabled = self.config.get('vision_enabled', False)
        file_enabled = self.config.get('file_processing_enabled', False)

        for path in paths:
            if not os.path.exists(path):
                continue

            ext = os.path.splitext(path)[1].lower()
            is_image = ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp']
            is_supported_doc = ext in ['.txt', '.docx', '.srt', '.pdf']

            if is_image:
                if vision_enabled:
                    self.add_file(path)
                else:
                    rejected_images.append(os.path.basename(path))
            elif is_supported_doc:
                if file_enabled:
                    self.add_file(path)
                else:
                    rejected_files.append(os.path.basename(path))
            else:
                rejected_unsupported.append(os.path.basename(path))

        # Show combined warning if any files were rejected
        if rejected_images or rejected_files or rejected_unsupported:
            from tkinter import messagebox
            msg_parts = []
            if rejected_images:
                msg_parts.append(f"Images rejected (Upload Image Mode disabled):\n• " + "\n• ".join(rejected_images[:3]))
                if len(rejected_images) > 3:
                    msg_parts[-1] += f"\n  ... and {len(rejected_images) - 3} more"
            if rejected_files:
                msg_parts.append(f"Files rejected (Upload File Mode disabled):\n• " + "\n• ".join(rejected_files[:3]))
                if len(rejected_files) > 3:
                    msg_parts[-1] += f"\n  ... and {len(rejected_files) - 3} more"
            if rejected_unsupported:
                msg_parts.append(f"Unsupported files:\n• " + "\n• ".join(rejected_unsupported[:3]))
                if len(rejected_unsupported) > 3:
                    msg_parts[-1] += f"\n  ... and {len(rejected_unsupported) - 3} more"

            messagebox.showwarning("Some Files Rejected", "\n\n".join(msg_parts), parent=self)

        # Reset button style after drop
        self._update_add_button_style()