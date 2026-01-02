"""
2023-2025年 JRAレース バックテスト
- 期待値100%超えの単勝・複勝を買った場合の収支を検証
- 出走前情報のみで期待値を算出し、レース後に結果を照合
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import numpy as np
import time
import re
import os
from datetime import datetime, timedelta
import json

# ========== 設定 ==========
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

# bias_factors (アウトサイダー・バイアス補正)
BIAS_FACTORS = {
    "fav": 0.85,      # オッズ < 5
    "mid": 1.1,       # 5 <= オッズ < 20
    "long": 1.4,      # 20 <= オッズ < 50
    "extreme": 1.8    # オッズ >= 50
}

def get_bias(odds):
    if odds < 5: return BIAS_FACTORS["fav"]
    elif odds < 20: return BIAS_FACTORS["mid"]
    elif odds < 50: return BIAS_FACTORS["long"]
    else: return BIAS_FACTORS["extreme"]

# ========== Netkeiba スクレイパー (改良版) ==========

def get_race_ids_from_db(year, month):
    """db.netkeiba.comからレースIDを取得"""
    race_ids = []
    
    # 月の日数を計算
    if month == 12:
        next_month = datetime(year + 1, 1, 1)
    else:
        next_month = datetime(year, month + 1, 1)
    first_day = datetime(year, month, 1)
    days_in_month = (next_month - first_day).days
    
    # 各週末（土日）をチェック
    for day in range(1, days_in_month + 1):
        date = datetime(year, month, day)
        # 土曜(5)か日曜(6)のみ
        if date.weekday() in [5, 6]:
            date_str = date.strftime('%Y%m%d')
            
            # 中央競馬の主要競馬場 (01=札幌, 02=函館, 03=福島, 04=新潟, 05=東京, 06=中山, 07=中京, 08=京都, 09=阪神, 10=小倉)
            for course in ['01', '02', '03', '04', '05', '06', '07', '08', '09', '10']:
                # 各レース (01-12)
                for race_num in range(1, 13):
                    # race_id形式: YYYYCCDDRRXX (年4桁 + 競馬場2桁 + 回次2桁 + 日2桁 + レース番号2桁)
                    # 簡易版として日付ベースのIDを生成
                    race_id = f"{year}{course}01{day:02d}{race_num:02d}"
                    race_ids.append(race_id)
    
    return race_ids

def get_race_ids_by_search(year, month):
    """netkeibaの検索機能からレースIDを取得"""
    race_ids = []
    
    # db.netkeiba.comの検索ページを使用
    # 年月を指定してレース一覧を取得
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    # 各開催日を生成 (週末)
    if month == 12:
        next_month = datetime(year + 1, 1, 1)
    else:
        next_month = datetime(year, month + 1, 1)
    first_day = datetime(year, month, 1)
    days_in_month = (next_month - first_day).days
    
    for day in range(1, days_in_month + 1):
        date = datetime(year, month, day)
        if date.weekday() in [5, 6]:  # 土日のみ
            date_str = date.strftime('%Y%m%d')
            
            # race_list.htmlを取得
            url = f"https://race.netkeiba.com/top/race_list.html?kaisai_date={date_str}"
            try:
                res = requests.get(url, headers=headers, timeout=10)
                res.encoding = 'utf-8'
                soup = BeautifulSoup(res.text, 'html.parser')
                
                # レースリンクを探す
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    # race_idを含むリンクを探す
                    match = re.search(r'race_id=(\d{12})', href)
                    if match:
                        race_ids.append(match.group(1))
                        
            except Exception as e:
                pass
            
            time.sleep(0.3)
    
    return list(set(race_ids))

def get_race_result_from_db(race_id):
    """
    db.netkeiba.comからレース結果を取得
    """
    url = f"https://db.netkeiba.com/race/{race_id}/"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    try:
        res = requests.get(url, headers=headers, timeout=15)
        res.encoding = 'EUC-JP'
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # レース情報
        race_info = {}
        title_elem = soup.find('h1')
        if title_elem:
            race_info['title'] = title_elem.text.strip()
        
        # 結果テーブル
        result_table = soup.find('table', class_='race_table_01')
        if not result_table:
            return None
            
        horses = []
        rows = result_table.find_all('tr')[1:]  # ヘッダー除く
        
        for row in rows:
            cols = row.find_all('td')
            if len(cols) < 13:
                continue
                
            try:
                # 着順
                finish = cols[0].text.strip()
                if not finish.isdigit():
                    continue  # 除外、中止など
                    
                # 馬番
                num_text = cols[2].text.strip()
                if not num_text.isdigit():
                    continue
                num = int(num_text)
                
                # 馬名
                horse_name_elem = cols[3].find('a')
                horse_name = horse_name_elem.text.strip() if horse_name_elem else ""
                
                # 騎手名
                jockey_elem = cols[6].find('a')
                jockey_name = jockey_elem.text.strip() if jockey_elem else ""
                
                # 単勝オッズ (11列目または12列目)
                odds = 0
                for idx in [12, 11, 10]:
                    if idx < len(cols):
                        odds_text = cols[idx].text.strip()
                        try:
                            odds = float(odds_text)
                            if odds > 0:
                                break
                        except:
                            continue
                
                # 人気
                popularity = 0
                for idx in [13, 12, 11]:
                    if idx < len(cols):
                        pop_text = cols[idx].text.strip()
                        if pop_text.isdigit():
                            popularity = int(pop_text)
                            break
                
                if odds <= 0:
                    continue
                    
                horses.append({
                    'num': num,
                    'name': horse_name,
                    'jockey': jockey_name,
                    'odds': odds,
                    'popularity': popularity,
                    'finish': int(finish)
                })
                
            except Exception as e:
                continue
        
        if len(horses) < 2:
            return None
        
        # 払戻金を取得
        payouts = get_payouts(soup)
        
        return {
            'race_id': race_id,
            'info': race_info,
            'horses': horses,
            'payouts': payouts
        }
        
    except Exception as e:
        return None

def get_payouts(soup):
    """払戻金テーブルから単勝・複勝の払戻を取得"""
    payouts = {'win': {}, 'place': {}}
    
    try:
        # 払戻テーブルを探す
        payout_tables = soup.find_all('table', class_='pay_table_01')
        
        for table in payout_tables:
            rows = table.find_all('tr')
            for row in rows:
                header = row.find('th')
                if not header:
                    continue
                    
                header_text = header.text.strip()
                cols = row.find_all('td')
                
                if '単勝' in header_text and len(cols) >= 2:
                    # 馬番
                    num_text = cols[0].text.strip()
                    # 払戻金
                    pay_text = cols[1].text.strip().replace(',', '').replace('円', '')
                    
                    nums = re.findall(r'\d+', num_text)
                    pays = re.findall(r'\d+', pay_text)
                    
                    for i, num in enumerate(nums):
                        if i < len(pays):
                            payouts['win'][int(num)] = int(pays[i])
                            
                elif '複勝' in header_text and len(cols) >= 2:
                    num_text = cols[0].text.strip()
                    pay_text = cols[1].text.strip().replace(',', '').replace('円', '')
                    
                    nums = re.findall(r'\d+', num_text)
                    pays = re.findall(r'\d+', pay_text)
                    
                    for i, num in enumerate(nums):
                        if i < len(pays):
                            payouts['place'][int(num)] = int(pays[i])
                                
    except Exception as e:
        pass
        
    return payouts

# ========== 期待値計算 (出走前情報のみ) ==========

def calculate_ev_prerace(horses):
    """
    出走前情報のみで期待値を計算
    - オッズ、人気から実力スコアを推定
    """
    if not horses or len(horses) == 0:
        return []
    
    # 1. 実力スコア計算 (人気とオッズをベースに)
    for h in horses:
        # 人気順位ベースのスコア (1位が最高)
        pop_score = max(0, 20 - h['popularity']) if h['popularity'] > 0 else 10
        
        # オッズベースのスコア (低いほど高スコア)
        odds_score = max(0, 50 / max(h['odds'], 1))
        
        h['strength_score'] = pop_score * 0.4 + odds_score * 0.6
    
    # 2. バイアス補正
    for h in horses:
        h['bias_factor'] = get_bias(h['odds'])
        h['adjusted_strength'] = h['strength_score'] * h['bias_factor']
    
    # 3. 正規化して真の勝率を計算
    total_strength = sum(h['adjusted_strength'] for h in horses)
    if total_strength > 0:
        for h in horses:
            h['true_win_prob'] = h['adjusted_strength'] / total_strength
    else:
        for h in horses:
            h['true_win_prob'] = 1 / len(horses)
    
    # 4. 単勝 EV
    for h in horses:
        h['win_ev'] = h['true_win_prob'] * h['odds']
    
    # 5. 複勝確率・EV推定
    for h in horses:
        mult = 2.8 if h['true_win_prob'] > 0.1 else 3.5
        h['place_prob'] = min(0.95, h['true_win_prob'] * mult)
        h['est_place_odds'] = h['odds'] / 3.8
        h['place_ev'] = h['place_prob'] * h['est_place_odds']
    
    return horses

# ========== バックテスト実行 ==========

def run_backtest(start_year=2023, end_year=2025):
    """2023-2025年のバックテストを実行"""
    
    results = {
        'win': {'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0},
        'place': {'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0}
    }
    
    total_races_processed = 0
    bet_unit = 100  # 1口100円
    
    print(f"=== バックテスト開始: {start_year}年 〜 {end_year}年 ===")
    print("(出走前情報のみで期待値を算出)")
    print()
    
    for year in range(start_year, end_year + 1):
        year_results = {
            'win': {'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0},
            'place': {'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0}
        }
        
        for month in range(1, 13):
            # 未来の月はスキップ (2025年1月2日現在なので2025年1月以降はスキップ)
            current_date = datetime(2026, 1, 2)
            check_date = datetime(year, month, 1)
            if check_date >= current_date:
                continue
                
            print(f"--- {year}年{month}月のレースを取得中... ---")
            
            # レースIDを取得
            race_ids = get_race_ids_by_search(year, month)
            print(f"  発見: {len(race_ids)}レース")
            
            month_races = 0
            
            for i, race_id in enumerate(race_ids):
                # レース結果を取得
                race_data = get_race_result_from_db(race_id)
                if not race_data or not race_data['horses']:
                    continue
                
                month_races += 1
                total_races_processed += 1
                
                # 出走前情報で期待値計算
                horses = calculate_ev_prerace(race_data['horses'])
                
                # EV >= 1.0 の馬を特定
                for h in horses:
                    # 単勝 EV >= 1.0
                    if h.get('win_ev', 0) >= 1.0:
                        results['win']['bets'] += 1
                        results['win']['investment'] += bet_unit
                        year_results['win']['bets'] += 1
                        year_results['win']['investment'] += bet_unit
                        
                        # 1着なら的中
                        if h['finish'] == 1:
                            results['win']['hits'] += 1
                            year_results['win']['hits'] += 1
                            payout = race_data['payouts']['win'].get(h['num'], 0)
                            results['win']['payout'] += payout
                            year_results['win']['payout'] += payout
                    
                    # 複勝 EV >= 1.0
                    if h.get('place_ev', 0) >= 1.0:
                        results['place']['bets'] += 1
                        results['place']['investment'] += bet_unit
                        year_results['place']['bets'] += 1
                        year_results['place']['investment'] += bet_unit
                        
                        # 3着以内なら的中
                        if h['finish'] <= 3:
                            results['place']['hits'] += 1
                            year_results['place']['hits'] += 1
                            payout = race_data['payouts']['place'].get(h['num'], 0)
                            results['place']['payout'] += payout
                            year_results['place']['payout'] += payout
                
                if (i + 1) % 20 == 0:
                    print(f"    処理中: {i+1}/{len(race_ids)}")
                
                time.sleep(0.2)  # サーバー負荷軽減
            
            print(f"  処理完了: {month_races}レース")
        
        # 年次サマリー
        print(f"\n=== {year}年 年間サマリー ===")
        for bet_type, name in [('win', '単勝'), ('place', '複勝')]:
            r = year_results[bet_type]
            if r['investment'] > 0:
                roi = r['payout'] / r['investment'] * 100
                hit_rate = r['hits'] / r['bets'] * 100 if r['bets'] > 0 else 0
                profit = r['payout'] - r['investment']
                print(f"  {name}: {r['bets']}件, 的中{r['hits']}件 ({hit_rate:.1f}%), ROI {roi:.1f}%, 損益 {profit:+,}円")
        print()
    
    # 最終結果
    print("\n" + "="*70)
    print("=== バックテスト最終結果サマリー ===")
    print("="*70)
    print(f"対象期間: {start_year}年 〜 {end_year}年")
    print(f"処理レース数: {total_races_processed:,}レース")
    print()
    
    for bet_type, name in [('win', '単勝'), ('place', '複勝')]:
        r = results[bet_type]
        roi = (r['payout'] / r['investment'] * 100) if r['investment'] > 0 else 0
        hit_rate = (r['hits'] / r['bets'] * 100) if r['bets'] > 0 else 0
        profit = r['payout'] - r['investment']
        
        print(f"【{name}】(EV >= 100%)")
        print(f"  総ベット数: {r['bets']:,}件")
        print(f"  的中数: {r['hits']:,}件")
        print(f"  的中率: {hit_rate:.2f}%")
        print(f"  総投資額: {r['investment']:,}円")
        print(f"  総払戻額: {r['payout']:,}円")
        print(f"  純利益: {profit:+,}円")
        print(f"  ROI: {roi:.1f}%")
        print()
    
    # 結果をファイルに保存
    output = {
        'period': f"{start_year}-{end_year}",
        'total_races': total_races_processed,
        'results': results,
        'timestamp': datetime.now().isoformat()
    }
    
    with open(f"{DATA_DIR}/backtest_result_{start_year}_{end_year}.json", 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n結果を {DATA_DIR}/backtest_result_{start_year}_{end_year}.json に保存しました")
    
    return results

if __name__ == "__main__":
    run_backtest(2023, 2025)
