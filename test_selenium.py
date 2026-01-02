"""Selenium動作確認テスト"""
print("Starting Selenium test...")

import sys
sys.path.insert(0, '.')

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    print("Selenium imported successfully")
    
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    
    print("Creating Chrome driver...")
    driver = webdriver.Chrome(options=options)
    print("Driver created!")
    
    print("Navigating to test page...")
    driver.get("https://www.google.com")
    print(f"Page title: {driver.title}")
    
    driver.quit()
    print("Test passed!")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
