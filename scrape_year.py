"""
大規模データ収集

2024年1月〜12月のデータを収集
- 訓練: 1月〜9月
- テスト: 10月〜12月
"""

import sys
import os
import json
import time
import re
from datetime import datetime, timedelta

sys.stdout.reconfigure(line_buffering=True)

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options


def get_race_ids_for_date(driver, date_str):
    url = f"https://race.netkeiba.com/top/race_list.html?kaisai_date={date_str}"
    try:
        driver.get(url)
        time.sleep(1.0)
        race_links = driver.find_elements(By.CSS_SELECTOR, 'a[href*="race_id="]')
        race_ids = set()
        for link in race_links:
            href = link.get_attribute('href')
            match = re.search(r'race_id=(\d+)', href)
            if match:
                race_ids.add(match.group(1))
        return list(race_ids)
    except:
        return []


def get_race_data(driver, race_id):
    url = f"https://db.netkeiba.com/race/{race_id}/"
    try:
        driver.get(url)
        time.sleep(0.6)
        
        race_info = {}
        try:
            info = driver.find_element(By.CSS_SELECTOR, '.data_intro')
            info_text = info.text
            course_match = re.search(r'(札幌|函館|福島|新潟|東京|中山|中京|京都|阪神|小倉)', info_text)
            if course_match:
                race_info['course'] = course_match.group(1)
            dist_match = re.search(r'(\d{4})m', info_text)
            if dist_match:
                race_info['distance'] = int(dist_match.group(1))
        except:
            pass
        
        horses = []
        try:
            result_table = driver.find_element(By.CSS_SELECTOR, 'table.race_table_01')
            rows = result_table.find_elements(By.CSS_SELECTOR, 'tr')[1:]
            
            for row in rows:
                cols = row.find_elements(By.CSS_SELECTOR, 'td')
                if len(cols) < 14:
                    continue
                try:
                    finish_text = cols[0].text.strip()
                    if not finish_text.isdigit():
                        continue
                    finish = int(finish_text)
                    
                    num_text = cols[2].text.strip()
                    if not num_text.isdigit():
                        continue
                    num = int(num_text)
                    
                    horse_link = cols[3].find_element(By.CSS_SELECTOR, 'a')
                    horse_name = horse_link.text.strip()
                    horse_href = horse_link.get_attribute('href')
                    horse_id_match = re.search(r'/horse/(\d+)', horse_href)
                    horse_id = horse_id_match.group(1) if horse_id_match else ""
                    
                    jockey_link = cols[6].find_element(By.CSS_SELECTOR, 'a')
                    jockey_name = jockey_link.text.strip()
                    jockey_href = jockey_link.get_attribute('href')
                    jockey_match = re.search(r'/jockey/(?:result/recent/)?(\d+)', jockey_href)
                    jockey_id = jockey_match.group(1) if jockey_match else ""
                    
                    odds = 0.0
                    try:
                        odds = float(cols[12].text.strip())
                    except:
                        pass
                    
                    popularity = 0
                    pop_text = cols[13].text.strip()
                    if pop_text.isdigit():
                        popularity = int(pop_text)
                    
                    horses.append({
                        'num': num, 'name': horse_name, 'horse_id': horse_id,
                        'jockey': jockey_name, 'jockey_id': jockey_id,
                        'odds': odds, 'popularity': popularity, 'finish': finish
                    })
                except:
                    continue
        except:
            return None
        
        if len(horses) < 5:
            return None
        
        payouts = {'win': {}, 'place': {}}
        try:
            tables = driver.find_elements(By.CSS_SELECTOR, 'table.pay_table_01')
            for table in tables:
                rows = table.find_elements(By.CSS_SELECTOR, 'tr')
                for row in rows:
                    try:
                        header = row.find_element(By.CSS_SELECTOR, 'th')
                        header_text = header.text.strip()
                        cols = row.find_elements(By.CSS_SELECTOR, 'td')
                        if '単勝' in header_text and len(cols) >= 2:
                            nums = re.findall(r'\d+', cols[0].text.strip())
                            pays = re.findall(r'\d+', cols[1].text.strip().replace(',', ''))
                            for i, n in enumerate(nums):
                                if i < len(pays):
                                    payouts['win'][n] = int(pays[i])
                        elif '複勝' in header_text and len(cols) >= 2:
                            nums = re.findall(r'\d+', cols[0].text.strip())
                            pays = re.findall(r'\d+', cols[1].text.strip().replace(',', ''))
                            for i, n in enumerate(nums):
                                if i < len(pays):
                                    payouts['place'][n] = int(pays[i])
                    except:
                        continue
        except:
            pass
        
        return {
            'race_id': race_id, 'race_info': race_info,
            'horses': horses, 'payouts': payouts
        }
    except:
        return None


def scrape_year(year, output_dir, max_races=None):
    """1年分のレースをスクレイピング"""
    print(f"=== Scraping {year} ===", flush=True)
    
    os.makedirs(output_dir, exist_ok=True)
    
    # 土日のリストを生成
    start = datetime(year, 1, 1)
    end = datetime(year, 12, 31)
    
    dates = []
    current = start
    while current <= end:
        if current.weekday() in [5, 6]:
            dates.append(current.strftime("%Y%m%d"))
        current += timedelta(days=1)
    
    print(f"Target: {len(dates)} weekend days", flush=True)
    
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    driver = webdriver.Chrome(options=options)
    
    total = 0
    scraped = 0
    
    try:
        for i, date_str in enumerate(dates):
            print(f"[{i+1}/{len(dates)}] {date_str}...", end='', flush=True)
            
            race_ids = get_race_ids_for_date(driver, date_str)
            
            if not race_ids:
                print(" no races", flush=True)
                continue
            
            count = 0
            for race_id in race_ids:
                filepath = os.path.join(output_dir, f"race_{race_id}.json")
                if os.path.exists(filepath):
                    continue
                
                data = get_race_data(driver, race_id)
                if data:
                    with open(filepath, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    scraped += 1
                    count += 1
                
                total += 1
                if max_races and total >= max_races:
                    print(f" {count} (limit)", flush=True)
                    return scraped
                
                time.sleep(0.2)
            
            print(f" {count} new ({scraped} total)", flush=True)
    finally:
        driver.quit()
    
    print(f"\nTotal scraped: {scraped}", flush=True)
    return scraped


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--year', type=int, default=2024)
    parser.add_argument('--max', type=int, default=500)
    parser.add_argument('--output', default='data/2024_full')
    
    args = parser.parse_args()
    
    scrape_year(args.year, args.output, args.max)
