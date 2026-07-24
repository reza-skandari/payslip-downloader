"""
Automated payslip downloader for my.imperial.ac.uk

Usage:
    python downloader.py --start 2024-01 --end 2024-12
    python downloader.py --start 2024-01 --end 2024-12 --dry-run
    python downloader.py --start 2024-01 --end 2024-12 --debug
"""

import os
import sys
import logging
import argparse
from pathlib import Path
from datetime import date
from calendar import monthrange
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv

_HERE = Path(__file__).parent
# PLAYWRIGHT_BROWSERS_PATH is set by gui.py before this module is imported.
# When running downloader.py directly (CLI), fall back to local .playwright-browsers.
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(_HERE / ".playwright-browsers"))

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

load_dotenv()

log = logging.getLogger(__name__)

PORTAL_URL    = os.getenv("PAYROLL_URL", "https://my.imperial.ac.uk/Payslip/").strip()
MS_USERNAME   = os.getenv("MS365_USERNAME", "").strip()
DOWNLOAD_DIR  = Path(os.getenv("DOWNLOAD_DIR", "./payslips"))

MS_LOGIN_DOMAIN  = "login.microsoftonline.com"
DOWNLOAD_PAYSLIP_BTN = '[id$="wtDownloadPayslip"]'


def months_in_range(start: date, end: date):
    current = start.replace(day=1)
    while current <= end.replace(day=1):
        yield current
        current += relativedelta(months=1)


def handle_ms_login(page):
    """If we land on Microsoft login, pre-fill the username and wait for the user to finish."""
    try:
        page.wait_for_url(f"**{MS_LOGIN_DOMAIN}**", timeout=8_000)
    except PWTimeout:
        return  # already past the login page

    if MS_USERNAME:
        log.info("Pre-filling username: %s", MS_USERNAME)
        page.fill("input[type='email']", MS_USERNAME)
        page.click("input[type='submit']")  # Next

    log.info("")
    log.info("=" * 60)
    log.info("Complete the login (password + MFA) in the browser window.")
    log.info("The script will continue automatically once you are in.")
    log.info("=" * 60)

    # Wait until redirected away from Microsoft login (MFA approved)
    page.wait_for_function(
        f"!window.location.href.includes('{MS_LOGIN_DOMAIN}')",
        timeout=180_000,
    )
    log.info("Logged in — now on: %s", page.url)


def select_year(page, year_str: str) -> bool:
    """
    Change the year dropdown. Returns False if the year isn't in the dropdown
    (no payslips recorded for that year), True otherwise.
    """
    year_select = page.get_by_label("Select a year to view")
    available = year_select.locator("option").all_text_contents()
    if year_str not in available:
        log.info("   Year %s not in portal dropdown — skipping", year_str)
        return False
    year_select.select_option(year_str)
    try:
        page.wait_for_function(
            """year => {
                const months = ['January','February','March','April','May','June',
                                'July','August','September','October','November','December'];
                const text = document.body.innerText;
                return months.some(m => text.includes(m + ' ' + year));
            }""",
            arg=year_str,
            timeout=15_000,
        )
    except PWTimeout:
        pass  # year exists in dropdown but may have no payslips
    return True


