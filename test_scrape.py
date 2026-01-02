from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time
import re
from datetime import datetime, timedelta
import pytz

options = Options()
options.add_argument('--headless')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')

driver = webdriver.Chrome(options=options)

# JSTで今日から5日間の日付を取得
jst = pytz.timezone('Asia/Tokyo')
today = datetime.now(jst)
print(f"Today (JST): {today.strftime('%Y-%m-%d')}")

for i in range(5):
    target_date = (today + timedelta(days=i)).strftime('%Y%m%d')
    url = f"https://race.netkeiba.com/top/race_list.html?kaisai_date={target_date}"
    print(f"\nChecking {target_date}...")
    
    driver.get(url)
    time.sleep(2)
    
    # race_id を含むリンクを取得
    links = driver.find_elements(By.CSS_SELECTOR, 'a[href*="race_id="]')
    race_ids = set()
    for link in links:
        href = link.get_attribute('href') or ''
        match = re.search(r'race_id=(\d+)', href)
        if match:
            race_ids.add(match.group(1))
    
    print(f"  Found {len(race_ids)} unique race IDs")
    if race_ids:
        for rid in list(race_ids)[:3]:
            print(f"    Example: {rid}")

driver.quit()
