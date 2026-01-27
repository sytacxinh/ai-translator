"""
Windows Authentication Module for AI Translator.
Supports Windows Hello (PIN/Fingerprint/Face) with password fallback.
"""
import asyncio
import ctypes
import logging
import os
import threading
import time
import tkinter as tk
from typing import Optional, Callable

try:
    import ttkbootstrap as ttk
    HAS_TTKBOOTSTRAP = True
except ImportError:
    from tkinter import ttk
    HAS_TTKBOOTSTRAP = False

# Windows Hello API - try multiple package names
HAS_WINDOWS_HELLO = False
UserConsentVerifier = None
UserConsentVerificationResult = None
UserConsentVerifierAvailability = None

# Try winsdk first (recommended)
try:
    from winsdk.windows.security.credentials.ui import (
        UserConsentVerifier,
        UserConsentVerificationResult,
        UserConsentVerifierAvailability
    )
    HAS_WINDOWS_HELLO = True
except ImportError:
    # Try winrt as fallback
    try:
        from winrt.windows.security.credentials.ui import (
            UserConsentVerifier,
            UserConsentVerificationResult,
            UserConsentVerifierAvailability
        )
        HAS_WINDOWS_HELLO = True
    except ImportError:
        logging.info("Windows Hello API not available - will use password only")

# Constants
LOGON32_LOGON_INTERACTIVE = 2
LOGON32_PROVIDER_DEFAULT = 0
MAX_ATTEMPTS = 5


class WindowsHelloAuth:
    """Windows Hello authentication using native API."""

    @staticmethod
    def is_available() -> bool:
        """Check if Windows Hello is available on this system."""
        if not HAS_WINDOWS_HELLO:
            return False
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                availability = loop.run_until_complete(
                    UserConsentVerifier.check_availability_async()
                )
                return availability == UserConsentVerifierAvailability.AVAILABLE
            finally:
                loop.close()
        except Exception as e:
            logging.warning(f"Windows Hello availability check failed: {e}")
            return False

    @staticmethod
    def verify_async(callback: Callable[[bool], None], message: str = "Verify your identity"):
        """
        Show Windows Hello dialog in background thread.
        Calls callback(True) on success, callback(False) on failure/cancel.
        """
        def run_verification():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(
                        UserConsentVerifier.request_verification_async(message)
                    )
                    success = result == UserConsentVerificationResult.VERIFIED
                    callback(success)
                finally:
                    loop.close()
            except Exception as e:
                logging.error(f"Windows Hello verification error: {e}")
                callback(False)

        thread = threading.Thread(target=run_verification, daemon=True)
        thread.start()


def verify_password(password: str) -> bool:
    """Verify Windows password using LogonUserW API."""
    if not password:
        return False

    try:
        username = os.environ.get('USERNAME', '')
        domain = os.environ.get('USERDOMAIN', '')

        if not username:
            return False

        advapi32 = ctypes.windll.advapi32
        kernel32 = ctypes.windll.kernel32

        token = ctypes.c_void_p()
        result = advapi32.LogonUserW(
            ctypes.c_wchar_p(username),
            ctypes.c_wchar_p(domain),
            ctypes.c_wchar_p(password),
            LOGON32_LOGON_INTERACTIVE,
            LOGON32_PROVIDER_DEFAULT,
            ctypes.byref(token)
        )

        if result:
            kernel32.CloseHandle(token)
            return True
        return False

    except Exception as e:
        logging.error(f"Password verification error: {e}")
        return False


