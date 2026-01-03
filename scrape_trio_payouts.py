"""
三連複払い戻しデータをスクレイピングして既存データに追加
"""

import os
import json
import time
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

def scrape_trio_payouts(data_dir, max_races=50):
    """既存のレースデータに三連複払い戻しを追加"""
    
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    
    driver = webdriver.Chrome(options=options)
    
    # 処理対象のレースファイル
    files = [f for f in os.listdir(data_dir) if f.endswith('.json')]
    
    updated = 0
    skipped = 0
    errors = 0
    
    for i, filename in enumerate(files[:max_races]):
        filepath = os.path.join(data_dir, filename)
        
        with open(filepath, 'r', encoding='utf-8') as f:
            race = json.load(f)
        
        # 既に三連複データがある場合はスキップ
        if race.get('payouts', {}).get('trio'):
            skipped += 1
            continue
        
        race_id = race.get('race_id', '')
        if not race_id:
            continue
        
        print(f"[{i+1}/{min(len(files), max_races)}] Scraping trio payout for {race_id}...", end=' ', flush=True)
        
        try:
            # 結果ページからオッズを取得
            url = f"https://db.netkeiba.com/race/{race_id}/"
            driver.get(url)
            time.sleep(1)
            
            # 払い戻しテーブルを探す
            page_text = driver.find_element(By.TAG_NAME, 'body').text
            
            # 三連複の払い戻しを探す
            # パターン: 三連複 X - Y - Z XXX,XXX または 三連複 X - Y - Z XXX
            trio_pattern = r'三連複\s*(\d+)\s*[－\-\s]+(\d+)\s*[－\-\s]+(\d+)\s+([\d,]+)'
            matches = re.findall(trio_pattern, page_text)
            
            if matches:
                trio_payouts = []
                for m in matches:
                    nums = sorted([int(m[0]), int(m[1]), int(m[2])])
                    payout = int(m[3].replace(',', ''))
                    trio_payouts.append({
                        'combo': nums,
                        'payout': payout
                    })
                
                if 'payouts' not in race:
                    race['payouts'] = {}
                race['payouts']['trio'] = trio_payouts
                
                # 保存
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(race, f, ensure_ascii=False, indent=2)
                
                print(f"OK {trio_payouts[0]['payout']:,}yen")
                updated += 1
            else:
                print("No trio data found")
                errors += 1
        
        except Exception as e:
            print(f"Error: {e}")
            errors += 1
        
        # レート制限
        time.sleep(0.5)
    
    driver.quit()
    
    print(f"\n完了: 更新={updated}, スキップ={skipped}, エラー={errors}")
    return updated


if __name__ == '__main__':
    import sys
    
    # コマンドライン引数でデータディレクトリを指定
    data_dir = sys.argv[1] if len(sys.argv) > 1 else 'data/2024_full'
    max_races = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    
    print(f"Data directory: {data_dir}")
    print(f"Max races: {max_races}")
    print()
    
    scrape_trio_payouts(data_dir, max_races)
