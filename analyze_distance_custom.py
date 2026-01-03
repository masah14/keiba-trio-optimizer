"""
三連複戦略 距離別収支分析（カスタム距離定義）

距離カテゴリ：
- スプリント: ～1400m
- マイル: 1401-1800m  
- 中距離: 2000-2400m（ユーザー定義）
- 長距離: 2500m～（ユーザー定義）
"""

import json
import os
import sys
from collections import defaultdict
from itertools import combinations

sys.path.insert(0, 'app')

from ev_engine_v3 import EVEngineV3, EVConfigV3

# 距離カテゴリ（カスタム定義）
def get_distance_category(distance):
    if distance <= 1400:
        return 'スプリント（～1400m）'
    elif distance <= 1800:
        return 'マイル（1401-1800m）'
    elif distance <= 2400:
        return '中距離（2000-2400m）'
    else:
        return '長距離（2500m～）'


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


def estimate_trio_payout(race, combo_nums):
    """実際の三連複払い戻しを取得"""
    payouts = race.get('payouts', {})
    trio_payouts = payouts.get('trio', [])
    
    for payout_info in trio_payouts:
        if isinstance(payout_info, dict):
            nums = set(payout_info.get('combo', []))
            if nums == combo_nums:
                return payout_info.get('payout', 0)
    
    # 払い戻し情報がない場合は推定
    return 0


def run_analysis():
    print("=" * 80)
    print("三連複戦略 距離別収支分析（カスタム距離定義）")
    print("=" * 80)
    
    # 2023をトレーニング、2024をテスト
    train_races = load_races("data/2023_full")
    test_races = load_races("data/2024_full")
    
    print(f"\nTraining: {len(train_races)} races (2023)")
    print(f"Testing: {len(test_races)} races (2024)")
    
    if len(train_races) == 0:
        print("Error: No training data found in data/2023_full")
        return
    if len(test_races) == 0:
        print("Error: No test data found in data/2024_full")
        return
    
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
    
    # 距離別統計
    distance_stats = defaultdict(lambda: {'races': 0, 'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0})
    
    for race in test_races:
        horses = race.get('horses', [])
        race_info = race.get('race_info', {})
        distance = race_info.get('distance', 0)
        
        if len(horses) < 8 or distance == 0:
            continue
        
        category = get_distance_category(distance)
        distance_stats[category]['races'] += 1
        
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
        
        # 着順3着以内の馬番
        top3_nums = set(h['num'] for h in calculated if h.get('finish', 99) <= 3)
        
        if len(axis_horses) >= 1 and len(hole_horses) >= 2:
            for axis in axis_horses[:1]:
                for hole_combo in combinations(hole_horses[:3], 2):
                    combo_nums = {axis['num'], hole_combo[0]['num'], hole_combo[1]['num']}
                    
                    distance_stats[category]['bets'] += 1
                    distance_stats[category]['investment'] += bet_unit
                    
                    if combo_nums == top3_nums:
                        distance_stats[category]['hits'] += 1
                        # 実際の払い戻しを取得
                        actual_payout = estimate_trio_payout(race, combo_nums)
                        if actual_payout == 0:
                            # 払い戻し情報がない場合は推定
                            odds_product = axis['odds'] * hole_combo[0]['odds'] * hole_combo[1]['odds']
                            actual_payout = int(max(200, odds_product * 0.04) * bet_unit / 100)
                        distance_stats[category]['payout'] += actual_payout
    
    # 結果表示
    print("\n" + "=" * 90)
    print("距離別収支（カスタム定義: 中距離2000-2400m、長距離2500m～）")
    print("=" * 90)
    print(f"{'距離カテゴリ':<25} {'レース数':>8} {'ベット':>8} {'的中':>6} {'投資':>12} {'回収':>12} {'収支':>12} {'ROI':>8}")
    print("-" * 90)
    
    total = {'races': 0, 'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0}
    
    for cat in ['スプリント（～1400m）', 'マイル（1401-1800m）', '中距離（2000-2400m）', '長距離（2500m～）']:
        data = distance_stats[cat]
        if data['races'] == 0:
            continue
        
        profit = data['payout'] - data['investment']
        roi = (data['payout'] / data['investment'] * 100) if data['investment'] > 0 else 0
        
        mark = "✓" if roi >= 100 else ""
        print(f"{cat:<25} {data['races']:>8} {data['bets']:>8} {data['hits']:>6} {data['investment']:>12,} {data['payout']:>12,} {profit:>+12,} {roi:>7.1f}% {mark}")
        
        for k in total:
            total[k] += data[k]
    
    print("-" * 90)
    profit = total['payout'] - total['investment']
    roi = (total['payout'] / total['investment'] * 100) if total['investment'] > 0 else 0
    print(f"{'合計':<25} {total['races']:>8} {total['bets']:>8} {total['hits']:>6} {total['investment']:>12,} {total['payout']:>12,} {profit:>+12,} {roi:>7.1f}%")
    print("=" * 90)


if __name__ == "__main__":
    run_analysis()