class PasswordDialog:
    """Fallback password dialog with rate limiting."""

    def __init__(self, parent, title: str = "Enter Password"):
        self.result = False
        self.parent = parent
        self.failed_attempts = 0

        self._create_dialog(title)

    def _create_dialog(self, title: str):
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title(title)
        self.dialog.geometry("420x220")
        self.dialog.resizable(False, False)

        # Center and make modal
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() - 420) // 2
        y = (self.dialog.winfo_screenheight() - 220) // 2
        self.dialog.geometry(f"+{x}+{y}")

        self.dialog.transient(self.parent)
        self.dialog.grab_set()
        self.dialog.configure(bg='#2b2b2b')

        # Force to front
        self.dialog.attributes('-topmost', True)
        self.dialog.update()
        self.dialog.attributes('-topmost', False)

        self._create_widgets()
        self.password_entry.focus_set()
        self.dialog.protocol("WM_DELETE_WINDOW", self._cancel)
        self.dialog.wait_window()

    def _create_widgets(self):
        username = os.environ.get('USERNAME', 'User')

        main_frame = ttk.Frame(self.dialog, padding=25)
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="🔐 Enter Windows Password",
                  font=('Segoe UI', 13, 'bold')).pack(pady=(0, 15))

        ttk.Label(main_frame, text=f"Password for {username}:",
                  font=('Segoe UI', 10)).pack(anchor='w')

        self.password_var = tk.StringVar()
        self.password_entry = ttk.Entry(
            main_frame,
            textvariable=self.password_var,
            show="*",
            font=('Segoe UI', 12),
            width=30
        )
        self.password_entry.pack(fill=tk.X, pady=(5, 8))
        self.password_entry.bind('<Return>', lambda e: self._verify())

        self.error_label = ttk.Label(main_frame, text="",
                                      foreground='#dc3545',
                                      font=('Segoe UI', 9))
        self.error_label.pack(anchor='w')

        remaining = MAX_ATTEMPTS - self.failed_attempts
        self.attempts_label = ttk.Label(
            main_frame,
            text=f"Attempts remaining: {remaining}/{MAX_ATTEMPTS}",
            foreground='#888888',
            font=('Segoe UI', 9)
        )
        self.attempts_label.pack(anchor='w', pady=(3, 15))

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X)

        if HAS_TTKBOOTSTRAP:
            ttk.Button(btn_frame, text="Verify", command=self._verify,
                       bootstyle="primary", width=12).pack(side=tk.RIGHT, padx=(8, 0))
            ttk.Button(btn_frame, text="Cancel", command=self._cancel,
                       bootstyle="secondary", width=12).pack(side=tk.RIGHT)
        else:
            ttk.Button(btn_frame, text="Verify", command=self._verify,
                       width=12).pack(side=tk.RIGHT, padx=(8, 0))
            ttk.Button(btn_frame, text="Cancel", command=self._cancel,
                       width=12).pack(side=tk.RIGHT)

    def _verify(self):
        password = self.password_var.get()

        if not password:
            self.error_label.configure(text="Please enter your password")
            return

        self.error_label.configure(text="Verifying...", foreground='#888888')
        self.dialog.update()

        if verify_password(password):
            self.result = True
            self.dialog.destroy()
        else:
            self.failed_attempts += 1
            remaining = MAX_ATTEMPTS - self.failed_attempts

            self.attempts_label.configure(
                text=f"Attempts remaining: {remaining}/{MAX_ATTEMPTS}",
                foreground='#dc3545' if remaining <= 2 else '#888888'
            )

            if remaining <= 0:
                from tkinter import messagebox
                messagebox.showinfo(
                    "Too Many Attempts",
                    "Incorrect password.\n\n"
                    "Maximum attempts reached.\n"
                    "Please try again.",
                    parent=self.dialog
                )
                self.result = False
                self.dialog.destroy()
            else:
                self.error_label.configure(
                    text="Incorrect password.",
                    foreground='#dc3545'
                )
                self.password_var.set("")
                self.password_entry.focus_set()

    def _cancel(self):
        self.result = False
        self.dialog.destroy()


class WaitingDialog:
    """Dialog shown while waiting for Windows Hello."""

    def __init__(self, parent, message: str = "Waiting for Windows Hello...", on_cancel: Callable = None):
        self.parent = parent
        self.on_cancel = on_cancel
        self.cancelled = False

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Authenticating")
        self.dialog.geometry("400x180")
        self.dialog.resizable(False, False)

        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() - 400) // 2
        y = (self.dialog.winfo_screenheight() - 180) // 2
        self.dialog.geometry(f"+{x}+{y}")

        self.dialog.transient(parent)
        self.dialog.configure(bg='#2b2b2b')

        frame = ttk.Frame(self.dialog, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="🔐 Windows Hello",
                  font=('Segoe UI', 12, 'bold')).pack(pady=(5, 10))
        ttk.Label(frame, text=message, font=('Segoe UI', 10)).pack()
        ttk.Label(frame, text="(Use PIN, Fingerprint, or Face)",
                  font=('Segoe UI', 9), foreground='#888888').pack(pady=(5, 0))

        # Cancel button
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=(15, 0))
        if HAS_TTKBOOTSTRAP:
            ttk.Button(btn_frame, text="Cancel", command=self._cancel,
                       bootstyle="secondary", width=12).pack()
        else:
            ttk.Button(btn_frame, text="Cancel", command=self._cancel,
                       width=12).pack()

        self.dialog.protocol("WM_DELETE_WINDOW", self._cancel)

    def _cancel(self):
        """Handle cancel button click."""
        self.cancelled = True
        if self.on_cancel:
            self.on_cancel()
        self.close()

    def hide_for_windows_hello(self):
        """Hide this dialog so Windows Hello can appear on top."""
        if self.dialog.winfo_exists():
            # Minimize instead of withdraw to release focus
            self.dialog.iconify()

            # Allow any process to set foreground window
            try:
                user32 = ctypes.windll.user32

                # ASFW_ANY = -1: Allow any process to set foreground
                ASFW_ANY = -1
                user32.AllowSetForegroundWindow(ASFW_ANY)

                # Simulate Alt key press/release to unlock foreground window changes
                # This is a known trick to bypass Windows' foreground lock
                VK_MENU = 0x12  # Alt key
                KEYEVENTF_EXTENDEDKEY = 0x0001
                KEYEVENTF_KEYUP = 0x0002

                user32.keybd_event(VK_MENU, 0, KEYEVENTF_EXTENDEDKEY, 0)
                user32.keybd_event(VK_MENU, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)

                # Also try LockSetForegroundWindow to unlock
                LSFW_UNLOCK = 2
                user32.LockSetForegroundWindow(LSFW_UNLOCK)

            except Exception as e:
                logging.debug(f"Could not unlock foreground: {e}")

    def show(self):
        """Show the dialog again."""
        if self.dialog.winfo_exists():
            self.dialog.deiconify()
            self.dialog.lift()
            self.dialog.focus_force()

    def close(self):
        if self.dialog.winfo_exists():
            self.dialog.destroy()


