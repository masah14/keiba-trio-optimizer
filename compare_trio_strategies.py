"""
三連複戦略比較

1. 軸1 + 穴2: 軸馬1頭 + 穴馬2頭
2. 軸2 + 穴1: 軸馬2頭 + 穴馬1頭
3. 軸 + 穴 + 全: 軸馬1頭 + 穴馬1頭 + 残り全馬（流し）
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
    
    return dict(horse_stats), dict(jockey_stats)


def estimate_trio_odds(horses):
    odds_product = 1.0
    for h in horses:
        odds_product *= h['odds']
    return max(2.0, odds_product * 0.04)


def is_good_hole(h):
    """穴馬条件"""
    odds = h.get('odds', 999)
    pop = h.get('popularity', 0)
    place_ev = h.get('place_ev', 0)
    conf = h.get('_scores', {}).get('confidence', 0)
    return pop >= 4 and place_ev > 1.0 and conf >= 0.7 and 10 <= odds <= 50


def run_comparison():
    print("=" * 70, flush=True)
    print("=== 三連複戦略 比較 ===", flush=True)
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
    
    bet_unit = 100
    
    # 3つの戦略
    strategies = {
        '軸1+穴2': {'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0, 'details': []},
        '軸2+穴1': {'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0, 'details': []},
        '軸+穴+全': {'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0, 'details': []},
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
        
        # 軸馬: 人気1-2位
        axis_horses = [h for h in calculated if h.get('popularity', 99) <= 2]
        
        # 穴馬: 厳選条件
        hole_horses = [h for h in calculated if is_good_hole(h)]
        
        # その他の馬（3番人気以降で穴馬以外）
        other_horses = [h for h in calculated 
                       if h.get('popularity', 0) >= 3 
                       and h not in hole_horses]
        
        # 着順
        top3_nums = set(h['num'] for h in calculated if h.get('finish', 99) <= 3)
        
        # 戦略1: 軸1 + 穴2
        if len(axis_horses) >= 1 and len(hole_horses) >= 2:
            for axis in axis_horses[:1]:  # 1番人気のみ
                for hole_combo in combinations(hole_horses[:3], 2):
                    combo_nums = {axis['num'], hole_combo[0]['num'], hole_combo[1]['num']}
                    
                    strategies['軸1+穴2']['bets'] += 1
                    strategies['軸1+穴2']['investment'] += bet_unit
                    
                    if combo_nums == top3_nums:
                        strategies['軸1+穴2']['hits'] += 1
                        est_payout = estimate_trio_odds([axis, hole_combo[0], hole_combo[1]]) * bet_unit
                        strategies['軸1+穴2']['payout'] += int(est_payout)
        
        # 戦略2: 軸2 + 穴1
        if len(axis_horses) >= 2 and len(hole_horses) >= 1:
            for axis_combo in combinations(axis_horses[:2], 2):
                for hole in hole_horses[:2]:
                    combo_nums = {axis_combo[0]['num'], axis_combo[1]['num'], hole['num']}
                    
                    strategies['軸2+穴1']['bets'] += 1
                    strategies['軸2+穴1']['investment'] += bet_unit
                    
                    if combo_nums == top3_nums:
                        strategies['軸2+穴1']['hits'] += 1
                        est_payout = estimate_trio_odds([axis_combo[0], axis_combo[1], hole]) * bet_unit
                        strategies['軸2+穴1']['payout'] += int(est_payout)
        
        # 戦略3: 軸 + 穴 + 全（流し）
        if len(axis_horses) >= 1 and len(hole_horses) >= 1:
            axis = axis_horses[0]  # 1番人気
            
            for hole in hole_horses[:2]:  # 穴馬2頭まで
                # 残りの馬全部と組み合わせ
                remaining = [h for h in calculated 
                            if h['num'] != axis['num'] and h['num'] != hole['num']]
                
                for other in remaining[:5]:  # 最大5頭まで
                    combo_nums = {axis['num'], hole['num'], other['num']}
                    
                    strategies['軸+穴+全']['bets'] += 1
                    strategies['軸+穴+全']['investment'] += bet_unit
                    
                    if combo_nums == top3_nums:
                        strategies['軸+穴+全']['hits'] += 1
                        est_payout = estimate_trio_odds([axis, hole, other]) * bet_unit
                        strategies['軸+穴+全']['payout'] += int(est_payout)
    
    # 結果表示
    print("\n" + "=" * 70, flush=True)
    print("=== 結果比較 ===", flush=True)
    print("=" * 70, flush=True)
    
    print(f"\n{'戦略':<15} | {'ベット':>8} | {'的中':>5} | {'的中率':>7} | {'損益':>12} | {'ROI':>8}", flush=True)
    print("-" * 70, flush=True)
    
    results = []
    for name, stats in strategies.items():
        if stats['investment'] > 0:
            roi = stats['payout'] / stats['investment'] * 100
            hit_rate = stats['hits'] / stats['bets'] * 100 if stats['bets'] > 0 else 0
            profit = stats['payout'] - stats['investment']
            
            mark = "***" if roi >= 100 else ""
            print(f"{name:<15} | {stats['bets']:>8} | {stats['hits']:>5} | {hit_rate:>6.1f}% | {profit:>+11,} | {roi:>7.1f}% {mark}", flush=True)
            
            results.append({
                'name': name,
                'bets': stats['bets'],
                'hits': stats['hits'],
                'hit_rate': hit_rate,
                'profit': profit,
                'roi': roi
            })
    
    print("\n" + "=" * 70, flush=True)
    
    if results:
        best = max(results, key=lambda x: x['roi'])
        print(f"\n最良戦略: {best['name']}", flush=True)
        print(f"  ROI: {best['roi']:.1f}%", flush=True)
        print(f"  損益: {best['profit']:+,}円", flush=True)
        print(f"  的中率: {best['hit_rate']:.1f}%", flush=True)
        
        # コスト効率
        print("\n【コスト効率分析】", flush=True)
        for r in sorted(results, key=lambda x: x['bets']):
            cost_per_hit = r['bets'] / max(1, r['hits'])
            print(f"  {r['name']}: {r['bets']}点購入 / {r['hits']}的中 = {cost_per_hit:.1f}点/的中", flush=True)


if __name__ == "__main__":
    run_comparison()
