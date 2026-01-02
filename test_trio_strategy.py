"""
三連複戦略テスト

戦略:
1. 軸馬: 人気1-3位（高確率で3着以内）
2. 穴馬: 複勝EV > 1.0 かつ 4番人気以降
3. 三連複: 軸馬2頭 + 穴馬1頭 の組み合わせ

仮説:
- 穴馬が来れば高配当
- 軸馬で確率を担保
- 組み合わせの妙で控除率を上回る
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
            if race.get('horses') and len(race['horses']) >= 8:  # 8頭以上のみ
                races.append(race)
    return races


def build_stats(races):
    horse_stats = defaultdict(lambda: {
        'runs': 0, 'wins': 0, 'places': 0, 'finishes': [],
    })
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


def estimate_trio_odds(horses_in_combo):
    """
    三連複オッズを推定
    
    単純なヒューリスティック:
    オッズ = (1着オッズ × 2着オッズ × 3着オッズ) × 0.05
    """
    odds_product = 1.0
    for h in horses_in_combo:
        odds_product *= h['odds']
    
    # 三連複は三連単より約6倍低い配当
    # 経験則として 0.03-0.08 の係数
    estimated = odds_product * 0.04
    
    # 最低オッズ
    return max(1.5, estimated)


def run_trio_strategy_test():
    print("=" * 70, flush=True)
    print("=== 三連複戦略テスト ===", flush=True)
    print("=" * 70, flush=True)
    
    # データロード
    all_races = load_races("data/2024_full")
    print(f"\nTotal races: {len(all_races)}", flush=True)
    
    # 70:30 分割
    n_train = int(len(all_races) * 0.7)
    train_races = all_races[:n_train]
    test_races = all_races[n_train:]
    
    print(f"Training: {len(train_races)}, Test: {len(test_races)}", flush=True)
    
    # 統計構築
    horse_stats, jockey_stats = build_stats(train_races)
    print(f"Horses: {len(horse_stats)}, Jockeys: {len(jockey_stats)}", flush=True)
    
    v3 = EVEngineV3(EVConfigV3(
        weight_base_ability=0.35, weight_course_fit=0.20,
        weight_recent_form=0.20, weight_jockey=0.15, weight_market=0.10,
        fav_factor=0.95, mid_factor=1.00, long_factor=1.05, extreme_factor=1.10
    ))
    
    bet_unit = 100
    
    # 戦略別の結果
    strategies = {
        'axis2_hole1': {'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0},  # 軸2頭+穴1頭
        'axis1_hole2': {'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0},  # 軸1頭+穴2頭
        'random': {'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0},       # ランダム比較
    }
    
    print("\nTesting strategies...", flush=True)
    
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
        
        # EV計算
        calculated = v3.calculate_ev([h.copy() for h in horses])
        
        # 軸馬を選定（人気1-3位）
        axis_horses = [h for h in calculated if h.get('popularity', 99) <= 3]
        
        # 穴馬を選定（4番人気以降で複勝EV > 1.0）
        hole_horses = [
            h for h in calculated 
            if h.get('popularity', 0) >= 4 
            and h.get('place_ev', 0) > 1.0
            and h.get('odds', 999) <= 50  # オッズ50倍以下
        ]
        
        # 着順で的中判定
        top3_nums = set(h['num'] for h in calculated if h.get('finish', 99) <= 3)
        
        # 戦略1: 軸2頭 + 穴1頭
        if len(axis_horses) >= 2 and len(hole_horses) >= 1:
            for axis_combo in combinations(axis_horses[:3], 2):
                for hole in hole_horses[:2]:  # 最大2頭まで
                    combo_nums = {axis_combo[0]['num'], axis_combo[1]['num'], hole['num']}
                    
                    strategies['axis2_hole1']['bets'] += 1
                    strategies['axis2_hole1']['investment'] += bet_unit
                    
                    if combo_nums == top3_nums:
                        # 三連複的中！
                        strategies['axis2_hole1']['hits'] += 1
                        # 配当を推定（実際のデータがないため）
                        est_payout = estimate_trio_odds([axis_combo[0], axis_combo[1], hole]) * bet_unit
                        strategies['axis2_hole1']['payout'] += int(est_payout)
        
        # 戦略2: 軸1頭 + 穴2頭
        if len(axis_horses) >= 1 and len(hole_horses) >= 2:
            for axis in axis_horses[:2]:
                for hole_combo in combinations(hole_horses[:3], 2):
                    combo_nums = {axis['num'], hole_combo[0]['num'], hole_combo[1]['num']}
                    
                    strategies['axis1_hole2']['bets'] += 1
                    strategies['axis1_hole2']['investment'] += bet_unit
                    
                    if combo_nums == top3_nums:
                        strategies['axis1_hole2']['hits'] += 1
                        est_payout = estimate_trio_odds([axis, hole_combo[0], hole_combo[1]]) * bet_unit
                        strategies['axis1_hole2']['payout'] += int(est_payout)
        
        # ランダム比較（上位6頭から3頭選ぶ）
        top6 = sorted(calculated, key=lambda x: x.get('popularity', 99))[:6]
        for combo in list(combinations(top6, 3))[:5]:  # 最大5組
            combo_nums = {combo[0]['num'], combo[1]['num'], combo[2]['num']}
            
            strategies['random']['bets'] += 1
            strategies['random']['investment'] += bet_unit
            
            if combo_nums == top3_nums:
                strategies['random']['hits'] += 1
                est_payout = estimate_trio_odds(combo) * bet_unit
                strategies['random']['payout'] += int(est_payout)
    
    # 結果表示
    print("\n" + "=" * 70, flush=True)
    print("=== 三連複戦略 結果 ===", flush=True)
    print("=" * 70, flush=True)
    
    print(f"\n{'Strategy':<20} | {'Bets':>8} | {'Hits':>6} | {'Hit%':>7} | {'Profit':>12} | {'ROI':>8}", flush=True)
    print("-" * 75, flush=True)
    
    for name, stats in strategies.items():
        if stats['investment'] > 0:
            roi = stats['payout'] / stats['investment'] * 100
            hit_rate = stats['hits'] / stats['bets'] * 100 if stats['bets'] > 0 else 0
            profit = stats['payout'] - stats['investment']
            mark = "PASS" if roi >= 100 else ""
            
            print(f"{name:<20} | {stats['bets']:>8} | {stats['hits']:>6} | {hit_rate:>6.1f}% | {profit:>+11,} | {roi:>7.1f}% {mark}", flush=True)
    
    print("\n" + "=" * 70, flush=True)
    
    # 分析
    best = max(strategies.items(), key=lambda x: x[1]['payout'] / max(1, x[1]['investment']))
    print(f"\nBest strategy: {best[0]}", flush=True)
    
    if best[1]['investment'] > 0:
        best_roi = best[1]['payout'] / best[1]['investment'] * 100
        if best_roi >= 100:
            print(f"ROI: {best_roi:.1f}% - This strategy shows promise!", flush=True)
        else:
            print(f"ROI: {best_roi:.1f}% - Still not profitable.", flush=True)


if __name__ == "__main__":
    run_trio_strategy_test()
