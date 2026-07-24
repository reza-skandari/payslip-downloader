"""
Imperial Payslip Downloader — GUI entry point.
Uses downloader.py (Playwright) for all browser interaction.
Build with build.bat to produce a standalone .exe.
"""

import os
import sys
import logging
import threading
import subprocess
from pathlib import Path
from datetime import date
from calendar import monthrange
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv
from tkinter import filedialog

import customtkinter as ctk

# ── Browser path: next to the exe (frozen) or next to this script (dev) ──────
if getattr(sys, "frozen", False):
    _BASE = Path(sys.executable).parent
else:
    _BASE = Path(__file__).parent

_BROWSERS_PATH = _BASE / ".playwright-browsers"
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_BROWSERS_PATH)

load_dotenv(_BASE / ".env")

import downloader as dl
from downloader import (
    PORTAL_URL, DOWNLOAD_DIR, MS_USERNAME,
    months_in_range, handle_ms_login, select_year, download_month,
)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


def _year_options():
    this_year = date.today().year
    return [str(y) for y in range(2010, this_year + 1)]


def _month_options():
    return [f"{m:02d}" for m in range(1, 13)]


# ── Logging bridge ────────────────────────────────────────────────────────────

class TextHandler(logging.Handler):
    def __init__(self, widget: ctk.CTkTextbox):
        super().__init__()
        self._widget = widget

    def emit(self, record):
        msg = self.format(record) + "\n"
        self._widget.after(0, self._append, msg)

    def _append(self, msg: str):
        self._widget.configure(state="normal")
        self._widget.insert("end", msg)
        self._widget.see("end")
        self._widget.configure(state="disabled")


