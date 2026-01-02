"""
大規模ウォークフォワードテスト（2023-2024）

オーバーフィット防止:
- 訓練: 2023年データ (500レース)
- テスト: 2024年データ (620レース)

距離別に結果を報告
"""

import json
import os
import sys
from collections import defaultdict
from itertools import combinations

sys.path.insert(0, 'app')
sys.stdout.reconfigure(line_buffering=True)

from ev_engine_v3 import EVEngineV3, EVConfigV3


def load_races(cache_dir):
    races = []
    if not os.path.exists(cache_dir):
        return races
    for f in os.listdir(cache_dir):
        if f.startswith('race_') and f.endswith('.json'):
            with open(os.path.join(cache_dir, f), 'r', encoding='utf-8') as fp:
                race = json.load(fp)
            if race.get('horses') and len(race['horses']) >= 8:
                races.append(race)
    return races


def build_stats(races):
    horse_stats = defaultdict(lambda: {'runs': 0, 'wins': 0, 'places': 0, 'finishes': []})
    jockey_stats = defaultdict(lambda: {'runs': 0, 'wins': 0})
    
    for race in races:
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
    
    for stats in horse_stats.values():
        if stats['runs'] > 0:
            stats['win_rate'] = stats['wins'] / stats['runs']
            stats['place_rate'] = stats['places'] / stats['runs']
    
    for stats in jockey_stats.values():
        if stats['runs'] > 0:
            stats['win_rate'] = stats['wins'] / stats['runs']
    
    return dict(horse_stats), dict(jockey_stats)


def get_distance_category(distance):
    if distance <= 1400:
        return "Sprint (1400m-)"
    elif distance <= 1800:
        return "Mile (1600-1800m)"
    elif distance <= 2200:
        return "Middle (2000-2200m)"
    else:
        return "Long (2400m+)"


def estimate_trio_odds(horses):
    odds_product = 1.0
    for h in horses:
        odds_product *= h['odds']
    return max(2.0, odds_product * 0.04)


def is_good_hole(h):
    odds = h.get('odds', 999)
    pop = h.get('popularity', 0)
    place_ev = h.get('place_ev', 0)
    conf = h.get('_scores', {}).get('confidence', 0)
    return pop >= 4 and place_ev > 1.0 and conf >= 0.7 and 10 <= odds <= 50