def download_month(page, month_date: date, download_dir: Path, dry_run: bool, debug: bool, current_year: list) -> bool:
    """
    Downloads the payslip for a single month.
    Returns True if a payslip was found, False if the month was not listed.
    """
    year_str    = str(month_date.year)
    last_day    = monthrange(month_date.year, month_date.month)[1]
    month_label = f"{last_day} {month_date.strftime('%B %Y')}"  # e.g. "30 April 2026"

    log.info("── %s", month_label)

    if current_year[0] != year_str:
        if not select_year(page, year_str):
            current_year[0] = year_str  # mark as visited so we don't retry
            return False
        current_year[0] = year_str

    if debug:
        shot = _HERE / f"debug_{month_date.strftime('%Y-%m')}.png"
        page.screenshot(path=str(shot), full_page=True)
        log.info("   [DEBUG] Screenshot → %s", shot)
        log.info("   [DEBUG] Page text:\n%s", page.locator("body").inner_text()[:1000])

    # Step 1: check the month is listed.
    month_link = page.get_by_text(month_label, exact=False)
    if month_link.count() == 0:
        log.info("   No payslip listed — skipping")
        return False

    if dry_run:
        log.info("   [DRY RUN] Would download")
        return True

    # Skip if already downloaded.
    if (download_dir / year_str / f"{month_date.strftime('%Y-%b')}.pdf").exists():
        log.info("   Already exists — skipping")
        return True

    # Step 2: click the month div (expands/selects the row).
    month_link.first.click()
    page.wait_for_load_state("networkidle", timeout=10_000)

    # Step 3: click the "View Full Payslip" button for this specific month.
    # Each button's onclick contains the period end-date e.g. Period=30-04-2026.
    # This uniquely identifies the right button among all visible rows.
    last_day   = monthrange(month_date.year, month_date.month)[1]
    period     = f"{last_day:02d}-{month_date.month:02d}-{month_date.year}"
    view_btn   = page.locator(f'input[value="View Full Payslip"][onclick*="Period={period}"]')
    view_btn.click()
    page.wait_for_load_state("networkidle", timeout=15_000)

    iframe = page.locator("iframe").content_frame
    iframe.get_by_role("button", name="Download").wait_for(timeout=15_000)

    save_dir = download_dir / year_str
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / f"{month_date.strftime('%Y-%b')}.pdf"

    with page.expect_download(timeout=30_000) as dl_info:
        iframe.get_by_role("button", name="Download").click()

    dl_info.value.save_as(save_path)
    log.info("   Saved → %s", save_path)

    iframe.get_by_role("link", name="Close").click()

    # Navigate back to the payslip list so the next iteration starts clean.
    page.goto(PORTAL_URL, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_load_state("networkidle", timeout=15_000)

    # Reset current_year so the dropdown is re-selected on the fresh page.
    current_year[0] = None

    return True


def parse_args():
    p = argparse.ArgumentParser(description="Download payslips from my.imperial.ac.uk")
    p.add_argument("--start",   required=True,       help="Start month YYYY-MM  e.g. 2024-01")
    p.add_argument("--end",     required=True,       help="End month   YYYY-MM  e.g. 2024-12")
    p.add_argument("--dry-run", action="store_true", help="Show what would be downloaded without saving")
    p.add_argument("--debug",   action="store_true", help="Save a screenshot + print page text after each year change")
    return p.parse_args()


def main():
    args = parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        start_date = date.fromisoformat(args.start + "-01")
        end_date   = date.fromisoformat(args.end   + "-01")
    except ValueError:
        log.error("Dates must be YYYY-MM format, e.g. --start 2024-01 --end 2024-12")
        sys.exit(1)

    if start_date > end_date:
        log.error("--start must be before or equal to --end")
        sys.exit(1)

    months = list(months_in_range(start_date, end_date))
    log.info("Range: %s → %s  (%d months)", start_date.strftime("%B %Y"), end_date.strftime("%B %Y"), len(months))
    if args.dry_run:
        log.info("DRY RUN — no files will be saved")

    with sync_playwright() as p:
        # ── Step 1: visible browser for login ────────────────────────────────
        login_browser = p.chromium.launch(headless=False)
        login_context = login_browser.new_context()
        login_page    = login_context.new_page()

        log.info("Navigating to payslips page …")
        login_page.goto(PORTAL_URL, wait_until="domcontentloaded", timeout=60_000)
        handle_ms_login(login_page)

        if "/Payslip" not in login_page.url:
            login_page.goto(PORTAL_URL, wait_until="domcontentloaded", timeout=60_000)
            login_page.wait_for_load_state("networkidle", timeout=15_000)

        cookies = login_context.cookies()
        login_browser.close()
        log.info("Login complete. Browser closed.")

        # ── Step 2: headless browser with the same cookies ────────────────────
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        context.add_cookies(cookies)
        page    = context.new_page()

        page.goto(PORTAL_URL, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_load_state("networkidle", timeout=15_000)

        log.info("Ready. Starting downloads …")

        downloaded, skipped, errors = 0, 0, 0
        current_year = [None]

        for month_date in months:
            try:
                found = download_month(
                    page, month_date, DOWNLOAD_DIR,
                    dry_run=args.dry_run, debug=args.debug,
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

        log.info("")
        log.info("=" * 60)
        log.info("Done.  Downloaded: %d  Skipped: %d  Errors: %d", downloaded, skipped, errors)
        log.info("=" * 60)

        browser.close()


if __name__ == "__main__":
    main()
