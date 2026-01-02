"""拡張スクレイパーのデバッグ - 列マッピング確認"""
import sys
import re
sys.stdout.reconfigure(line_buffering=True)

print("Starting enhanced debug...", flush=True)

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

options = Options()
options.add_argument('--headless')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')

print("Creating driver...", flush=True)
driver = webdriver.Chrome(options=options)

try:
    race_id = "202406050811"  # 有馬記念2024
    url = f"https://db.netkeiba.com/race/{race_id}/"
    
    print(f"Navigating to {url}", flush=True)
    driver.get(url)
    
    import time
    time.sleep(2)
    
    print(f"Page title: {driver.title}", flush=True)
    
    # レース結果テーブル
    result_table = driver.find_element(By.CSS_SELECTOR, 'table.race_table_01')
    rows = result_table.find_elements(By.CSS_SELECTOR, 'tr')
    
    print(f"\nFound {len(rows)} rows", flush=True)
    
    # ヘッダー
    headers = rows[0].find_elements(By.CSS_SELECTOR, 'th')
    print(f"Headers ({len(headers)}):", flush=True)
    for i, h in enumerate(headers):
        print(f"  {i}: {h.text.strip()[:10]}", flush=True)
    
    # 最初のデータ行
    if len(rows) > 1:
        cols = rows[1].find_elements(By.CSS_SELECTOR, 'td')
        print(f"\nFirst data row ({len(cols)} columns):", flush=True)
        for i, col in enumerate(cols):
            text = col.text.strip()[:20] if col.text else "(empty)"
            print(f"  {i}: {text}", flush=True)
        
        # 馬リンクを探す
        print("\n=== Links in row ===", flush=True)
        links = rows[1].find_elements(By.CSS_SELECTOR, 'a')
        for link in links[:5]:
            href = link.get_attribute('href')
            text = link.text.strip()[:15]
            print(f"  {text}: {href}", flush=True)
            
            # 馬ID抽出テスト
            if '/horse/' in href:
                match = re.search(r'/horse/(\w+)', href)
                if match:
                    print(f"    -> Horse ID: {match.group(1)}", flush=True)
            
            # 騎手ID抽出テスト  
            if '/jockey/' in href:
                match = re.search(r'/jockey/(\w+)', href)
                if match:
                    print(f"    -> Jockey ID: {match.group(1)}", flush=True)
    
    # レース情報
    print("\n=== Race Info ===", flush=True)
    try:
        info = driver.find_element(By.CSS_SELECTOR, '.data_intro')
        print(f"data_intro: {info.text[:100]}", flush=True)
    except:
        print("data_intro not found", flush=True)
        
    try:
        diary = driver.find_element(By.CSS_SELECTOR, 'div.race_head_info')
        print(f"race_head_info: {diary.text[:100]}", flush=True)
    except:
        print("race_head_info not found", flush=True)

finally:
    driver.quit()
    print("\nDone.", flush=True)
