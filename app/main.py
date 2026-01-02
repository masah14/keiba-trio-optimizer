"""
本日のレース取得＆EV計算 API

機能:
1. 今日の開催レースを取得
2. 対象クラス（GIII, 1勝, 2勝, 未勝利）をフィルタ
3. 各馬のEV（期待値）を計算
4. 三連複推奨買い目を生成
"""

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional, Dict
import os
import sys
import json
from datetime import datetime, timedelta, timezone
from collections import defaultdict

# 日本時間を取得
JST = timezone(timedelta(hours=9))

def get_jst_now():
    """日本時間の現在時刻を取得"""
    return datetime.now(JST)

# EV Engine V3
sys.path.insert(0, os.path.dirname(__file__))
from ev_engine_v3 import EVEngineV3, EVConfigV3

app = FastAPI(title="競馬三連複 最適化戦略アプリ")

# V3エンジン初期化
engine = EVEngineV3(EVConfigV3(
    weight_base_ability=0.35, weight_course_fit=0.20,
    weight_recent_form=0.20, weight_jockey=0.15, weight_market=0.10,
    fav_factor=0.95, mid_factor=1.00, long_factor=1.05, extreme_factor=1.10
))

# 対象クラス
TARGET_CLASSES = ['GIII', '1勝クラス', '2勝クラス', '未勝利']

# 統計データをロード
def load_stats():
    """2023年のデータから統計を構築"""
    stats_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'stats_2023.json')
    
    if os.path.exists(stats_file):
        with open(stats_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    # 統計ファイルがなければ構築
    horse_stats = defaultdict(lambda: {'runs': 0, 'wins': 0, 'places': 0, 'finishes': []})
    jockey_stats = defaultdict(lambda: {'runs': 0, 'wins': 0})
    
    data_dir = os.path.join(os.path.dirname(__file__), '..', 'data', '2023_full')
    if os.path.exists(data_dir):
        for f in os.listdir(data_dir):
            if f.startswith('race_') and f.endswith('.json'):
                with open(os.path.join(data_dir, f), 'r', encoding='utf-8') as fp:
                    race = json.load(fp)
                
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
                        jockey_stats[jockey_id]['runs'] += 1
                        if finish == 1: jockey_stats[jockey_id]['wins'] += 1
        
        # 勝率計算
        for stats in horse_stats.values():
            if stats['runs'] > 0:
                stats['win_rate'] = stats['wins'] / stats['runs']
                stats['place_rate'] = stats['places'] / stats['runs']
        
        for stats in jockey_stats.values():
            if stats['runs'] > 0:
                stats['win_rate'] = stats['wins'] / stats['runs']
        
        # 保存
        result = {'horse_stats': dict(horse_stats), 'jockey_stats': dict(jockey_stats)}
        os.makedirs(os.path.dirname(stats_file), exist_ok=True)
        with open(stats_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False)
        
        return result
    
    return {'horse_stats': {}, 'jockey_stats': {}}


# 統計データ
stats_data = None


def get_stats():
    global stats_data
    if stats_data is None:
        stats_data = load_stats()
    return stats_data


def get_distance_category(distance):
    if distance <= 1400:
        return "sprint"
    elif distance <= 1800:
        return "mile"
    elif distance <= 2200:
        return "middle"
    else:
        return "long"


def is_good_hole(h):
    """穴馬判定"""
    odds = h.get('odds', 999)
    pop = h.get('popularity', 0)
    place_ev = h.get('place_ev', 0)
    return pop >= 4 and place_ev > 1.0 and 10 <= odds <= 50


def calculate_trio_bets(horses, race_class, distance):
    """三連複買い目を計算"""
    dist_cat = get_distance_category(distance)
    
    # 軸馬: 人気1-2位
    axis_horses = [h for h in horses if h.get('popularity', 99) <= 2]
    
    # 穴馬: 複勝EV > 1.0, オッズ10-50倍
    hole_horses = [h for h in horses if is_good_hole(h)]
    hole_nums = set(h['num'] for h in hole_horses)
    
    if not axis_horses or not hole_horses:
        return []
    
    axis = axis_horses[0]
    bets = []
    
    for hole in hole_horses[:2]:
        remaining = [h for h in horses if h['num'] not in [axis['num'], hole['num']]]
        
        for other in remaining[:5]:
            # 金額計算
            amount = 100
            multipliers = []
            
            if dist_cat in ['mile', 'long']:
                amount *= 2
                multipliers.append('距離×2')
            
            if race_class == 'GIII':
                amount *= 2
                multipliers.append('GIII×2')
            
            is_double_hole = other['num'] in hole_nums
            if is_double_hole:
                amount *= 2
                multipliers.append('穴2×2')
            
            bets.append({
                'combo': sorted([axis['num'], hole['num'], other['num']]),
                'horses': [
                    {'num': axis['num'], 'name': axis['name']},
                    {'num': hole['num'], 'name': hole['name']},
                    {'num': other['num'], 'name': other['name']},
                ],
                'amount': amount,
                'is_boosted': is_double_hole,
                'multipliers': multipliers
            })
    
    return bets


@app.get("/api/today-races")
async def get_today_races():
    """今日から4日後までのレース一覧を取得"""
    from datetime import timedelta
    
    # 今日から4日後までの日付リスト（5日間）
    today = get_jst_now()
    date_range = [(today + timedelta(days=i)).strftime('%Y%m%d') for i in range(5)]
    
    # キャッシュディレクトリを確認
    cache_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'today')
    os.makedirs(cache_dir, exist_ok=True)
    
    target_races = []
    other_races = []
    
    # 競馬場コード→名前の変換
    TRACK_NAMES = {
        '01': '札幌', '02': '函館', '03': '福島', '04': '新潟', '05': '東京',
        '06': '中山', '07': '中京', '08': '京都', '09': '阪神', '10': '小倉'
    }
    
    # キャッシュ内の全レースファイルを読み込み
    for f in os.listdir(cache_dir):
        if not f.endswith('.json'):
            continue
        
        with open(os.path.join(cache_dir, f), 'r', encoding='utf-8') as fp:
            race = json.load(fp)
        
        race_info = race.get('race_info', {})
        race_class = race_info.get('class', '')
        race_id = race.get('race_id', '')
        race_name = race_info.get('name', '') or f'レース{race_id[-2:]}'
        
        # kaisai_dateがあればそれを使用、なければrace_idから推測
        kaisai_date = race_info.get('kaisai_date', '')
        
        # track_codeとrace_numを取得
        track_code = race_info.get('track_code', race_id[4:6] if len(race_id) >= 6 else '')
        track_name = race_info.get('track_name', TRACK_NAMES.get(track_code, ''))
        race_num = race_info.get('race_num', int(race_id[-2:]) if len(race_id) >= 2 else 0)
        
        race_data = {
            'race_id': race_id,
            'date': kaisai_date,
            'track_name': track_name,
            'race_num': race_num,
            'name': race_name,
            'course': race_info.get('course', ''),
            'distance': race_info.get('distance', 0),
            'class': race_class or '未分類',
            'horse_count': len(race.get('horses', [])),
            'is_target': race_class in TARGET_CLASSES
        }
        
        if race_class in TARGET_CLASSES:
            target_races.append(race_data)
        else:
            other_races.append(race_data)
    
    # 日付とレース番号でソート
    target_races.sort(key=lambda x: (x.get('date', ''), x.get('track_name', ''), x.get('race_num', 0)))
    other_races.sort(key=lambda x: (x.get('date', ''), x.get('track_name', ''), x.get('race_num', 0)))
    
    return {
        'date_range': date_range,
        'date_from': date_range[0],
        'date_to': date_range[-1],
        'target_classes': TARGET_CLASSES,
        'target_races': target_races,
        'other_races': other_races,
        'races': target_races,  # 後方互換
        'total_races': len(target_races) + len(other_races),
        'message': '「レースを取得」ボタンを押してください' if len(target_races) + len(other_races) == 0 else None
    }


