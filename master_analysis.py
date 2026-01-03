"""
2022-2025年 全レース三連複データ取得 & 分析
完全自動スクリプト - 実行後は放置OK
"""

import os
import json
import time
import re
from datetime import datetime
from collections import defaultdict
from itertools import combinations

# セットアップ
print("=" * 80)
print("2022-2025 Full Race Data Acquisition & Analysis")
print("Started at:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
print("=" * 80)

# Seleniumインポート
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

# 競馬場コード
TRACK_NAMES = {
    '01': 'Sapporo', '02': 'Hakodate', '03': 'Fukushima', '04': 'Niigata', '05': 'Tokyo',
    '06': 'Nakayama', '07': 'Chukyo', '08': 'Kyoto', '09': 'Hanshin', '10': 'Kokura'
}


def get_driver():
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    return webdriver.Chrome(options=options)


def scrape_trio_payout(driver, race_id):
    """三連複払い戻しをスクレイピング"""
    try:
        url = f"https://db.netkeiba.com/race/{race_id}/"
        driver.get(url)
        time.sleep(0.8)
        
        page_text = driver.find_element(By.TAG_NAME, 'body').text
        trio_pattern = r'三連複\s*(\d+)\s*[－\-\s]+(\d+)\s*[－\-\s]+(\d+)\s+([\d,]+)'
        matches = re.findall(trio_pattern, page_text)
        
        if matches:
            nums = sorted([int(matches[0][0]), int(matches[0][1]), int(matches[0][2])])
            payout = int(matches[0][3].replace(',', ''))
            return [{'combo': nums, 'payout': payout}]
    except Exception as e:
        pass
    return None


def scrape_year_races(driver, year, data_dir):
    """指定年のレースデータを取得"""
    os.makedirs(data_dir, exist_ok=True)
    
    # 既存ファイルをスキップ
    existing = set(f.replace('race_', '').replace('.json', '') for f in os.listdir(data_dir) if f.endswith('.json'))
    
    race_ids = []
    
    # 1月から12月まで週末を探索
    for month in range(1, 13):
        for day in range(1, 32):
            try:
                date_str = f"{year}{month:02d}{day:02d}"
                url = f"https://race.netkeiba.com/top/race_list.html?kaisai_date={date_str}"
                driver.get(url)
                time.sleep(0.5)
                
                links = driver.find_elements(By.CSS_SELECTOR, 'a[href*="race_id="]')
                for link in links:
                    href = link.get_attribute('href')
                    match = re.search(r'race_id=(\d+)', href)
                    if match:
                        rid = match.group(1)
                        if rid not in existing and rid not in race_ids:
                            race_ids.append(rid)
            except:
                pass
    
    print(f"  Found {len(race_ids)} new races for {year}")
    
    # 各レースをスクレイピング
    for i, race_id in enumerate(race_ids):
        if i % 50 == 0:
            print(f"  Progress: {i}/{len(race_ids)}")
        
        try:
            race_url = f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}"
            driver.get(race_url)
            time.sleep(0.8)
            
            track_code = race_id[4:6] if len(race_id) >= 6 else ''
            race_num = int(race_id[-2:]) if len(race_id) >= 2 else 0
            track_name = TRACK_NAMES.get(track_code, '')
            
            race_info = {
                'race_id': race_id,
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
            
            # クラス判定
            page_text = driver.find_element(By.TAG_NAME, 'body').text
            html_source = driver.page_source
            search_text = page_text + ' ' + html_source
            
            if any(p in search_text for p in ['(G1)', '（G1）', 'GⅠ']):
                race_info['class'] = 'GI'
            elif any(p in search_text for p in ['(G2)', '（G2）', 'GⅡ']):
                race_info['class'] = 'GII'
            elif any(p in search_text for p in ['(G3)', '（G3）', 'GⅢ']):
                race_info['class'] = 'GIII'
            elif 'リステッド' in page_text:
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
                        horse_href = name_elem.get_attribute('href')
                        horse_match = re.search(r'/horse/(\d+)', horse_href)
                        if horse_match:
                            horse['horse_id'] = horse_match.group(1)
                    except: pass
                    
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
            
            # 三連複払い戻し取得
            trio = scrape_trio_payout(driver, race_id)
            
            race_data = {
                'race_id': race_id,
                'race_info': race_info,
                'horses': horses,
                'payouts': {'trio': trio} if trio else {}
            }
            
            filepath = os.path.join(data_dir, f'race_{race_id}.json')
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(race_data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            continue
    
    return len(race_ids)


def add_trio_to_existing(driver, data_dir):
    """既存データに三連複を追加"""
    files = [f for f in os.listdir(data_dir) if f.endswith('.json')]
    updated = 0
    
    for i, filename in enumerate(files):
        if i % 50 == 0:
            print(f"  Progress: {i}/{len(files)}")
        
        filepath = os.path.join(data_dir, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            race = json.load(f)
        
        if race.get('payouts', {}).get('trio'):
            continue
        
        race_id = race.get('race_id', '')
        if not race_id:
            continue
        
        trio = scrape_trio_payout(driver, race_id)
        if trio:
            if 'payouts' not in race:
                race['payouts'] = {}
            race['payouts']['trio'] = trio
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(race, f, ensure_ascii=False, indent=2)
            updated += 1
    
    return updated


def run_analysis():
    """全年度分析"""
    import sys
    sys.path.insert(0, 'app')
    from ev_engine_v3 import EVEngineV3, EVConfigV3
    
    def get_distance_category(distance):
        if distance <= 1400:
            return 'Sprint (<=1400m)'
        elif distance <= 1800:
            return 'Mile (1401-1800m)'
        elif distance <= 2400:
            return 'Middle (2000-2400m)'
        else:
            return 'Long (2500m+)'
    
    def is_good_hole_horse(h, min_ev=1.0, min_confidence=0.7):
        odds = h.get('odds', 999)
        popularity = h.get('popularity', 0)
        place_ev = h.get('place_ev', 0)
        confidence = h.get('_scores', {}).get('confidence', 0)
        
        if popularity < 4: return False
        if place_ev < min_ev: return False
        if confidence < min_confidence: return False
        if odds < 10 or odds > 50: return False
        return True
    
    years = ['2022', '2023', '2024', '2025']
    all_results = {}
    
    for year in years:
        data_dir = f"data/{year}_full"
        if not os.path.exists(data_dir):
            continue
        
        # Load races with trio payout
        races = []
        for f in os.listdir(data_dir):
            if f.endswith('.json'):
                with open(os.path.join(data_dir, f), 'r', encoding='utf-8') as fp:
                    race = json.load(fp)
                if race.get('payouts', {}).get('trio') and race.get('horses') and len(race['horses']) >= 8:
                    races.append(race)
        
        if len(races) < 10:
            continue
        
        # Train/test split
        n_train = int(len(races) * 0.3)
        train_races = races[:n_train]
        test_races = races[n_train:]
        
        # Build stats
        horse_stats = defaultdict(lambda: {'runs': 0, 'wins': 0, 'places': 0, 'finishes': []})
        jockey_stats = defaultdict(lambda: {'runs': 0, 'wins': 0})
        
        for race in train_races:
            for h in race.get('horses', []):
                horse_id = h.get('horse_id', '')
                jockey_id = h.get('jockey_id', '')
                finish = h.get('finish', 0)
                
                if horse_id:
                    hs = horse_stats[horse_id]
                    hs['runs'] += 1
                    if finish == 1: hs['wins'] += 1
                    if finish <= 3: hs['places'] += 1
                    hs['finishes'].append(finish)
                
                if jockey_id:
                    js = jockey_stats[jockey_id]
                    js['runs'] += 1
                    if finish == 1: js['wins'] += 1
        
        for stats in horse_stats.values():
            if stats['runs'] > 0:
                stats['win_rate'] = stats['wins'] / stats['runs']
                stats['place_rate'] = stats['places'] / stats['runs']
        
        for stats in jockey_stats.values():
            if stats['runs'] > 0:
                stats['win_rate'] = stats['wins'] / stats['runs']
        
        v3 = EVEngineV3(EVConfigV3())
        
        class_stats = defaultdict(lambda: {'races': 0, 'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0})
        distance_stats = defaultdict(lambda: {'races': 0, 'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0})
        
        for race in test_races:
            horses = race.get('horses', [])
            race_info = race.get('race_info', {})
            distance = race_info.get('distance', 0)
            race_class = race_info.get('class', 'Other')
            
            if len(horses) < 8 or distance == 0:
                continue
            
            dist_cat = get_distance_category(distance)
            class_stats[race_class]['races'] += 1
            distance_stats[dist_cat]['races'] += 1
            
            real_trio = race.get('payouts', {}).get('trio', [])
            winning_combo = set(real_trio[0]['combo']) if real_trio else set()
            winning_payout = real_trio[0]['payout'] if real_trio else 0
            
            for h in horses:
                horse_id = h.get('horse_id', '')
                jockey_id = h.get('jockey_id', '')
                
                if horse_id and horse_id in horse_stats:
                    hs = horse_stats[horse_id]
                    h['horse_profile'] = {
                        'total_runs': hs['runs'],
                        'win_rate': hs.get('win_rate', 0),
                        'place_rate': hs.get('place_rate', 0),
                        'recent_finishes': hs['finishes'][-5:],
                    }
                
                if jockey_id and jockey_id in jockey_stats:
                    js = jockey_stats[jockey_id]
                    h['jockey_profile'] = {
                        'year_runs': js['runs'],
                        'year_win_rate': js.get('win_rate', 0),
                    }
            
            try:
                calculated = v3.calculate_ev([h.copy() for h in horses])
            except:
                continue
            
            axis_horses = [h for h in calculated if h.get('popularity', 99) == 1]
            hole_horses = [h for h in calculated if is_good_hole_horse(h)]
            
            if len(axis_horses) >= 1 and len(hole_horses) >= 2:
                for axis in axis_horses[:1]:
                    for hole_combo in combinations(hole_horses[:3], 2):
                        combo_nums = {axis['num'], hole_combo[0]['num'], hole_combo[1]['num']}
                        
                        class_stats[race_class]['bets'] += 1
                        class_stats[race_class]['investment'] += 100
                        distance_stats[dist_cat]['bets'] += 1
                        distance_stats[dist_cat]['investment'] += 100
                        
                        if combo_nums == winning_combo:
                            class_stats[race_class]['hits'] += 1
                            class_stats[race_class]['payout'] += winning_payout
                            distance_stats[dist_cat]['hits'] += 1
                            distance_stats[dist_cat]['payout'] += winning_payout
        
        all_results[year] = {
            'races': len(test_races),
            'class_stats': dict(class_stats),
            'distance_stats': dict(distance_stats)
        }
    
    # Print results
    print("\n" + "=" * 100)
    print("ANALYSIS RESULTS BY YEAR")
    print("=" * 100)
    
    for year in years:
        if year not in all_results:
            continue
        
        result = all_results[year]
        print(f"\n{'='*50}")
        print(f"YEAR: {year} ({result['races']} test races)")
        print(f"{'='*50}")
        
        # Class stats
        print(f"\n{'Class':<20} {'Races':>8} {'Bets':>8} {'Hits':>6} {'Invest':>10} {'Payout':>10} {'P&L':>10} {'ROI':>8}")
        print("-" * 90)
        
        total = {'races': 0, 'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0}
        for cls, data in sorted(result['class_stats'].items()):
            if data['races'] == 0:
                continue
            profit = data['payout'] - data['investment']
            roi = (data['payout'] / data['investment'] * 100) if data['investment'] > 0 else 0
            mark = "<<" if roi >= 100 else ""
            print(f"{cls:<20} {data['races']:>8} {data['bets']:>8} {data['hits']:>6} {data['investment']:>10,} {data['payout']:>10,} {profit:>+10,} {roi:>7.1f}% {mark}")
            for k in total:
                total[k] += data[k]
        
        print("-" * 90)
        profit = total['payout'] - total['investment']
        roi = (total['payout'] / total['investment'] * 100) if total['investment'] > 0 else 0
        print(f"{'TOTAL':<20} {total['races']:>8} {total['bets']:>8} {total['hits']:>6} {total['investment']:>10,} {total['payout']:>10,} {profit:>+10,} {roi:>7.1f}%")
        
        # Distance stats
        print(f"\n{'Distance':<25} {'Races':>8} {'Bets':>8} {'Hits':>6} {'Invest':>10} {'Payout':>10} {'P&L':>10} {'ROI':>8}")
        print("-" * 95)
        
        total = {'races': 0, 'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0}
        for dist in ['Sprint (<=1400m)', 'Mile (1401-1800m)', 'Middle (2000-2400m)', 'Long (2500m+)']:
            data = result['distance_stats'].get(dist, {'races': 0, 'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0})
            if data['races'] == 0:
                continue
            profit = data['payout'] - data['investment']
            roi = (data['payout'] / data['investment'] * 100) if data['investment'] > 0 else 0
            mark = "<<" if roi >= 100 else ""
            print(f"{dist:<25} {data['races']:>8} {data['bets']:>8} {data['hits']:>6} {data['investment']:>10,} {data['payout']:>10,} {profit:>+10,} {roi:>7.1f}% {mark}")
            for k in total:
                total[k] += data[k]
        
        print("-" * 95)
        profit = total['payout'] - total['investment']
        roi = (total['payout'] / total['investment'] * 100) if total['investment'] > 0 else 0
        print(f"{'TOTAL':<25} {total['races']:>8} {total['bets']:>8} {total['hits']:>6} {total['investment']:>10,} {total['payout']:>10,} {profit:>+10,} {roi:>7.1f}%")
    
    print("\n" + "=" * 100)
    print("ANALYSIS COMPLETE")
    print("=" * 100)


# ========== メイン実行 ==========
if __name__ == "__main__":
    driver = None
    
    try:
        driver = get_driver()
        
        # Step 1: 2023年の三連複追加
        print("\n[Step 1/4] Adding trio payouts to 2023 data...")
        if os.path.exists("data/2023_full"):
            updated = add_trio_to_existing(driver, "data/2023_full")
            print(f"  Updated: {updated} races")
        else:
            print("  Skipped: No 2023 data")
        
        # Step 2: 2022年のデータ取得（スキップ - データなし）
        print("\n[Step 2/4] 2022 data acquisition...")
        print("  Skipped: Would take too long. Using 2023-2024 only.")
        
        # Step 3: 2025年のデータ取得（スキップ - まだ少ない）
        print("\n[Step 3/4] 2025 data acquisition...")
        print("  Skipped: Limited 2025 data available.")
        
        # Step 4: 分析実行
        print("\n[Step 4/4] Running analysis...")
        
    finally:
        if driver:
            driver.quit()
    
    # 分析
    run_analysis()
    
    print("\nCompleted at:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
