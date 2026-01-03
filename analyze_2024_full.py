"""
2024年全レース 三連複戦略 収支分析
- クラス別
- 距離別（カスタム定義）
実際の払い戻しデータ使用
"""

import json
import os
import sys
from collections import defaultdict
from itertools import combinations

sys.path.insert(0, 'app')

from ev_engine_v3 import EVEngineV3, EVConfigV3


def get_distance_category(distance):
    if distance <= 1400:
        return 'Sprint (<=1400m)'
    elif distance <= 1800:
        return 'Mile (1401-1800m)'
    elif distance <= 2400:
        return 'Middle (2000-2400m)'
    else:
        return 'Long (2500m+)'


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
    
    if popularity < 4:
        return False
    if place_ev < min_ev:
        return False
    if confidence < min_confidence:
        return False
    if odds < 10 or odds > 50:
        return False
    
    return True


def run_full_analysis():
    print("=" * 100)
    print("2024 Full Year Trio Strategy Analysis (REAL Payout Data)")
    print("=" * 100)
    
    # レースロード
    all_races = load_races_with_payout("data/2024_full")
    print(f"\nRaces with trio payout: {len(all_races)}")
    
    if len(all_races) < 100:
        print("WARNING: Less than 100 races with payout data. Results may be unreliable.")
    
    # トレーニング/テスト分割（30%/70%）
    n_train = int(len(all_races) * 0.3)
    train_races = all_races[:n_train]
    test_races = all_races[n_train:]
    
    print(f"Training: {len(train_races)}, Test: {len(test_races)}")
    
    horse_stats, jockey_stats = build_stats(train_races)
    print(f"Horses: {len(horse_stats)}, Jockeys: {len(jockey_stats)}")
    
    v3 = EVEngineV3(EVConfigV3(
        weight_base_ability=0.35, weight_course_fit=0.20,
        weight_recent_form=0.20, weight_jockey=0.15, weight_market=0.10,
        fav_factor=0.95, mid_factor=1.00, long_factor=1.05, extreme_factor=1.10
    ))
    
    bet_unit = 100
    min_ev = 1.0
    min_conf = 0.7
    
    # 統計
    class_stats = defaultdict(lambda: {'races': 0, 'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0})
    distance_stats = defaultdict(lambda: {'races': 0, 'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0})
    
    for race in test_races:
        horses = race.get('horses', [])
        race_info = race.get('race_info', {})
        distance = race_info.get('distance', 0)
        race_class = race_info.get('class', 'Other')
        
        if len(horses) < 8 or distance == 0:
            continue
        
        dist_cat = get_distance_category(distance)
        
        class_stats[race_class]['races'] += 1
        distance_stats[dist_cat]['races'] += 1
        
        # 実際の三連複払い戻し
        real_trio = race.get('payouts', {}).get('trio', [])
        winning_combo = set(real_trio[0]['combo']) if real_trio else set()
        winning_payout = real_trio[0]['payout'] if real_trio else 0
        
        # ホース統計を注入
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
        
        # 軸馬: 1番人気
        axis_horses = [h for h in calculated if h.get('popularity', 99) == 1]
        
        # 穴馬
        hole_horses = [h for h in calculated if is_good_hole_horse(h, min_ev=min_ev, min_confidence=min_conf)]
        
        if len(axis_horses) >= 1 and len(hole_horses) >= 2:
            for axis in axis_horses[:1]:
                for hole_combo in combinations(hole_horses[:3], 2):
                    combo_nums = {axis['num'], hole_combo[0]['num'], hole_combo[1]['num']}
                    
                    # クラス別
                    class_stats[race_class]['bets'] += 1
                    class_stats[race_class]['investment'] += bet_unit
                    
                    # 距離別
                    distance_stats[dist_cat]['bets'] += 1
                    distance_stats[dist_cat]['investment'] += bet_unit
                    
                    if combo_nums == winning_combo:
                        class_stats[race_class]['hits'] += 1
                        class_stats[race_class]['payout'] += winning_payout
                        
                        distance_stats[dist_cat]['hits'] += 1
                        distance_stats[dist_cat]['payout'] += winning_payout
    
    # === クラス別結果 ===
    print("\n" + "=" * 100)
    print("1. CLASS-BASED P&L (Real Payout)")
    print("=" * 100)
    print(f"{'Class':<20} {'Races':>8} {'Bets':>8} {'Hits':>6} {'Investment':>12} {'Payout':>12} {'P&L':>12} {'ROI':>8}")
    print("-" * 100)
    
    class_order = ['GI', 'GII', 'GIII', 'Listed', 'Open', '3-Win', '2-Win', '1-Win', 'Maiden', 'Newcomer', 'Other']
    class_map = {
        'GI': 'GI', 'GII': 'GII', 'GIII': 'GIII',
        'Listed': 'Listed', 'Open': 'Open',
        '3-Win': '3-Win', '2-Win': '2-Win', '1-Win': '1-Win',
        'Maiden': 'Maiden', 'Newcomer': 'Newcomer', 'Other': 'Other'
    }
    
    total_class = {'races': 0, 'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0}
    
    for cls in sorted(class_stats.keys(), key=lambda x: class_order.index(x) if x in class_order else 99):
        data = class_stats[cls]
        if data['races'] == 0:
            continue
        
        profit = data['payout'] - data['investment']
        roi = (data['payout'] / data['investment'] * 100) if data['investment'] > 0 else 0
        
        mark = "<<" if roi >= 100 else ""
        print(f"{cls:<20} {data['races']:>8} {data['bets']:>8} {data['hits']:>6} {data['investment']:>12,} {data['payout']:>12,} {profit:>+12,} {roi:>7.1f}% {mark}")
        
        for k in total_class:
            total_class[k] += data[k]
    
    print("-" * 100)
    profit = total_class['payout'] - total_class['investment']
    roi = (total_class['payout'] / total_class['investment'] * 100) if total_class['investment'] > 0 else 0
    print(f"{'TOTAL':<20} {total_class['races']:>8} {total_class['bets']:>8} {total_class['hits']:>6} {total_class['investment']:>12,} {total_class['payout']:>12,} {profit:>+12,} {roi:>7.1f}%")
    
    # === 距離別結果 ===
    print("\n" + "=" * 100)
    print("2. DISTANCE-BASED P&L (Custom: Middle=2000-2400m, Long=2500m+)")
    print("=" * 100)
    print(f"{'Distance':<25} {'Races':>8} {'Bets':>8} {'Hits':>6} {'Investment':>12} {'Payout':>12} {'P&L':>12} {'ROI':>8}")
    print("-" * 100)
    
    total_dist = {'races': 0, 'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0}
    
    for cat in ['Sprint (<=1400m)', 'Mile (1401-1800m)', 'Middle (2000-2400m)', 'Long (2500m+)']:
        data = distance_stats[cat]
        if data['races'] == 0:
            continue
        
        profit = data['payout'] - data['investment']
        roi = (data['payout'] / data['investment'] * 100) if data['investment'] > 0 else 0
        
        mark = "<<" if roi >= 100 else ""
        print(f"{cat:<25} {data['races']:>8} {data['bets']:>8} {data['hits']:>6} {data['investment']:>12,} {data['payout']:>12,} {profit:>+12,} {roi:>7.1f}% {mark}")
        
        for k in total_dist:
            total_dist[k] += data[k]
    
    print("-" * 100)
    profit = total_dist['payout'] - total_dist['investment']
    roi = (total_dist['payout'] / total_dist['investment'] * 100) if total_dist['investment'] > 0 else 0
    print(f"{'TOTAL':<25} {total_dist['races']:>8} {total_dist['bets']:>8} {total_dist['hits']:>6} {total_dist['investment']:>12,} {total_dist['payout']:>12,} {profit:>+12,} {roi:>7.1f}%")
    print("=" * 100)


if __name__ == "__main__":
    run_full_analysis()
