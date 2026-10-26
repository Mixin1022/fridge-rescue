"""User-assisted login to the dedicated backend browser, while backend is stopped."""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parent
# Use Playwright's normal browser installation (or the caller's explicit override).
profile = root / 'work/cloud-data/browser-profile'
profile.mkdir(parents=True, exist_ok=True)
choice = input('1 Xiaohongshu / 2 Douyin: ').strip()
url = 'https://www.douyin.com/' if choice == '2' else 'https://www.xiaohongshu.com/'
with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(str(profile), headless=False)
    try:
        page = context.new_page()
        page.goto(url, wait_until='domcontentloaded', timeout=60000)
        input('Finish login in browser, then press Enter here to save and close: ')
    finally:
        context.close()
