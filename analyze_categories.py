"""
カテゴリ別収支分析

コース別、距離別、グレード別に:
- 単勝
- 複勝  
- 三連複（軸1+穴2戦略）
の収支を分析
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
            if race.get('horses') and len(race['horses']) >= 5:
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


def analyze_category(test_races, horse_stats, jockey_stats, v3, category_func, category_name):
    """カテゴリ別に分析"""
    
    results = defaultdict(lambda: {
        'races': 0,
        'win': {'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0},
        'place': {'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0},
        'trio': {'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0},
    })
    
    bet_unit = 100
    
    for race in test_races:
        horses = race.get('horses', [])
        payouts = race.get('payouts', {'win': {}, 'place': {}})
        race_info = race.get('race_info', {})
        
        # カテゴリ取得
        category = category_func(race)
        if not category:
            continue
        
        results[category]['races'] += 1
        
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
        top3_nums = set(h['num'] for h in calculated if h.get('finish', 99) <= 3)
        
        # 単勝・複勝
        for h in calculated:
            num = h['num']
            finish = h.get('finish', 0)
            odds = h.get('odds', 999)
            confidence = h.get('_scores', {}).get('confidence', 0)
            
            if odds > 30:
                continue
            
            # 単勝 EV >= 1.5
            if h.get('win_ev', 0) >= 1.5 and confidence >= 0.7:
                results[category]['win']['bets'] += 1
                results[category]['win']['investment'] += bet_unit
                if finish == 1:
                    results[category]['win']['hits'] += 1
                    payout = payouts.get('win', {}).get(str(num), 0)
                    results[category]['win']['payout'] += payout
            
            # 複勝 EV >= 1.0
            if h.get('place_ev', 0) >= 1.0 and confidence >= 0.7:
                results[category]['place']['bets'] += 1
                results[category]['place']['investment'] += bet_unit
                if finish <= 3:
                    results[category]['place']['hits'] += 1
                    payout = payouts.get('place', {}).get(str(num), 0)
                    results[category]['place']['payout'] += payout
        
        # 三連複
        if len(horses) >= 8:
            axis = [h for h in calculated if h.get('popularity', 99) <= 2]
            holes = [h for h in calculated if is_good_hole(h)]
            
            if len(axis) >= 1 and len(holes) >= 2:
                for a in axis[:1]:
                    for hole_combo in combinations(holes[:3], 2):
                        combo_nums = {a['num'], hole_combo[0]['num'], hole_combo[1]['num']}
                        
                        results[category]['trio']['bets'] += 1
                        results[category]['trio']['investment'] += bet_unit
                        
                        if combo_nums == top3_nums:
                            results[category]['trio']['hits'] += 1
                            est_payout = estimate_trio_odds([a, hole_combo[0], hole_combo[1]]) * bet_unit
                            results[category]['trio']['payout'] += int(est_payout)
    
    return dict(results)


def print_results(results, category_name):
    print(f"\n{'=' * 80}", flush=True)
    print(f"=== {category_name} ===", flush=True)
    print(f"{'=' * 80}", flush=True)
    
    print(f"\n{'Category':<20} | {'Races':>5} | {'Type':<6} | {'Bets':>5} | {'Hits':>4} | {'Profit':>10} | {'ROI':>7}", flush=True)
    print("-" * 80, flush=True)
    
    sorted_results = sorted(results.items(), key=lambda x: x[0])
    
    for category, data in sorted_results:
        printed_category = True
        for bet_type in ['win', 'place', 'trio']:
            stats = data[bet_type]
            if stats['investment'] > 0:
                roi = stats['payout'] / stats['investment'] * 100
                profit = stats['payout'] - stats['investment']
                mark = "***" if roi >= 100 else ""
                
                cat_display = category if printed_category else ""
                races_display = data['races'] if printed_category else ""
                printed_category = False
                
                type_jp = {'win': '単勝', 'place': '複勝', 'trio': '三連複'}[bet_type]
                
                print(f"{cat_display:<20} | {races_display:>5} | {type_jp:<6} | {stats['bets']:>5} | {stats['hits']:>4} | {profit:>+9,} | {roi:>6.1f}% {mark}", flush=True)


def run_analysis():
    print("=" * 80, flush=True)
    print("=== カテゴリ別収支分析 ===", flush=True)
    print("=" * 80, flush=True)
    
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
    
    # 1. コース別
    def get_course(race):
        return race.get('race_info', {}).get('course', '')
    
    course_results = analyze_category(test_races, horse_stats, jockey_stats, v3, get_course, "Course")
    print_results(course_results, "コース別")
    
    # 2. 距離別
    def get_distance_cat(race):
        dist = race.get('race_info', {}).get('distance', 0)
        if dist > 0:
            return get_distance_category(dist)
        return None
    
    distance_results = analyze_category(test_races, horse_stats, jockey_stats, v3, get_distance_cat, "Distance")
    print_results(distance_results, "距離別")
    
    # 3. 総合サマリー
    print(f"\n{'=' * 80}", flush=True)
    print("=== 高収益カテゴリ TOP5 ===", flush=True)
    print(f"{'=' * 80}", flush=True)
    
    all_combos = []
    for category, data in course_results.items():
        for bet_type in ['win', 'place', 'trio']:
            stats = data[bet_type]
            if stats['investment'] > 0 and stats['bets'] >= 10:
                roi = stats['payout'] / stats['investment'] * 100
                profit = stats['payout'] - stats['investment']
                all_combos.append({
                    'category': f"{category} ({bet_type})",
                    'bets': stats['bets'],
                    'roi': roi,
                    'profit': profit
                })
    
    for category, data in distance_results.items():
        for bet_type in ['win', 'place', 'trio']:
            stats = data[bet_type]
            if stats['investment'] > 0 and stats['bets'] >= 10:
                roi = stats['payout'] / stats['investment'] * 100
                profit = stats['payout'] - stats['investment']
                all_combos.append({
                    'category': f"{category} ({bet_type})",
                    'bets': stats['bets'],
                    'roi': roi,
                    'profit': profit
                })
    
    top5 = sorted(all_combos, key=lambda x: x['roi'], reverse=True)[:5]
    
    print(f"\n{'Category':<35} | {'Bets':>6} | {'Profit':>10} | {'ROI':>8}", flush=True)
    print("-" * 70, flush=True)
    
    for item in top5:
        mark = "***" if item['roi'] >= 100 else ""
        print(f"{item['category']:<35} | {item['bets']:>6} | {item['profit']:>+9,} | {item['roi']:>7.1f}% {mark}", flush=True)


if __name__ == "__main__":
    run_analysis()
