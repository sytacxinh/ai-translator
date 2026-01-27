"""
Toast Notification System for AI Translator.
Provides non-intrusive visual feedback for user actions.
"""
import tkinter as tk
from typing import Optional, List, Callable
from dataclasses import dataclass
from enum import Enum


class ToastType(Enum):
    """Types of toast notifications with associated styling."""
    SUCCESS = "success"
    ERROR = "error"
    INFO = "info"
    WARNING = "warning"


@dataclass
class ToastConfig:
    """Configuration for a toast type."""
    bg: str
    fg: str
    icon: str
    default_duration: int


class ToastManager:
    """
    Manages toast notifications with stacking and animations.

    Features:
    - Multiple toast types (success, error, info, warning)
    - Smooth fade in/out animations
    - Automatic stacking when multiple toasts
    - Click to dismiss
    - Auto-dismiss after duration

    Usage:
        toast = ToastManager(root)
        toast.show("Copied to clipboard!", ToastType.SUCCESS)
        toast.show("Translation failed", ToastType.ERROR, duration=5000)
    """

    CONFIGS = {
        ToastType.SUCCESS: ToastConfig("#28a745", "#ffffff", "✓", 2000),
        ToastType.ERROR: ToastConfig("#dc3545", "#ffffff", "✕", 4000),
        ToastType.INFO: ToastConfig("#17a2b8", "#ffffff", "ℹ", 2500),
        ToastType.WARNING: ToastConfig("#ffc107", "#212529", "⚠", 3000),
    }

    # Layout constants
    MARGIN_BOTTOM = 60   # Above taskbar
    MARGIN_RIGHT = 20    # From right edge
    TOAST_GAP = 10       # Gap between stacked toasts
    MAX_TOASTS = 5       # Maximum visible toasts

    # Animation settings
    FADE_IN_STEP = 0.1   # Alpha increment per frame
    FADE_OUT_STEP = 0.1  # Alpha decrement per frame
    FADE_IN_DELAY = 20   # ms between fade-in frames
    FADE_OUT_DELAY = 25  # ms between fade-out frames

    def __init__(self, root: tk.Tk) -> None:
        """
        Initialize ToastManager.

        Args:
            root: The root Tkinter window
        """
        self.root = root
        self.active_toasts: List[tk.Toplevel] = []
        self._dismiss_callbacks: dict = {}  # toast -> after_id for auto-dismiss

    def show(self,
             message: str,
             toast_type: ToastType = ToastType.INFO,
             duration: Optional[int] = None) -> tk.Toplevel:
        """
        Show a toast notification.

        Args:
            message: Text to display
            toast_type: Type of toast (affects color/icon)
            duration: Display duration in ms (None = use default for type)

        Returns:
            The toast Toplevel window (for testing/advanced use)
        """
        # Remove oldest toast if at max
        if len(self.active_toasts) >= self.MAX_TOASTS:
            oldest = self.active_toasts[0]
            self._dismiss(oldest, animate=False)

        config = self.CONFIGS[toast_type]
        duration = duration or config.default_duration

        # Create toast window
        toast = tk.Toplevel(self.root)
        toast.overrideredirect(True)
        toast.attributes('-topmost', True)
        toast.attributes('-alpha', 0.0)  # Start invisible for fade-in

        # Configure appearance
        toast.configure(bg=config.bg)

        # Content frame with padding
        frame = tk.Frame(toast, bg=config.bg, padx=20, pady=12)
        frame.pack(fill=tk.BOTH, expand=True)

        # Icon + Message
        text = f"{config.icon}  {message}"
        label = tk.Label(
            frame,
            text=text,
            bg=config.bg,
            fg=config.fg,
            font=('Segoe UI', 11),
            wraplength=300,  # Wrap long messages
            justify=tk.LEFT
        )
        label.pack()

        # Click to dismiss - bind to all widgets
        for widget in (toast, frame, label):
            widget.bind('<Button-1>', lambda e, t=toast: self._dismiss(t))

        # Calculate position
        toast.update_idletasks()
        self._position_toast(toast)

        # Add to active list
        self.active_toasts.append(toast)

        # Animate fade in, then schedule auto-dismiss
        self._fade_in(toast, callback=lambda: self._schedule_dismiss(toast, duration))

        return toast

    def show_success(self, message: str, duration: Optional[int] = None) -> tk.Toplevel:
        """Convenience method for success toast."""
        return self.show(message, ToastType.SUCCESS, duration)

    def show_error(self, message: str, duration: Optional[int] = None) -> tk.Toplevel:
        """Convenience method for error toast."""
        return self.show(message, ToastType.ERROR, duration)

    def show_info(self, message: str, duration: Optional[int] = None) -> tk.Toplevel:
        """Convenience method for info toast."""
        return self.show(message, ToastType.INFO, duration)

    def show_warning(self, message: str, duration: Optional[int] = None) -> tk.Toplevel:
        """Convenience method for warning toast."""
        return self.show(message, ToastType.WARNING, duration)

    def dismiss_all(self) -> None:
        """Dismiss all active toasts immediately."""
        for toast in self.active_toasts[:]:  # Copy list to avoid modification during iteration
            self._dismiss(toast, animate=False)

    def _position_toast(self, toast: tk.Toplevel) -> None:
        """Position toast at bottom-right, accounting for stack."""
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()

        toast_w = toast.winfo_reqwidth()
        toast_h = toast.winfo_reqheight()

        # Calculate Y based on existing toasts (stack from bottom)
        y_offset = self.MARGIN_BOTTOM
        for existing_toast in self.active_toasts:
            if existing_toast != toast and existing_toast.winfo_exists():
                try:
                    y_offset += existing_toast.winfo_reqheight() + self.TOAST_GAP
                except tk.TclError:
                    pass  # Toast was destroyed

        x = screen_w - toast_w - self.MARGIN_RIGHT
        y = screen_h - toast_h - y_offset

        toast.geometry(f"+{x}+{y}")

    def _schedule_dismiss(self, toast: tk.Toplevel, duration: int) -> None:
        """Schedule auto-dismiss after duration."""
        if toast.winfo_exists():
            after_id = toast.after(duration, lambda: self._dismiss(toast))
            self._dismiss_callbacks[toast] = after_id

    def _cancel_dismiss(self, toast: tk.Toplevel) -> None:
        """Cancel scheduled auto-dismiss."""
        if toast in self._dismiss_callbacks:
            try:
                toast.after_cancel(self._dismiss_callbacks[toast])
            except (tk.TclError, ValueError):
                pass  # Already cancelled or toast destroyed
            del self._dismiss_callbacks[toast]

    def _fade_in(self,
                 toast: tk.Toplevel,
                 callback: Optional[Callable] = None,
                 alpha: float = 0.0) -> None:
        """Animate fade in."""
        if not toast.winfo_exists():
            return

        alpha += self.FADE_IN_STEP
        if alpha <= 0.95:
            try:
                toast.attributes('-alpha', alpha)
                toast.after(self.FADE_IN_DELAY,
                           lambda: self._fade_in(toast, callback, alpha))
            except tk.TclError:
                pass  # Toast was destroyed
        else:
            try:
                toast.attributes('-alpha', 0.95)
            except tk.TclError:
                pass
            if callback:
                callback()

    def _fade_out(self,
                  toast: tk.Toplevel,
                  callback: Optional[Callable] = None,
                  alpha: float = 0.95) -> None:
        """Animate fade out."""
        if not toast.winfo_exists():
            if callback:
                callback()
            return

        alpha -= self.FADE_OUT_STEP
        if alpha > 0:
            try:
                toast.attributes('-alpha', alpha)
                toast.after(self.FADE_OUT_DELAY,
                           lambda: self._fade_out(toast, callback, alpha))
            except tk.TclError:
                if callback:
                    callback()
        else:
            if callback:
                callback()

    def _dismiss(self, toast: tk.Toplevel, animate: bool = True) -> None:
        """
        Dismiss a toast.

        Args:
            toast: The toast to dismiss
            animate: Whether to animate the dismissal
        """
        if toast not in self.active_toasts:
            return

        # Cancel any scheduled auto-dismiss
        self._cancel_dismiss(toast)

        # Remove from active list first to prevent re-dismiss
        self.active_toasts.remove(toast)

        def on_complete():
            try:
                if toast.winfo_exists():
                    toast.destroy()
            except tk.TclError:
                pass  # Already destroyed
            # Reposition remaining toasts
            self._reposition_all()

        if animate:
            self._fade_out(toast, callback=on_complete)
        else:
            on_complete()

    def _reposition_all(self) -> None:
        """Reposition all active toasts after one is dismissed."""
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()

        y_offset = self.MARGIN_BOTTOM
        for toast in self.active_toasts:
            if toast.winfo_exists():
                try:
                    toast_w = toast.winfo_reqwidth()
                    toast_h = toast.winfo_reqheight()

                    x = screen_w - toast_w - self.MARGIN_RIGHT
                    y = screen_h - toast_h - y_offset

                    toast.geometry(f"+{x}+{y}")
                    y_offset += toast_h + self.TOAST_GAP
                except tk.TclError:
                    pass  # Toast was destroyed during iteration