def require_auth(parent) -> bool:
    """
    Authenticate user with Windows Hello (preferred) or password fallback.

    Flow:
    1. If Windows Hello available → show native dialog (PIN/Fingerprint/Face)
    2. If user verifies → return True
    3. If user cancels or WH not available → show password dialog
    4. Password dialog has 5-attempt soft limit

    Returns:
        True if authenticated successfully
    """
    # Try Windows Hello first
    if WindowsHelloAuth.is_available():
        result_container = {'result': None, 'done': False}

        def on_hello_result(success: bool):
            result_container['result'] = success
            result_container['done'] = True

        # Start Windows Hello in background
        WindowsHelloAuth.verify_async(
            on_hello_result,
            "AI Translator - Verify your identity to view API keys"
        )

        # Function to find and bring Windows Hello dialog to front
        def bring_windows_hello_to_front():
            try:
                user32 = ctypes.windll.user32

                # Allow any process to set foreground
                user32.AllowSetForegroundWindow(-1)  # ASFW_ANY

                # Unlock foreground
                user32.LockSetForegroundWindow(2)  # LSFW_UNLOCK

                # Find Windows Security dialog by class name
                # Common class names for Windows Hello/Security dialogs
                class_names = [
                    "Credential Dialog Xaml Host",
                    "Windows.UI.Core.CoreWindow",
                    "ApplicationFrameWindow"
                ]

                hwnd = None
                for class_name in class_names:
                    hwnd = user32.FindWindowW(class_name, None)
                    if hwnd:
                        break

                if hwnd:
                    # Bring to front
                    SW_SHOW = 5
                    SW_RESTORE = 9
                    user32.ShowWindow(hwnd, SW_RESTORE)
                    user32.SetForegroundWindow(hwnd)
                    user32.BringWindowToTop(hwnd)

                    # Also try SetWindowPos with HWND_TOPMOST
                    HWND_TOPMOST = -1
                    SWP_NOMOVE = 0x0002
                    SWP_NOSIZE = 0x0001
                    SWP_SHOWWINDOW = 0x0040
                    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                                       SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)

            except Exception as e:
                logging.debug(f"Could not bring Windows Hello to front: {e}")

        # Try to bring Windows Hello to front multiple times
        for i in range(5):
            time.sleep(0.1)
            bring_windows_hello_to_front()
            if result_container['done']:
                break

        # Wait for result (check periodically without blocking)
        while not result_container['done']:
            if not parent.winfo_exists():
                break
            try:
                parent.update()
                # Keep trying to bring Windows Hello to front
                bring_windows_hello_to_front()
            except tk.TclError:
                break
            time.sleep(0.1)

        if result_container['result']:
            return True
        # Windows Hello cancelled/failed → fall through to password

    # Fallback: Password dialog
    dialog = PasswordDialog(parent)
    return dialog.result


# Backward compatibility aliases
def verify_credential(credential: str) -> bool:
    """Backward compatibility: verify password."""
    return verify_password(credential)

def verify_windows_credential(credential: str) -> bool:
    """Backward compatibility: verify password."""
    return verify_password(credential)

def verify_windows_password(password: str) -> bool:
    """Backward compatibility: verify password."""
    return verify_password(password)

def has_windows_pin() -> bool:
    """Check if Windows Hello is available (renamed for clarity)."""
    return WindowsHelloAuth.is_available() if HAS_WINDOWS_HELLO else False


# Legacy class alias
class AuthDialog(PasswordDialog):
    """Legacy alias for PasswordDialog."""
    pass

class EnhancedAuthDialog(PasswordDialog):
    """Legacy alias for PasswordDialog."""
    pass