def run_full_test():
    print("=" * 80, flush=True)
    print("=== 大規模ウォークフォワードテスト (2023-2024) ===", flush=True)
    print("=" * 80, flush=True)
    
    # 訓練データ: 2023年
    train_races = load_races("data/2023_full")
    print(f"\n訓練データ (2023年): {len(train_races)} レース", flush=True)
    
    # テストデータ: 2024年
    test_races = load_races("data/2024_full")
    print(f"テストデータ (2024年): {len(test_races)} レース", flush=True)
    
    # 2023年のデータで統計構築
    print("\n2023年データで統計構築（2024年は未知のデータ）...", flush=True)
    horse_stats, jockey_stats = build_stats(train_races)
    print(f"馬: {len(horse_stats)}頭, 騎手: {len(jockey_stats)}名", flush=True)
    
    v3 = EVEngineV3(EVConfigV3(
        weight_base_ability=0.35, weight_course_fit=0.20,
        weight_recent_form=0.20, weight_jockey=0.15, weight_market=0.10,
        fav_factor=0.95, mid_factor=1.00, long_factor=1.05, extreme_factor=1.10
    ))
    
    base_unit = 100
    boost_unit = 200
    
    # 距離別に結果を集計
    results_by_distance = defaultdict(lambda: {
        'races': 0,
        'bets': 0,
        'investment': 0,
        'payout': 0,
        'hits': 0,
        'boosted_hits': 0,
    })
    
    # 全体
    total_stats = {
        'races': 0,
        'bets': 0,
        'investment': 0,
        'payout': 0,
        'hits': 0,
        'boosted_hits': 0,
    }
    
    for race in test_races:
        horses = race.get('horses', [])
        distance = race.get('race_info', {}).get('distance', 0)
        
        if len(horses) < 8:
            continue
        
        dist_cat = get_distance_category(distance) if distance > 0 else "Unknown"
        
        results_by_distance[dist_cat]['races'] += 1
        total_stats['races'] += 1
        
        # プロファイル付与（2023年の統計のみ使用！）
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
        
        calculated = v3.calculate_ev([h.copy() for h in horses])
        
        axis_horses = [h for h in calculated if h.get('popularity', 99) <= 2]
        hole_horses = [h for h in calculated if is_good_hole(h)]
        hole_nums = set(h['num'] for h in hole_horses)
        
        top3_nums = set(h['num'] for h in calculated if h.get('finish', 99) <= 3)
        
        if len(axis_horses) < 1 or len(hole_horses) < 1:
            continue
        
        axis = axis_horses[0]
        
        # ハイブリッド戦略: 軸+穴+全（穴2強化）
        for hole in hole_horses[:2]:
            remaining = [h for h in calculated 
                        if h['num'] != axis['num'] and h['num'] != hole['num']]
            
            for other in remaining[:5]:
                combo_nums = {axis['num'], hole['num'], other['num']}
                trio = [axis, hole, other]
                
                is_double_hole = other['num'] in hole_nums
                bet_amount = boost_unit if is_double_hole else base_unit
                
                results_by_distance[dist_cat]['bets'] += 1
                results_by_distance[dist_cat]['investment'] += bet_amount
                total_stats['bets'] += 1
                total_stats['investment'] += bet_amount
                
                if combo_nums == top3_nums:
                    est_payout = estimate_trio_odds(trio) * bet_amount / 100
                    results_by_distance[dist_cat]['hits'] += 1
                    results_by_distance[dist_cat]['payout'] += int(est_payout * 100)
                    total_stats['hits'] += 1
                    total_stats['payout'] += int(est_payout * 100)
                    
                    if is_double_hole:
                        results_by_distance[dist_cat]['boosted_hits'] += 1
                        total_stats['boosted_hits'] += 1
    
    # 結果表示
    print("\n" + "=" * 80, flush=True)
    print("=== 距離別 結果 (ハイブリッド戦略: 軸+穴+全, 穴2強化) ===", flush=True)
    print("=" * 80, flush=True)
    
    print(f"\n{'距離':<20} | {'レース':>5} | {'ベット':>6} | {'投資':>10} | {'払戻':>10} | {'損益':>10} | {'ROI':>7}", flush=True)
    print("-" * 85, flush=True)
    
    for dist_cat in ['Sprint (1400m-)', 'Mile (1600-1800m)', 'Middle (2000-2200m)', 'Long (2400m+)']:
        if dist_cat in results_by_distance:
            stats = results_by_distance[dist_cat]
            if stats['investment'] > 0:
                roi = stats['payout'] / stats['investment'] * 100
                profit = stats['payout'] - stats['investment']
                mark = "***" if roi >= 100 else ""
                
                print(f"{dist_cat:<20} | {stats['races']:>5} | {stats['bets']:>6} | {stats['investment']:>9,} | {stats['payout']:>9,} | {profit:>+9,} | {roi:>6.1f}% {mark}", flush=True)
    
    print("-" * 85, flush=True)
    
    # 全体
    if total_stats['investment'] > 0:
        total_roi = total_stats['payout'] / total_stats['investment'] * 100
        total_profit = total_stats['payout'] - total_stats['investment']
        mark = "***" if total_roi >= 100 else ""
        
        print(f"{'全体':<20} | {total_stats['races']:>5} | {total_stats['bets']:>6} | {total_stats['investment']:>9,} | {total_stats['payout']:>9,} | {total_profit:>+9,} | {total_roi:>6.1f}% {mark}", flush=True)
    
    print("\n" + "=" * 80, flush=True)
    
    # 詳細
    print(f"\n【詳細】", flush=True)
    print(f"  総レース数: {total_stats['races']}", flush=True)
    print(f"  総ベット数: {total_stats['bets']}", flush=True)
    print(f"  的中数: {total_stats['hits']} (うち穴2強化: {total_stats['boosted_hits']})", flush=True)
    print(f"  的中率: {total_stats['hits'] / total_stats['bets'] * 100:.2f}% (有効)" if total_stats['bets'] > 0 else "", flush=True)
    
    if total_roi >= 100:
        print(f"\n*** ウォークフォワードテスト PASS! ***", flush=True)
        print(f"2023年のデータで学習し、未知の2024年データでプラス収支!", flush=True)
    else:
        print(f"\n*** ウォークフォワードテスト FAIL ***", flush=True)
        print(f"未知のデータではプラス収支にならず", flush=True)


if __name__ == "__main__":
    run_full_test()
