"""
簡易版拡張スクレイパー

馬の詳細ページへのアクセスを省略し、
レース結果ページから取得できる情報のみを収集

この方法なら1レースあたり数秒で完了
"""

import sys
import os
import json
import time
import re

sys.stdout.reconfigure(line_buffering=True)

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException


def get_race_with_ids(race_id: str, driver=None) -> dict:
    """
    レース結果ページから馬ID・騎手IDを含むデータを取得
    """
    close_driver = False
    
    if driver is None:
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        driver = webdriver.Chrome(options=options)
        close_driver = True
    
    url = f"https://db.netkeiba.com/race/{race_id}/"
    
    try:
        driver.get(url)
        time.sleep(1.5)
        
        # レース情報
        race_info = {}
        try:
            info = driver.find_element(By.CSS_SELECTOR, '.data_intro')
            info_text = info.text
            
            # コース
            course_match = re.search(r'(札幌|函館|福島|新潟|東京|中山|中京|京都|阪神|小倉)', info_text)
            if course_match:
                race_info['course'] = course_match.group(1)
            
            # 距離
            dist_match = re.search(r'(\d{4})m', info_text)
            if dist_match:
                race_info['distance'] = int(dist_match.group(1))
        except:
            pass
        
        # 出走馬
        horses = []
        result_table = driver.find_element(By.CSS_SELECTOR, 'table.race_table_01')
        rows = result_table.find_elements(By.CSS_SELECTOR, 'tr')[1:]  # ヘッダー除く
        
        for row in rows:
            cols = row.find_elements(By.CSS_SELECTOR, 'td')
            if len(cols) < 14:
                continue
            
            try:
                # 着順
                finish_text = cols[0].text.strip()
                if not finish_text.isdigit():
                    continue
                finish = int(finish_text)
                
                # 馬番
                num_text = cols[2].text.strip()
                if not num_text.isdigit():
                    continue
                num = int(num_text)
                
                # 馬名・ID
                horse_link = cols[3].find_element(By.CSS_SELECTOR, 'a')
                horse_name = horse_link.text.strip()
                horse_href = horse_link.get_attribute('href')
                horse_id_match = re.search(r'/horse/(\d+)', horse_href)
                horse_id = horse_id_match.group(1) if horse_id_match else ""
                
                # 騎手名・ID
                jockey_link = cols[6].find_element(By.CSS_SELECTOR, 'a')
                jockey_name = jockey_link.text.strip()
                jockey_href = jockey_link.get_attribute('href')
                jockey_match = re.search(r'/jockey/(?:result/recent/)?(\d+)', jockey_href)
                jockey_id = jockey_match.group(1) if jockey_match else ""
                
                # オッズ（12列目）
                odds = 0.0
                try:
                    odds = float(cols[12].text.strip())
                except:
                    pass
                
                # 人気（13列目）
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
                
            except Exception as e:
                continue
        
        if len(horses) < 2:
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
        print(f"Error: {e}", flush=True)
        return None
    finally:
        if close_driver:
            driver.quit()


def update_cache_with_ids():
    """既存キャッシュを馬ID・騎手ID付きで更新"""
    print("=== Updating Cache with Horse/Jockey IDs ===", flush=True)
    
    cache_dir = "data/cache"
    output_dir = "data/cache_with_ids"
    os.makedirs(output_dir, exist_ok=True)
    
    files = [f for f in os.listdir(cache_dir) 
             if f.startswith('race_') and f.endswith('.json')]
    
    print(f"Found {len(files)} cached races", flush=True)
    
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    driver = webdriver.Chrome(options=options)
    
    updated = 0
    
    try:
        for i, filename in enumerate(files):  # 全件処理
            race_id = filename.replace('race_', '').replace('.json', '')
            
            # 既に更新済みならスキップ
            output_path = os.path.join(output_dir, filename)
            if os.path.exists(output_path):
                print(f"  [{i+1}/{len(files)}] SKIP {race_id}", flush=True)
                continue
            
            print(f"  [{i+1}/{len(files)}] {race_id}...", end='', flush=True)
            
            data = get_race_with_ids(race_id, driver)
            
            if data:
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                print(f" {len(data['horses'])} horses", flush=True)
                updated += 1
            else:
                print(" FAILED", flush=True)
            
            time.sleep(0.5)
            
    finally:
        driver.quit()
    
    print(f"\nUpdated {updated} races", flush=True)
    return updated


if __name__ == "__main__":
    update_cache_with_ids()
