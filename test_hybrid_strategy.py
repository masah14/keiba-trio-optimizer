"""
ハイブリッド戦略テスト

軸+穴+全 をベースに:
- 基本: 全組み合わせを100円で購入
- 強化: 「軸+穴2」に該当するものは200円（2倍）で購入
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


def run_hybrid_test():
    print("=" * 70, flush=True)
    print("=== ハイブリッド戦略テスト ===", flush=True)
    print("=" * 70, flush=True)
    
    all_races = load_races("data/2024_full")
    print(f"\nTotal races: {len(all_races)}", flush=True)
    
    n_train = int(len(all_races) * 0.7)
    train_races = all_races[:n_train]
    test_races = all_races[n_train:]
    
    print(f"Training: {len(train_races)}, Test: {len(test_races)}", flush=True)
    
    horse_stats, jockey_stats = build_stats(train_races)
    
    v3 = EVEngineV3(EVConfigV3(
        weight_base_ability=0.35, weight_course_fit=0.20,
        weight_recent_form=0.20, weight_jockey=0.15, weight_market=0.10,
        fav_factor=0.95, mid_factor=1.00, long_factor=1.05, extreme_factor=1.10
    ))
    
    base_unit = 100
    boost_unit = 200  # 穴2の場合は2倍
    
    # 戦略比較
    strategies = {
        '軸+穴+全（均一）': {'bets': 0, 'investment': 0, 'payout': 0, 'hits': 0},
        '軸+穴+全（穴2強化）': {'bets': 0, 'investment': 0, 'payout': 0, 'hits': 0, 'boosted_hits': 0},
        '軸1+穴2のみ': {'bets': 0, 'investment': 0, 'payout': 0, 'hits': 0},
    }
    
    for race in test_races:
        horses = race.get('horses', [])
        
        if len(horses) < 8:
            continue
        
        # プロファイル付与
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
        
        # 軸馬・穴馬を選定
        axis_horses = [h for h in calculated if h.get('popularity', 99) <= 2]
        hole_horses = [h for h in calculated if is_good_hole(h)]
        hole_nums = set(h['num'] for h in hole_horses)
        
        top3_nums = set(h['num'] for h in calculated if h.get('finish', 99) <= 3)
        
        if len(axis_horses) < 1 or len(hole_horses) < 1:
            continue
        
        axis = axis_horses[0]
        
        # 軸+穴+全 の組み合わせを生成
        for hole in hole_horses[:2]:
            remaining = [h for h in calculated 
                        if h['num'] != axis['num'] and h['num'] != hole['num']]
            
            for other in remaining[:5]:
                combo_nums = {axis['num'], hole['num'], other['num']}
                trio = [axis, hole, other]
                
                # この組み合わせが「軸+穴2」か判定
                is_double_hole = other['num'] in hole_nums
                
                est_payout_per_100 = estimate_trio_odds(trio) * 100
                
                # 戦略1: 均一（全て100円）
                strategies['軸+穴+全（均一）']['bets'] += 1
                strategies['軸+穴+全（均一）']['investment'] += base_unit
                if combo_nums == top3_nums:
                    strategies['軸+穴+全（均一）']['hits'] += 1
                    strategies['軸+穴+全（均一）']['payout'] += int(est_payout_per_100)
                
                # 戦略2: 穴2強化（穴馬2頭なら200円）
                bet_amount = boost_unit if is_double_hole else base_unit
                strategies['軸+穴+全（穴2強化）']['bets'] += 1
                strategies['軸+穴+全（穴2強化）']['investment'] += bet_amount
                if combo_nums == top3_nums:
                    strategies['軸+穴+全（穴2強化）']['hits'] += 1
                    payout = int(est_payout_per_100 * (bet_amount / 100))
                    strategies['軸+穴+全（穴2強化）']['payout'] += payout
                    if is_double_hole:
                        strategies['軸+穴+全（穴2強化）']['boosted_hits'] += 1
        
        # 戦略3: 軸1+穴2のみ
        if len(hole_horses) >= 2:
            for hole_combo in combinations(hole_horses[:3], 2):
                combo_nums = {axis['num'], hole_combo[0]['num'], hole_combo[1]['num']}
                
                strategies['軸1+穴2のみ']['bets'] += 1
                strategies['軸1+穴2のみ']['investment'] += base_unit
                if combo_nums == top3_nums:
                    strategies['軸1+穴2のみ']['hits'] += 1
                    est_payout = estimate_trio_odds([axis, hole_combo[0], hole_combo[1]]) * base_unit
                    strategies['軸1+穴2のみ']['payout'] += int(est_payout)
    
    # 結果表示
    print("\n" + "=" * 70, flush=True)
    print("=== 結果比較 ===", flush=True)
    print("=" * 70, flush=True)
    
    print(f"\n{'戦略':<20} | {'ベット':>6} | {'投資':>10} | {'払戻':>10} | {'損益':>10} | {'ROI':>7}", flush=True)
    print("-" * 80, flush=True)
    
    for name, stats in strategies.items():
        if stats['investment'] > 0:
            roi = stats['payout'] / stats['investment'] * 100
            profit = stats['payout'] - stats['investment']
            mark = "***" if roi >= 100 else ""
            
            print(f"{name:<20} | {stats['bets']:>6} | {stats['investment']:>9,} | {stats['payout']:>9,} | {profit:>+9,} | {roi:>6.1f}% {mark}", flush=True)
    
    print("\n" + "=" * 70, flush=True)
    
    # 最良戦略
    best_name = max(strategies.keys(), 
                   key=lambda k: strategies[k]['payout'] / max(1, strategies[k]['investment']))
    best = strategies[best_name]
    best_roi = best['payout'] / best['investment'] * 100 if best['investment'] > 0 else 0
    best_profit = best['payout'] - best['investment']
    
    print(f"\n最良戦略: {best_name}", flush=True)
    print(f"  ROI: {best_roi:.1f}%", flush=True)
    print(f"  利益: {best_profit:+,}円", flush=True)
    
    # ハイブリッドの詳細
    hybrid = strategies['軸+穴+全（穴2強化）']
    if hybrid['investment'] > 0:
        print(f"\n【ハイブリッド戦略の詳細】", flush=True)
        print(f"  通常的中: {hybrid['hits'] - hybrid['boosted_hits']}件", flush=True)
        print(f"  穴2強化的中: {hybrid['boosted_hits']}件（2倍配当）", flush=True)


if __name__ == "__main__":
    run_hybrid_test()
