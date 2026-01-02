"""
大規模バックテスト - 2023-2024年

1. 指定期間のレースIDを取得
2. レースデータをスクレイピング
3. 統計データベース構築
4. V2 vs V3 比較検証
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
from selenium.common.exceptions import NoSuchElementException


def get_race_ids_for_date(driver, date_str: str) -> list:
    """
    指定日のレースIDリストを取得
    
    Args:
        date_str: YYYYMMDD形式
    """
    url = f"https://race.netkeiba.com/top/race_list.html?kaisai_date={date_str}"
    
    try:
        driver.get(url)
        time.sleep(1.5)
        
        # レースリンクを取得
        race_links = driver.find_elements(By.CSS_SELECTOR, 'a[href*="race_id="]')
        
        race_ids = set()
        for link in race_links:
            href = link.get_attribute('href')
            match = re.search(r'race_id=(\d+)', href)
            if match:
                race_ids.add(match.group(1))
        
        return list(race_ids)
        
    except Exception as e:
        print(f"  Error getting races for {date_str}: {e}", flush=True)
        return []


def get_race_data(driver, race_id: str) -> dict:
    """レースデータを取得（簡易版）"""
    url = f"https://db.netkeiba.com/race/{race_id}/"
    
    try:
        driver.get(url)
        time.sleep(1.0)
        
        # レース情報
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
        
        # 出走馬
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
                        'num': num,
                        'name': horse_name,
                        'horse_id': horse_id,
                        'jockey': jockey_name,
                        'jockey_id': jockey_id,
                        'odds': odds,
                        'popularity': popularity,
                        'finish': finish
                    })
                except:
                    continue
        except:
            return None
        
        if len(horses) < 5:
            return None
        
        # 払戻金
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
                            num_text = cols[0].text.strip()
                            pay_text = cols[1].text.strip().replace(',', '')
                            nums = re.findall(r'\d+', num_text)
                            pays = re.findall(r'\d+', pay_text)
                            for i, n in enumerate(nums):
                                if i < len(pays):
                                    payouts['win'][n] = int(pays[i])
                        
                        elif '複勝' in header_text and len(cols) >= 2:
                            num_text = cols[0].text.strip()
                            pay_text = cols[1].text.strip().replace(',', '')
                            nums = re.findall(r'\d+', num_text)
                            pays = re.findall(r'\d+', pay_text)
                            for i, n in enumerate(nums):
                                if i < len(pays):
                                    payouts['place'][n] = int(pays[i])
                    except:
                        continue
        except:
            pass
        
        return {
            'race_id': race_id,
            'race_info': race_info,
            'horses': horses,
            'payouts': payouts
        }
        
    except Exception as e:
        return None


def scrape_date_range(start_date: str, end_date: str, 
                     output_dir: str = "data/backtest_2023_2024",
                     max_races: int = None):
    """
    指定期間のレースをスクレイピング
    
    Args:
        start_date: YYYYMMDD
        end_date: YYYYMMDD
        max_races: 最大レース数（テスト用）
    """
    print(f"=== Scraping Races from {start_date} to {end_date} ===", flush=True)
    
    os.makedirs(output_dir, exist_ok=True)
    
    # 日付リストを生成
    start = datetime.strptime(start_date, "%Y%m%d")
    end = datetime.strptime(end_date, "%Y%m%d")
    
    dates = []
    current = start
    while current <= end:
        # 土日のみ（競馬開催日）
        if current.weekday() in [5, 6]:  # 土=5, 日=6
            dates.append(current.strftime("%Y%m%d"))
        current += timedelta(days=1)
    
    print(f"Target dates: {len(dates)} days (Sat/Sun only)", flush=True)
    
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    driver = webdriver.Chrome(options=options)
    
    total_races = 0
    scraped = 0
    
    try:
        for date_str in dates:
            # レースID取得
            print(f"\n{date_str}:", end='', flush=True)
            race_ids = get_race_ids_for_date(driver, date_str)
            
            if not race_ids:
                print(" no races", flush=True)
                continue
            
            print(f" {len(race_ids)} races", flush=True)
            
            for race_id in race_ids:
                # 既存チェック
                filepath = os.path.join(output_dir, f"race_{race_id}.json")
                if os.path.exists(filepath):
                    continue
                
                # スクレイピング
                data = get_race_data(driver, race_id)
                
                if data:
                    with open(filepath, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    scraped += 1
                    print(".", end='', flush=True)
                
                total_races += 1
                
                if max_races and total_races >= max_races:
                    print(f"\n\nReached max races limit: {max_races}", flush=True)
                    return scraped
                
                time.sleep(0.3)
            
    finally:
        driver.quit()
    
    print(f"\n\nScraped {scraped} new races (total processed: {total_races})", flush=True)
    return scraped


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', default='20241201', help='Start date YYYYMMDD')
    parser.add_argument('--end', default='20241222', help='End date YYYYMMDD')
    parser.add_argument('--max', type=int, default=100, help='Max races to scrape')
    
    args = parser.parse_args()
    
    scrape_date_range(args.start, args.end, max_races=args.max)
