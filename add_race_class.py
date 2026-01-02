"""
レースクラス情報を追加するスクリプト

JRAのクラス分け:
- GI, GII, GIII (重賞)
- リステッド
- オープン特別
- 3勝クラス
- 2勝クラス  
- 1勝クラス
- 新馬・未勝利
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


def get_race_class(driver, race_id):
    """レースページからクラス情報を取得"""
    url = f"https://db.netkeiba.com/race/{race_id}/"
    try:
        driver.get(url)
        time.sleep(0.5)
        
        # ページ全体のテキストを取得
        page_text = driver.find_element(By.TAG_NAME, 'body').text
        
        # クラスを判定（優先順位順）
        if '(G1)' in page_text or '（G1）' in page_text or '(GI)' in page_text or '（GI）' in page_text:
            return 'GI'
        elif '(G2)' in page_text or '（G2）' in page_text or '(GII)' in page_text or '（GII）' in page_text:
            return 'GII'
        elif '(G3)' in page_text or '（G3）' in page_text or '(GIII)' in page_text or '（GIII）' in page_text:
            return 'GIII'
        elif '(L)' in page_text or '（L）' in page_text or 'リステッド' in page_text:
            return 'リステッド'
        elif 'オープン' in page_text and '新馬' not in page_text and '未勝利' not in page_text:
            return 'オープン'
        elif '3勝クラス' in page_text or '1600万下' in page_text:
            return '3勝クラス'
        elif '2勝クラス' in page_text or '1000万下' in page_text:
            return '2勝クラス'
        elif '1勝クラス' in page_text or '500万下' in page_text:
            return '1勝クラス'
        elif '未勝利' in page_text:
            return '未勝利'
        elif '新馬' in page_text:
            return '新馬'
        else:
            return 'その他'
    except:
        return 'その他'


def update_race_files(data_dir, max_races=None):
    """レースファイルにクラス情報を追加"""
    print(f"Updating race files in {data_dir}...", flush=True)
    
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    driver = webdriver.Chrome(options=options)
    
    files = [f for f in os.listdir(data_dir) if f.startswith('race_') and f.endswith('.json')]
    print(f"Found {len(files)} files", flush=True)
    
    updated = 0
    
    try:
        for i, filename in enumerate(files):
            filepath = os.path.join(data_dir, filename)
            
            with open(filepath, 'r', encoding='utf-8') as f:
                race = json.load(f)
            
            # すでにクラス情報があればスキップ
            if race.get('race_info', {}).get('class'):
                continue
            
            race_id = race.get('race_id', '')
            if not race_id:
                continue
            
            race_class = get_race_class(driver, race_id)
            
            if 'race_info' not in race:
                race['race_info'] = {}
            race['race_info']['class'] = race_class
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(race, f, ensure_ascii=False, indent=2)
            
            updated += 1
            
            if (i + 1) % 10 == 0:
                print(f"  [{i+1}/{len(files)}] {race_class}", flush=True)
            
            if max_races and updated >= max_races:
                break
            
            time.sleep(0.3)
    finally:
        driver.quit()
    
    print(f"Updated {updated} files", flush=True)
    return updated


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--dir', default='data/2024_full')
    parser.add_argument('--max', type=int, default=None)
    
    args = parser.parse_args()
    
    update_race_files(args.dir, args.max)
