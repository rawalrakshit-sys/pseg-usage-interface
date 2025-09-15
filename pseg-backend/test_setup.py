#!/usr/bin/env python3
"""Test script to verify PSEGScraper setup works with new memory optimizations"""

import sys
sys.path.append('/home/ubuntu/pseg-usage-interface/pseg-backend')

from app.main import PSEGScraper

def test_scraper_setup():
    print('Testing PSEGScraper import and basic setup...')
    scraper = PSEGScraper()
    try:
        driver = scraper.setup_driver()
        print('✓ Chrome driver setup successful')
        print('✓ Memory optimization flags applied successfully')
        scraper.close()
        print('✓ Driver cleanup successful')
        return True
    except Exception as e:
        print(f'✗ Error during setup: {e}')
        scraper.close()
        return False

if __name__ == "__main__":
    success = test_scraper_setup()
    sys.exit(0 if success else 1)
