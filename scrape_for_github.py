"""
GitHub Actions用スクレイピングスクリプト
毎朝6時JSTに実行され、レースデータを更新する
"""

import os
import json
import re
import time
from datetime import datetime, timedelta, timezone
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

# 日本時間
JST = timezone(timedelta(hours=9))

# 競馬場コード→名前
TRACK_NAMES = {
    '01': '札幌', '02': '函館', '03': '福島', '04': '新潟', '05': '東京',
    '06': '中山', '07': '中京', '08': '京都', '09': '阪神', '10': '小倉'
}

def get_jst_now():
    return datetime.now(JST)

def scrape_races():
    """5日間のレースをスクレイピング"""
    
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    
    driver = webdriver.Chrome(options=options)
    
    # 今日から4日後までの日付リスト（5日間）
    today = get_jst_now()
    date_range = [(today + timedelta(days=i)).strftime('%Y%m%d') for i in range(5)]
    
    cache_dir = os.path.join(os.path.dirname(__file__), 'data', 'today')
    os.makedirs(cache_dir, exist_ok=True)
    
    # 古いデータを削除
    for f in os.listdir(cache_dir):
        if f.endswith('.json'):
            os.remove(os.path.join(cache_dir, f))
    
    scraped = []
    
    try:
        race_data_list = []  # (race_id, date)のペア
        
        # 5日間のレースIDを取得
        for target_date in date_range:
            url = f"https://race.netkeiba.com/top/race_list.html?kaisai_date={target_date}"
            driver.get(url)
            time.sleep(2)
            
            race_links = driver.find_elements(By.CSS_SELECTOR, 'a[href*="race_id="]')
            
            for link in race_links:
                href = link.get_attribute('href')
                match = re.search(r'race_id=(\d+)', href)
                if match:
                    race_data_list.append((match.group(1), target_date))
        
        # 重複を除去
        seen_race_ids = set()
        unique_races = []
        for race_id, kaisai_date in race_data_list:
            if race_id not in seen_race_ids:
                seen_race_ids.add(race_id)
                unique_races.append((race_id, kaisai_date))
        
        print(f"Found {len(unique_races)} unique races")
        
        # 各レースをスクレイピング
        for race_id, kaisai_date in unique_races[:100]:
            try:
                race_url = f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}"
                driver.get(race_url)
                time.sleep(1)
                
                # race_idからtrack_codeとrace_numを抽出
                track_code = race_id[4:6] if len(race_id) >= 6 else ''
                race_num = int(race_id[-2:]) if len(race_id) >= 2 else 0
                track_name = TRACK_NAMES.get(track_code, f'競馬場{track_code}')
                
                # レース情報
                race_info = {
                    'race_id': race_id,
                    'kaisai_date': kaisai_date,
                    'track_code': track_code,
                    'track_name': track_name,
                    'race_num': race_num
                }
                
                try:
                    title = driver.find_element(By.CSS_SELECTOR, '.RaceName').text.strip()
                    race_info['name'] = title
                except: pass
                
                try:
                    data_intro = driver.find_element(By.CSS_SELECTOR, '.RaceData01').text
                    dist_match = re.search(r'(\d+)m', data_intro)
                    if dist_match:
                        race_info['distance'] = int(dist_match.group(1))
                except: pass
                
                try:
                    course_elem = driver.find_element(By.CSS_SELECTOR, '.RaceData02 span:first-child')
                    race_info['course'] = course_elem.text.strip()
                except: pass
                
                # クラス判定（グレードレースを優先的に判定）
                # body textとHTMLソース両方を検索（metaタグにグレード情報がある場合がある）
                page_text = driver.find_element(By.TAG_NAME, 'body').text
                html_source = driver.page_source
                search_text = page_text + ' ' + html_source
                
                # GI判定（複数パターン対応）
                if any(p in search_text for p in ['(G1)', '（G1）', '(GⅠ)', '（GⅠ）', 'GⅠ']):
                    race_info['class'] = 'GI'
                # GII判定
                elif any(p in search_text for p in ['(G2)', '（G2）', '(GⅡ)', '（GⅡ）', 'GⅡ']):
                    race_info['class'] = 'GII'
                # GIII判定
                elif any(p in search_text for p in ['(G3)', '（G3）', '(GⅢ)', '（GⅢ）', 'GⅢ']):
                    race_info['class'] = 'GIII'
                elif 'リステッド' in page_text or '(L)' in page_text:
                    race_info['class'] = 'リステッド'
                elif 'オープン' in page_text:
                    race_info['class'] = 'オープン'
                elif '3勝クラス' in page_text:
                    race_info['class'] = '3勝クラス'
                elif '2勝クラス' in page_text:
                    race_info['class'] = '2勝クラス'
                elif '1勝クラス' in page_text:
                    race_info['class'] = '1勝クラス'
                elif '未勝利' in page_text:
                    race_info['class'] = '未勝利'
                elif '新馬' in page_text:
                    race_info['class'] = '新馬'
                else:
                    race_info['class'] = 'その他'
                
                # 馬データ
                horses = []
                rows = driver.find_elements(By.CSS_SELECTOR, '.HorseList tr.HorseList')
                
                for row in rows:
                    try:
                        horse = {}
                        
                        num_elem = row.find_element(By.CSS_SELECTOR, 'td.Umaban')
                        horse['num'] = int(num_elem.text.strip())
                        
                        name_elem = row.find_element(By.CSS_SELECTOR, '.HorseName a')
                        horse['name'] = name_elem.text.strip()
                        
                        try:
                            odds_elem = row.find_element(By.CSS_SELECTOR, '.Popular span')
                            horse['popularity'] = int(odds_elem.text.strip())
                        except: pass
                        
                        try:
                            odds_elem = row.find_element(By.CSS_SELECTOR, '.Odds span')
                            horse['odds'] = float(odds_elem.text.strip())
                        except: pass
                        
                        horses.append(horse)
                    except:
                        continue
                
                # 保存
                race_data = {
                    'race_id': race_id,
                    'race_info': race_info,
                    'horses': horses
                }
                
                filepath = os.path.join(cache_dir, f'race_{race_id}.json')
                with open(filepath, 'w', encoding='utf-8') as fp:
                    json.dump(race_data, fp, ensure_ascii=False, indent=2)
                
                scraped.append(race_id)
                print(f"  Scraped: {race_id} - {race_info.get('name', 'N/A')}")
                
            except Exception as e:
                print(f"  Error scraping {race_id}: {e}")
                continue
        
    finally:
        driver.quit()
    
    print(f"\nTotal scraped: {len(scraped)} races")
    return scraped

if __name__ == '__main__':
    scrape_races()