@app.get("/api/race/{race_id}")
async def get_race_ev(race_id: str):
    """特定レースのEV計算"""
    cache_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'today')
    filepath = os.path.join(cache_dir, f'race_{race_id}.json')
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="レースが見つかりません")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        race = json.load(f)
    
    horses = race.get('horses', [])
    race_info = race.get('race_info', {})
    race_class = race_info.get('class', '')
    distance = race_info.get('distance', 0)
    
    # 統計データを付与
    stats = get_stats()
    horse_stats = stats.get('horse_stats', {})
    jockey_stats = stats.get('jockey_stats', {})
    
    for h in horses:
        horse_id = h.get('horse_id', '')
        jockey_id = h.get('jockey_id', '')
        
        if horse_id and horse_id in horse_stats:
            hs = horse_stats[horse_id]
            h['horse_profile'] = {
                'total_runs': hs.get('runs', 0),
                'win_rate': hs.get('win_rate', 0),
                'place_rate': hs.get('place_rate', 0),
            }
        
        if jockey_id and jockey_id in jockey_stats:
            js = jockey_stats[jockey_id]
            h['jockey_profile'] = {
                'year_runs': js.get('runs', 0),
                'year_win_rate': js.get('win_rate', 0),
            }
    
    # EV計算
    calculated = engine.calculate_ev(horses)
    
    # 三連複買い目
    trio_bets = []
    if len(horses) >= 8 and race_class in TARGET_CLASSES:
        trio_bets = calculate_trio_bets(calculated, race_class, distance)
    
    total_investment = sum(b['amount'] for b in trio_bets)
    
    return {
        'race_id': race_id,
        'race_info': race_info,
        'is_target': race_class in TARGET_CLASSES,
        'horses': calculated,
        'trio_bets': trio_bets,
        'summary': {
            'total_bets': len(trio_bets),
            'total_investment': total_investment,
            'axis_horse': trio_bets[0]['horses'][0] if trio_bets else None,
            'hole_horses': list(set(b['horses'][1]['name'] for b in trio_bets)) if trio_bets else []
        }
    }


