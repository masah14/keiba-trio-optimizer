"""
ウォークフォワードテスト

正しい検証方法:
- 訓練期間: 2024年1月〜6月のデータで統計構築
- テスト期間: 2024年7月〜12月で検証

これにより「将来のデータで過去を予測」問題を回避
"""

import sys
import os
import json
import time
import re
from datetime import datetime, timedelta
from collections import defaultdict

sys.path.insert(0, 'app')
sys.stdout.reconfigure(line_buffering=True)

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options


def get_race_ids_for_date(driver, date_str):
    url = f"https://race.netkeiba.com/top/race_list.html?kaisai_date={date_str}"
    try:
        driver.get(url)
        time.sleep(1.5)
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
        time.sleep(0.8)
        
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


def scrape_period(start_date, end_date, output_dir, max_races=None):
    """期間のレースをスクレイピング"""
    print(f"Scraping {start_date} to {end_date} -> {output_dir}", flush=True)
    
    os.makedirs(output_dir, exist_ok=True)
    
    start = datetime.strptime(start_date, "%Y%m%d")
    end = datetime.strptime(end_date, "%Y%m%d")
    
    dates = []
    current = start
    while current <= end:
        if current.weekday() in [5, 6]:  # 土日のみ
            dates.append(current.strftime("%Y%m%d"))
        current += timedelta(days=1)
    
    print(f"  {len(dates)} weekend days", flush=True)
    
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    driver = webdriver.Chrome(options=options)
    
    total = 0
    scraped = 0
    
    try:
        for date_str in dates:
            print(f"  {date_str}...", end='', flush=True)
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
                    print(f" {count} (limit reached)", flush=True)
                    return scraped
                
                time.sleep(0.3)
            
            print(f" {count} new", flush=True)
    finally:
        driver.quit()
    
    print(f"  Total scraped: {scraped}", flush=True)
    return scraped


def load_races(cache_dir):
    races = []
    if not os.path.exists(cache_dir):
        return races
    for f in os.listdir(cache_dir):
        if f.startswith('race_') and f.endswith('.json'):
            with open(os.path.join(cache_dir, f), 'r', encoding='utf-8') as fp:
                race = json.load(fp)
            if race.get('horses') and len(race['horses']) >= 5:
                races.append(race)
    return races


def build_stats_from_races(races):
    horse_stats = defaultdict(lambda: {
        'runs': 0, 'wins': 0, 'places': 0, 'finishes': [],
        'courses': defaultdict(lambda: {'runs': 0, 'wins': 0}),
    })
    jockey_stats = defaultdict(lambda: {'runs': 0, 'wins': 0, 'places': 0})
    
    for race in races:
        course = race.get('race_info', {}).get('course', '')
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
                if course:
                    hs['courses'][course]['runs'] += 1
                    if finish == 1: hs['courses'][course]['wins'] += 1
            
            if jockey_id:
                js = jockey_stats[jockey_id]
                js['runs'] += 1
                if finish == 1: js['wins'] += 1
                if finish <= 3: js['places'] += 1
    
    for stats in horse_stats.values():
        if stats['runs'] > 0:
            stats['win_rate'] = stats['wins'] / stats['runs']
            stats['place_rate'] = stats['places'] / stats['runs']
    
    for stats in jockey_stats.values():
        if stats['runs'] > 0:
            stats['win_rate'] = stats['wins'] / stats['runs']
    
    return dict(horse_stats), dict(jockey_stats)


