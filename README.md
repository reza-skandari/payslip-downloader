# Imperial College Payslip Downloader

A Windows desktop app that bulk-downloads payslips from the Imperial College London HR portal ([my.imperial.ac.uk/Payslip](https://my.imperial.ac.uk/Payslip/)).

Built because the portal only allows downloading one payslip at a time, with no date in the filename — and once Atlas replaces ICIS/My Imperial, historical payslips will no longer be directly accessible.

**→ Download the latest release:** https://reza-skandari.github.io/payslip-downloader/

---

## How it works

1. A browser window opens for Microsoft login (MFA supported — the script just waits).
2. Once logged in, the browser closes and a headless session takes over using the same cookies.
3. Payslips are downloaded for the selected date range and saved as named PDFs.

```
payslips/
├── 2024/
│   ├── 2024-Jan.pdf
│   ├── 2024-Feb.pdf
│   └── ...
└── 2025/
    └── ...
```

---

## Requirements (end users)

- Windows 10 or 11
- Imperial College Microsoft 365 account
- Internet connection

No Python, no browser pre-install. The app downloads Chromium (~150 MB) on first launch into its own folder.

---

## Building from source

### Prerequisites

- Python 3.10+
- Windows (PyInstaller produces platform-native executables)

### Steps

```bat
git clone https://github.com/reza-skandari/payslip-downloader.git
cd payslip-downloader

REM First time — installs dependencies and builds
build.bat

REM Subsequent builds (faster — reuses cache)
build.bat

REM Dev build (folder output, much faster — for testing changes)
build.bat --dev
```

Output: `dist\payslip-downloader.exe`

### Optional: `.env` file

Create a `.env` file (copy from `.env.example`) to pre-fill your email on the login page:

```
MS365_USERNAME=your.email@ic.ac.uk
```

Your password is **never** stored — you type it manually in the browser each time.

---

## Project structure

```
├── gui.py                  # GUI entry point (customtkinter)
├── downloader.py           # Playwright automation (login + downloads)
├── build.bat               # PyInstaller build script
├── splash.png              # Splash screen shown during exe startup
├── payslip-downloader.spec # PyInstaller spec (included for reproducibility)
├── requirements.txt        # Python dependencies
└── .env.example            # Template for optional config
```

---

## Security

- Password is never stored anywhere — login happens in a visible Microsoft browser window.
- MFA is fully supported — the script waits for the user to approve it.
- Session cookies are held in memory only and discarded when the app closes.
- No telemetry beyond an anonymous launch counter (a single integer, no personal data).
- CAPTCHA and MFA are never bypassed.

---

## Contributing

Bug reports and feature requests welcome — open an issue or email r.skandari@imperial.ac.uk.