@app.post("/api/scrape-today")
async def scrape_today():
    """今日から2日後までのレースをスクレイピング（ローカル環境のみ）"""
    
    # Render環境ではスクレイピングを無効化
    if os.environ.get('RENDER') == 'true':
        return {
            'status': 'disabled',
            'message': 'スクレイピングはローカル環境でのみ実行可能です',
            'scraped_count': 0
        }
    
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.chrome.options import Options
    except ImportError:
        return {
            'status': 'error',
            'message': 'Seleniumがインストールされていません',
            'scraped_count': 0
        }
    
    from datetime import timedelta
    import time
    import re
    
    # ChromeDriverの自動インストール
    try:
        import chromedriver_autoinstaller
        chromedriver_autoinstaller.install()
    except:
        pass
    
    # 今日から4日後までの日付リスト（5日間）
    today = get_jst_now()
    date_range = [(today + timedelta(days=i)).strftime('%Y%m%d') for i in range(5)]
    
    cache_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'today')
    os.makedirs(cache_dir, exist_ok=True)
    
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    
    driver = webdriver.Chrome(options=options)
    scraped = []
    
    try:
        race_data_list = []  # (race_id, date)のペア
        
        # 5日間のレースIDを取得
        for target_date in date_range:
            url = f"https://race.netkeiba.com/top/race_list.html?kaisai_date={target_date}"
            driver.get(url)
            time.sleep(1.5)
            
            race_links = driver.find_elements(By.CSS_SELECTOR, 'a[href*="race_id="]')
            
            for link in race_links:
                href = link.get_attribute('href')
                match = re.search(r'race_id=(\d+)', href)
                if match:
                    race_data_list.append((match.group(1), target_date))
        
        # 競馬場コード→名前の変換
        TRACK_NAMES = {
            '01': '札幌', '02': '函館', '03': '福島', '04': '新潟', '05': '東京',
            '06': '中山', '07': '中京', '08': '京都', '09': '阪神', '10': '小倉'
        }
        
        # 重複を除去
        seen_race_ids = set()
        unique_races = []
        for race_id, kaisai_date in race_data_list:
            if race_id not in seen_race_ids:
                seen_race_ids.add(race_id)
                unique_races.append((race_id, kaisai_date))
        
        # 各レースをスクレイピング（最大100レース）
        for race_id, kaisai_date in unique_races[:100]:
            filepath = os.path.join(cache_dir, f'race_{race_id}.json')
            if os.path.exists(filepath):
                continue
            
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
                
                # クラス判定
                page_text = driver.find_element(By.TAG_NAME, 'body').text
                if '(G1)' in page_text or '（G1）' in page_text:
                    race_info['class'] = 'GI'
                elif '(G2)' in page_text or '（G2）' in page_text:
                    race_info['class'] = 'GII'
                elif '(G3)' in page_text or '（G3）' in page_text:
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
                        horse['horse_id'] = name_elem.get_attribute('href').split('/')[-2]
                        
                        jockey_elem = row.find_element(By.CSS_SELECTOR, '.Jockey a')
                        horse['jockey'] = jockey_elem.text.strip()
                        horse['jockey_id'] = jockey_elem.get_attribute('href').split('/')[-2]
                        
                        try:
                            odds_elem = row.find_element(By.CSS_SELECTOR, '.Popular span')
                            horse['odds'] = float(odds_elem.text.strip())
                        except:
                            horse['odds'] = 99.9
                        
                        horses.append(horse)
                    except:
                        continue
                
                # 人気順を付与
                horses.sort(key=lambda x: x.get('odds', 999))
                for i, h in enumerate(horses):
                    h['popularity'] = i + 1
                horses.sort(key=lambda x: x['num'])
                
                # 保存
                data = {
                    'race_id': race_id,
                    'race_info': race_info,
                    'horses': horses
                }
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                
                scraped.append(race_id)
                
            except Exception as e:
                print(f"Error scraping {race_id}: {e}")
                continue
    
    finally:
        driver.quit()
    
    return {
        'date': today,
        'scraped_count': len(scraped),
        'race_ids': scraped
    }


@app.get("/api/config")
async def get_config():
    """設定情報"""
    return {
        'target_classes': TARGET_CLASSES,
        'strategy': {
            'name': '最適化三連複戦略',
            'roi': '164.4%',
            'description': '軸馬(1-2番人気) × 穴馬(EV>1.0) × 全馬',
            'multipliers': {
                'mile_long': '×2',
                'giii': '×2',
                'double_hole': '×2'
            }
        }
    }


# 静的ファイル
app.mount("/", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static"), html=True), name="static")