# ── Main window ───────────────────────────────────────────────────────────────

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Imperial Payslip Downloader")
        self.geometry("640x580")
        self.resizable(True, True)
        self._cookies = None  # reused across download runs
        self._build_ui()
        self._setup_logging()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)
        pad = {"padx": 16, "pady": 6}

        # ── Date range ────────────────────────────────────────────────────────
        date_frame = ctk.CTkFrame(self)
        date_frame.grid(row=0, column=0, sticky="ew", **pad)
        date_frame.grid_columnconfigure((1, 3), weight=1)

        ctk.CTkLabel(date_frame, text="Start month:").grid(
            row=0, column=0, padx=(12, 6), pady=10, sticky="w")
        self._start_year  = self._combo(date_frame, _year_options(),  row=0, col=1)
        ctk.CTkLabel(date_frame, text="–").grid(row=0, column=2, padx=4)
        self._start_month = self._combo(date_frame, _month_options(), row=0, col=3, width=80)

        ctk.CTkLabel(date_frame, text="End month:").grid(
            row=1, column=0, padx=(12, 6), pady=(0, 10), sticky="w")
        self._end_year  = self._combo(date_frame, _year_options(),  row=1, col=1)
        ctk.CTkLabel(date_frame, text="–").grid(row=1, column=2, padx=4)
        self._end_month = self._combo(date_frame, _month_options(), row=1, col=3, width=80)

        # Default: last 12 months
        today = date.today()
        self._end_year.set(str(today.year))
        self._end_month.set(f"{today.month:02d}")
        prev = today.replace(day=1) - relativedelta(months=11)
        self._start_year.set(str(prev.year))
        self._start_month.set(f"{prev.month:02d}")

        # ── Output folder ─────────────────────────────────────────────────────
        out_frame = ctk.CTkFrame(self)
        out_frame.grid(row=1, column=0, sticky="ew", **pad)
        out_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(out_frame, text="Save to:").grid(
            row=0, column=0, padx=(12, 6), pady=(10, 4), sticky="w")

        inner = ctk.CTkFrame(out_frame, fg_color="transparent")
        inner.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 10))
        inner.grid_columnconfigure(0, weight=1)

        self._out_var = ctk.StringVar(value=str(Path(DOWNLOAD_DIR).resolve()))
        ctk.CTkEntry(inner, textvariable=self._out_var).grid(
            row=0, column=0, sticky="ew", padx=(0, 8))
        ctk.CTkButton(inner, text="Browse…", width=90, command=self._browse).grid(
            row=0, column=1)

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 6))
        btn_frame.grid_columnconfigure(0, weight=1)

        self._btn_download = ctk.CTkButton(
            btn_frame, text="Download Payslips", command=self._download)
        self._btn_download.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self._btn_cancel = ctk.CTkButton(
            btn_frame, text="Cancel", width=90,
            fg_color="gray30", hover_color="gray20",
            command=self._cancel)
        self._btn_cancel.grid(row=0, column=1)
        self._btn_cancel.grid_remove()  # hidden until download starts

        # ── Progress bar ──────────────────────────────────────────────────────
        self._progress = ctk.CTkProgressBar(self)
        self._progress.set(0)
        self._progress.grid(row=3, column=0, sticky="ew", padx=16, pady=(6, 0))

        # ── Status label ──────────────────────────────────────────────────────
        self._status_var = ctk.StringVar(value="Set your date range and click Download.")
        ctk.CTkLabel(self, textvariable=self._status_var,
                     text_color="gray", anchor="w").grid(
            row=4, column=0, sticky="ew", padx=16)

        # ── Log box ───────────────────────────────────────────────────────────
        self._log_box = ctk.CTkTextbox(
            self, state="disabled", font=("Consolas", 11), wrap="none")
        self._log_box.grid(row=5, column=0, sticky="nsew", padx=16, pady=(4, 16))
        self.grid_rowconfigure(5, weight=1)

    def _combo(self, parent, values, row, col, width=120):
        cb = ctk.CTkComboBox(parent, values=values, width=width)
        cb.grid(row=row, column=col, padx=(0, 12), pady=4, sticky="ew")
        if values:
            cb.set(values[-1])
        return cb

    def _setup_logging(self):
        handler = TextHandler(self._log_box)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%H:%M:%S"))
        root = logging.getLogger()
        root.setLevel(logging.INFO)
        root.addHandler(handler)

    def _browse(self):
        folder = filedialog.askdirectory(initialdir=self._out_var.get() or ".")
        if folder:
            self._out_var.set(folder)

    def _set_buttons(self, enabled: bool):
        self._btn_download.configure(state="normal" if enabled else "disabled")
        if enabled:
            self._btn_cancel.grid_remove()
        else:
            self._btn_cancel.configure(state="normal")
            self._btn_cancel.grid()

    def _cancel(self):
        self._cancel_event.set()
        self._status_var.set("Cancelling after current download…")
        self._btn_cancel.configure(state="disabled")

    def _download(self):
        start_str = f"{self._start_year.get()}-{self._start_month.get()}"
        end_str   = f"{self._end_year.get()}-{self._end_month.get()}"
        out_dir   = Path(self._out_var.get() or "./payslips")

        try:
            start_date = date.fromisoformat(start_str + "-01")
            end_date   = date.fromisoformat(end_str   + "-01")
        except ValueError:
            self._status_var.set("Invalid date range.")
            return

        # Auto-swap if start is after end
        if start_date > end_date:
            start_date, end_date = end_date, start_date
            self._start_year.set(str(start_date.year))
            self._start_month.set(f"{start_date.month:02d}")
            self._end_year.set(str(end_date.year))
            self._end_month.set(f"{end_date.month:02d}")

        self._cancel_event = threading.Event()
        self._set_buttons(False)
        self._status_var.set("Starting browser …")

        def run():
            log = logging.getLogger(__name__)
            from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

            months = list(months_in_range(start_date, end_date))
            total  = len(months)
            log.info("Range: %s → %s  (%d months)",
                     start_date.strftime("%B %Y"), end_date.strftime("%B %Y"), total)
            self.after(0, self._progress.set, 0)
            downloaded, skipped, errors = 0, 0, 0

            try:
                with sync_playwright() as p:
                    if self._cookies:
                        log.info("Reusing existing session (no login needed) …")
                        self.after(0, self._status_var.set, "Reusing session. Preparing downloads …")
                        cookies = self._cookies
                    else:
                        # Visible browser for login only
                        login_browser = p.chromium.launch(headless=False)
                        login_context = login_browser.new_context()
                        login_page    = login_context.new_page()

                        log.info("Opening portal …")
                        login_page.goto(PORTAL_URL, wait_until="domcontentloaded", timeout=60_000)
                        handle_ms_login(login_page)

                        if "/Payslip" not in login_page.url:
                            login_page.goto(PORTAL_URL, wait_until="domcontentloaded", timeout=60_000)
                            login_page.wait_for_load_state("networkidle", timeout=15_000)

                        cookies = login_context.cookies()
                        self._cookies = cookies
                        login_browser.close()
                        log.info("Login complete. Browser closed.")
                        self.after(0, self._status_var.set, "Logged in. Preparing downloads …")

                    # Headless browser with same cookies for all downloads
                    browser = p.chromium.launch(headless=True)
                    context = browser.new_context(accept_downloads=True)
                    context.add_cookies(cookies)
                    page    = context.new_page()

                    page.goto(PORTAL_URL, wait_until="domcontentloaded", timeout=60_000)
                    page.wait_for_load_state("networkidle", timeout=15_000)

                    # If session expired, the portal redirects to login
                    if "login" in page.url.lower() or "/Payslip" not in page.url:
                        self._cookies = None
                        log.error("Session expired — please click Download again to log in.")
                        self.after(0, self._status_var.set, "Session expired. Click Download to log in again.")
                        self.after(0, self._set_buttons, True)
                        browser.close()
                        return

                    log.info("Starting downloads …")
                    current_year = [None]

                    for i, month_date in enumerate(months):
                        if self._cancel_event.is_set():
                            log.info("Cancelled by user.")
                            break

                        pct = int((i / total) * 100)
                        label = month_date.strftime("%B %Y")
                        self.after(0, self._status_var.set,
                                   f"{pct}%  —  {label}  ({i + 1} of {total})")

                        try:
                            found = download_month(
                                page, month_date, out_dir,
                                dry_run=False, debug=False,
                                current_year=current_year,
                            )
                            if found:
                                downloaded += 1
                            else:
                                skipped += 1
                        except PWTimeout as e:
                            log.error("   Timed out on %s: %s", month_date.strftime("%B %Y"), e)
                            errors += 1
                        except Exception as e:
                            log.error("   Failed on %s: %s", month_date.strftime("%B %Y"), e)
                            errors += 1

                        self.after(0, self._progress.set, (i + 1) / total)

                    browser.close()

            except Exception as e:
                log.error("Unexpected error: %s", e)

            prefix  = "Cancelled." if self._cancel_event.is_set() else "Done."
            summary = f"{prefix}  Downloaded: {downloaded}  Skipped: {skipped}  Errors: {errors}"
            log.info("")
            log.info("=" * 60)
            log.info(summary)
            log.info("=" * 60)
            self.after(0, self._status_var.set, summary)
            self.after(0, self._set_buttons, True)

        threading.Thread(target=run, daemon=True).start()