def run_walk_forward_test():
    """ウォークフォワードテスト実行"""
    print("=" * 70, flush=True)
    print("=== ウォークフォワードテスト ===", flush=True)
    print("=" * 70, flush=True)
    
    train_dir = "data/walk_forward/train"
    test_dir = "data/walk_forward/test"
    
    # Phase 1: データ収集
    print("\n[Phase 1] データ収集", flush=True)
    
    # 訓練期間: 2024年10月-11月（2ヶ月分）
    print("\n訓練期間 (2024/10-11):", flush=True)
    scrape_period("20241001", "20241130", train_dir, max_races=150)
    
    # テスト期間: 2024年12月（1ヶ月分）
    print("\nテスト期間 (2024/12):", flush=True)
    scrape_period("20241201", "20241222", test_dir, max_races=100)
    
    # Phase 2: 訓練期間のデータで統計構築
    print("\n[Phase 2] 統計構築（訓練期間データのみ使用）", flush=True)
    train_races = load_races(train_dir)
    print(f"  訓練レース: {len(train_races)}", flush=True)
    
    horse_stats, jockey_stats = build_stats_from_races(train_races)
    print(f"  馬統計: {len(horse_stats)} horses", flush=True)
    print(f"  騎手統計: {len(jockey_stats)} jockeys", flush=True)
    
    # Phase 3: テスト期間で検証
    print("\n[Phase 3] テスト期間で検証", flush=True)
    test_races = load_races(test_dir)
    print(f"  テストレース: {len(test_races)}", flush=True)
    
    if len(test_races) < 10:
        print("テストデータ不足")
        return
    
    from ev_engine_v3 import EVEngineV3, EVConfigV3
    
    v3 = EVEngineV3(EVConfigV3(
        weight_base_ability=0.35, weight_course_fit=0.20,
        weight_recent_form=0.20, weight_jockey=0.15, weight_market=0.10,
        fav_factor=0.95, mid_factor=1.00, long_factor=1.05, extreme_factor=1.10
    ))
    
    bet_unit = 100
    conditions = [
        ("単勝 EV>=1.5", 'win', 1.5),
        ("複勝 EV>=1.0", 'place', 1.0),
    ]
    
    for cond_name, bet_type, ev_threshold in conditions:
        stats = {'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0}
        
        for race in test_races:
            horses = race.get('horses', [])
            payouts = race.get('payouts', {'win': {}, 'place': {}})
            race_info = race.get('race_info', {})
            course = race_info.get('course', '')
            
            # 訓練期間の統計を使用（未来のデータを使わない！）
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
                        'course_runs': hs['courses'].get(course, {}).get('runs', 0),
                        'course_win_rate': (hs['courses'].get(course, {}).get('wins', 0) / 
                                           max(1, hs['courses'].get(course, {}).get('runs', 1))),
                    }
                
                if jockey_id and jockey_id in jockey_stats:
                    js = jockey_stats[jockey_id]
                    h['jockey_profile'] = {
                        'year_runs': js['runs'],
                        'year_win_rate': js.get('win_rate', 0),
                    }
            
            calculated = v3.calculate_ev([h.copy() for h in horses])
            
            for h in calculated:
                num = h['num']
                finish = h.get('finish', 0)
                odds = h.get('odds', 999)
                confidence = h.get('_scores', {}).get('confidence', 0)
                
                if odds > 30:
                    continue
                
                if bet_type == 'win':
                    ev = h.get('win_ev', 0)
                    hit_cond = finish == 1
                else:
                    ev = h.get('place_ev', 0)
                    hit_cond = finish <= 3
                
                if ev >= ev_threshold and confidence >= 0.7:
                    stats['bets'] += 1
                    stats['investment'] += bet_unit
                    if hit_cond:
                        stats['hits'] += 1
                        payout = payouts.get(bet_type, {}).get(str(num), 0)
                        stats['payout'] += payout
        
        roi = (stats['payout'] / stats['investment'] * 100) if stats['investment'] > 0 else 0
        hit_rate = (stats['hits'] / stats['bets'] * 100) if stats['bets'] > 0 else 0
        profit = stats['payout'] - stats['investment']
        
        print(f"\n【{cond_name}】", flush=True)
        print(f"  ベット: {stats['bets']}件", flush=True)
        print(f"  的中: {stats['hits']}件 ({hit_rate:.1f}%)", flush=True)
        print(f"  投資: {stats['investment']:,}円", flush=True)
        print(f"  払戻: {stats['payout']:,}円", flush=True)
        print(f"  損益: {profit:+,}円", flush=True)
        print(f"  ROI: {roi:.1f}%", flush=True)
        
        if roi >= 100:
            print("  → プラス収支！", flush=True)
        else:
            print("  → マイナス収支", flush=True)


if __name__ == "__main__":
    run_walk_forward_test()
