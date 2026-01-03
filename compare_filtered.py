"""
三連複ナガシ戦略 - 条件付き比較
条件:
- 距離: マイル(1401-1800m)、長距離(2500m+)
- クラス: GIII、未勝利、2勝クラス
"""

import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, 'app')

from ev_engine_v3 import EVEngineV3, EVConfigV3


def get_distance_category(distance):
    if distance <= 1400:
        return 'sprint'
    elif distance <= 1800:
        return 'mile'
    elif distance <= 2400:
        return 'middle'
    else:
        return 'long'


def load_races_with_payout(cache_dir):
    races = []
    if not os.path.exists(cache_dir):
        return races
    for f in os.listdir(cache_dir):
        if f.startswith('race_') and f.endswith('.json'):
            with open(os.path.join(cache_dir, f), 'r', encoding='utf-8') as fp:
                race = json.load(fp)
            if race.get('payouts', {}).get('trio') and race.get('horses') and len(race['horses']) >= 8:
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


def run_filtered_comparison():
    print("=" * 100)
    print("Trio Nagashi Strategy - FILTERED COMPARISON")
    print("Filter: Distance = Mile/Long, Class = GIII/Maiden/2-Win")
    print("=" * 100)
    
    all_races = load_races_with_payout("data/2024_full")
    print(f"\nTotal races with payout: {len(all_races)}")
    
    # フィルタ条件
    target_distances = ['mile', 'long']  # マイル、長距離
    target_classes = ['GIII', '未勝利', '2勝クラス']
    
    # フィルタリング
    filtered_races = []
    for race in all_races:
        race_info = race.get('race_info', {})
        distance = race_info.get('distance', 0)
        race_class = race_info.get('class', '')
        
        dist_cat = get_distance_category(distance)
        
        if dist_cat in target_distances and race_class in target_classes:
            filtered_races.append(race)
    
    print(f"Filtered races: {len(filtered_races)}")
    
    if len(filtered_races) < 10:
        print("Not enough data!")
        return
    
    # クラス分布
    class_dist = defaultdict(int)
    dist_dist = defaultdict(int)
    for race in filtered_races:
        class_dist[race.get('race_info', {}).get('class', 'Other')] += 1
        dist_dist[get_distance_category(race.get('race_info', {}).get('distance', 0))] += 1
    
    print(f"Class distribution: {dict(class_dist)}")
    print(f"Distance distribution: {dict(dist_dist)}")
    
    # 30% training, 70% test
    n_train = int(len(filtered_races) * 0.3)
    train_races = filtered_races[:n_train]
    test_races = filtered_races[n_train:]
    
    print(f"Training: {len(train_races)}, Test: {len(test_races)}")
    
    horse_stats, jockey_stats = build_stats(train_races)
    v3 = EVEngineV3(EVConfigV3())
    
    bet_unit = 100
    
    # 3パターン
    patterns = {
        '1-3 fav + hole + all': {'axis_max': 3, 'stats': {'races': 0, 'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0}},
        '1-2 fav + hole + all': {'axis_max': 2, 'stats': {'races': 0, 'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0}},
        '1 fav + hole + all':   {'axis_max': 1, 'stats': {'races': 0, 'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0}}
    }
    
    for race in test_races:
        horses = race.get('horses', [])
        if len(horses) < 8:
            continue
        
        real_trio = race.get('payouts', {}).get('trio', [])
        if not real_trio:
            continue
        winning_combo = set(real_trio[0]['combo'])
        winning_payout = real_trio[0]['payout']
        
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
        
        hole_horses = [h for h in calculated if is_good_hole_horse(h)]
        
        if len(hole_horses) < 1:
            continue
        
        for pattern_name, pattern_info in patterns.items():
            axis_max = pattern_info['axis_max']
            stats = pattern_info['stats']
            
            axis_horses = [h for h in calculated if h.get('popularity', 99) <= axis_max]
            
            if len(axis_horses) == 0:
                continue
            
            stats['races'] += 1
            
            for axis in axis_horses:
                for hole in hole_horses[:3]:
                    if hole['num'] == axis['num']:
                        continue
                    
                    others = [h for h in calculated if h['num'] not in {axis['num'], hole['num']}]
                    
                    for other in others:
                        combo = {axis['num'], hole['num'], other['num']}
                        
                        stats['bets'] += 1
                        stats['investment'] += bet_unit
                        
                        if combo == winning_combo:
                            stats['hits'] += 1
                            stats['payout'] += winning_payout
    
    # 結果
    print("\n" + "=" * 100)
    print("RESULTS (Filtered: Mile/Long + GIII/Maiden/2-Win)")
    print("=" * 100)
    print(f"{'Pattern':<25} {'Races':>8} {'Bets':>10} {'Hits':>6} {'Investment':>12} {'Payout':>12} {'P&L':>12} {'ROI':>8}")
    print("-" * 100)
    
    for pattern_name, pattern_info in patterns.items():
        stats = pattern_info['stats']
        profit = stats['payout'] - stats['investment']
        roi = (stats['payout'] / stats['investment'] * 100) if stats['investment'] > 0 else 0
        
        mark = "<<" if roi >= 100 else ""
        print(f"{pattern_name:<25} {stats['races']:>8} {stats['bets']:>10,} {stats['hits']:>6} {stats['investment']:>12,} {stats['payout']:>12,} {profit:>+12,} {roi:>7.1f}% {mark}")
    
    print("=" * 100)
    
    best = max(patterns.items(), key=lambda x: x[1]['stats']['payout'] - x[1]['stats']['investment'])
    print(f"\nBest: {best[0]}")
    
    best_stats = best[1]['stats']
    if best_stats['investment'] > 0:
        roi = best_stats['payout'] / best_stats['investment'] * 100
        print(f"ROI: {roi:.1f}%")


if __name__ == "__main__":
    run_filtered_comparison()