# ── First-run setup window ────────────────────────────────────────────────────

class SetupWindow(ctk.CTk):
    """Shown on first launch to download the Playwright browser."""

    def __init__(self):
        super().__init__()
        self.title("Payslip Downloader — First Time Setup")
        self.geometry("460x180")
        self.resizable(False, False)

        ctk.CTkLabel(self, text="First time setup",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(24, 4))
        self._label = ctk.CTkLabel(
            self, text="Downloading browser components (~150 MB)…",
            text_color="gray")
        self._label.pack(pady=4)

        self._bar = ctk.CTkProgressBar(self, mode="indeterminate")
        self._bar.pack(fill="x", padx=32, pady=12)
        self._bar.start()

        threading.Thread(target=self._install, daemon=True).start()

    def _install(self):
        try:
            from playwright._impl._driver import compute_driver_executable
            driver_exe, driver_cli = compute_driver_executable()
            subprocess.run(
                [str(driver_exe), str(driver_cli), "install", "chromium"],
                env={**os.environ, "PLAYWRIGHT_BROWSERS_PATH": str(_BROWSERS_PATH)},
                check=True,
            )
            self.after(0, self.destroy)
        except Exception as e:
            self.after(0, self._label.configure,
                       {"text": f"Setup failed: {e}", "text_color": "red"})
            self.after(0, self._bar.stop)


def _browser_present() -> bool:
    return any(_BROWSERS_PATH.glob("chromium-*"))


def _ping_usage():
    try:
        import requests
        requests.get(
            "https://api.counterapi.dev/v1/rskandari-payslip/launches/up",
            timeout=5,
            verify=False,
        )
    except Exception:
        pass


def _close_splash():
    """Dismiss the PyInstaller splash screen if present (frozen exe only)."""
    try:
        import pyi_splash  # only exists inside a PyInstaller --splash build
        pyi_splash.close()
    except Exception:
        pass


def main():
    threading.Thread(target=_ping_usage, daemon=True).start()

    if not _browser_present():
        _close_splash()
        setup = SetupWindow()
        setup.mainloop()
        if not _browser_present():
            return  # setup failed — error already shown

    app = App()
    _close_splash()
    app.mainloop()


if __name__ == "__main__":
    main()
