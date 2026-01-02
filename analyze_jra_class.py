"""
JRAクラス別収支分析

クラス: GI, GII, GIII, リステッド, オープン, 3勝クラス, 2勝クラス, 1勝クラス, 未勝利, 新馬
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


def run_class_analysis():
    print("=" * 80, flush=True)
    print("=== JRAクラス別収支分析 ===", flush=True)
    print("=" * 80, flush=True)
    
    train_races = load_races("data/2023_full")
    print(f"\n訓練 (2023年): {len(train_races)} レース", flush=True)
    
    test_races = load_races("data/2024_full")
    print(f"テスト (2024年): {len(test_races)} レース", flush=True)
    
    horse_stats, jockey_stats = build_stats(train_races)
    print(f"馬: {len(horse_stats)}頭, 騎手: {len(jockey_stats)}名", flush=True)
    
    v3 = EVEngineV3(EVConfigV3(
        weight_base_ability=0.35, weight_course_fit=0.20,
        weight_recent_form=0.20, weight_jockey=0.15, weight_market=0.10,
        fav_factor=0.95, mid_factor=1.00, long_factor=1.05, extreme_factor=1.10
    ))
    
    base_unit = 100
    boost_unit = 200
    
    # クラス別に集計
    results_by_class = defaultdict(lambda: {
        'races': 0, 'bets': 0, 'investment': 0, 'payout': 0, 'hits': 0,
    })
    
    total_stats = {'races': 0, 'bets': 0, 'investment': 0, 'payout': 0, 'hits': 0}
    
    for race in test_races:
        horses = race.get('horses', [])
        race_class = race.get('race_info', {}).get('class', 'その他')
        
        if len(horses) < 8:
            continue
        
        results_by_class[race_class]['races'] += 1
        total_stats['races'] += 1
        
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
        
        for hole in hole_horses[:2]:
            remaining = [h for h in calculated 
                        if h['num'] != axis['num'] and h['num'] != hole['num']]
            
            for other in remaining[:5]:
                combo_nums = {axis['num'], hole['num'], other['num']}
                trio = [axis, hole, other]
                
                is_double_hole = other['num'] in hole_nums
                bet_amount = boost_unit if is_double_hole else base_unit
                
                results_by_class[race_class]['bets'] += 1
                results_by_class[race_class]['investment'] += bet_amount
                total_stats['bets'] += 1
                total_stats['investment'] += bet_amount
                
                if combo_nums == top3_nums:
                    est_payout = estimate_trio_odds(trio) * bet_amount / 100
                    results_by_class[race_class]['hits'] += 1
                    results_by_class[race_class]['payout'] += int(est_payout * 100)
                    total_stats['hits'] += 1
                    total_stats['payout'] += int(est_payout * 100)
    
    # 結果表示
    print("\n" + "=" * 80, flush=True)
    print("=== JRAクラス別 結果 (ハイブリッド戦略) ===", flush=True)
    print("=" * 80, flush=True)
    
    print(f"\n{'クラス':<15} | {'レース':>5} | {'ベット':>6} | {'投資':>10} | {'払戻':>10} | {'損益':>10} | {'ROI':>7}", flush=True)
    print("-" * 85, flush=True)
    
    # クラス順序
    class_order = ['GI', 'GII', 'GIII', 'リステッド', 'オープン', '3勝クラス', '2勝クラス', '1勝クラス', '未勝利', '新馬', 'その他']
    
    for cls in class_order:
        if cls in results_by_class:
            stats = results_by_class[cls]
            if stats['investment'] > 0:
                roi = stats['payout'] / stats['investment'] * 100
                profit = stats['payout'] - stats['investment']
                mark = "***" if roi >= 100 else ""
                
                print(f"{cls:<15} | {stats['races']:>5} | {stats['bets']:>6} | {stats['investment']:>9,} | {stats['payout']:>9,} | {profit:>+9,} | {roi:>6.1f}% {mark}", flush=True)
    
    print("-" * 85, flush=True)
    
    if total_stats['investment'] > 0:
        total_roi = total_stats['payout'] / total_stats['investment'] * 100
        total_profit = total_stats['payout'] - total_stats['investment']
        mark = "***" if total_roi >= 100 else ""
        
        print(f"{'全体':<15} | {total_stats['races']:>5} | {total_stats['bets']:>6} | {total_stats['investment']:>9,} | {total_stats['payout']:>9,} | {total_profit:>+9,} | {total_roi:>6.1f}% {mark}", flush=True)
    
    print("\n" + "=" * 80, flush=True)
    
    # ベスト/ワースト
    sorted_classes = sorted(
        [(cls, stats) for cls, stats in results_by_class.items() if stats['investment'] > 0],
        key=lambda x: x[1]['payout'] / x[1]['investment'],
        reverse=True
    )
    
    if sorted_classes:
        print("\n【ベスト3】", flush=True)
        for i, (cls, stats) in enumerate(sorted_classes[:3]):
            roi = stats['payout'] / stats['investment'] * 100
            profit = stats['payout'] - stats['investment']
            print(f"  {i+1}. {cls}: ROI {roi:.1f}%, 損益 {profit:+,}円", flush=True)
        
        print("\n【ワースト3】", flush=True)
        for i, (cls, stats) in enumerate(sorted_classes[-3:]):
            roi = stats['payout'] / stats['investment'] * 100
            profit = stats['payout'] - stats['investment']
            print(f"  {i+1}. {cls}: ROI {roi:.1f}%, 損益 {profit:+,}円", flush=True)


if __name__ == "__main__":
    run_class_analysis()
