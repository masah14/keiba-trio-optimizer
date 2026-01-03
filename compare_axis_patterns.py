"""
三連複ナガシ戦略 - 軸馬数の比較
パターン:
1. 1～3番人気 + 穴馬 + 全
2. 1～2番人気 + 穴馬 + 全
3. 1番人気 + 穴馬 + 全
"""

import json
import os
import sys
from collections import defaultdict
from itertools import combinations

sys.path.insert(0, 'app')

from ev_engine_v3 import EVEngineV3, EVConfigV3


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


def run_comparison():
    print("=" * 90)
    print("Trio Nagashi Strategy Comparison: Axis Horse Count")
    print("=" * 90)
    
    # 2024年データ（既に三連複払い戻しデータあり）
    all_races = load_races_with_payout("data/2024_full")
    print(f"\nRaces with payout data: {len(all_races)}")
    
    if len(all_races) < 50:
        print("Not enough data!")
        return
    
    # 30% training, 70% test
    n_train = int(len(all_races) * 0.3)
    train_races = all_races[:n_train]
    test_races = all_races[n_train:]
    
    print(f"Training: {len(train_races)}, Test: {len(test_races)}")
    
    horse_stats, jockey_stats = build_stats(train_races)
    v3 = EVEngineV3(EVConfigV3())
    
    bet_unit = 100
    
    # 3パターンの統計
    patterns = {
        '1-3 fav + hole + all': {'axis_max': 3, 'stats': {'races': 0, 'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0}},
        '1-2 fav + hole + all': {'axis_max': 2, 'stats': {'races': 0, 'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0}},
        '1 fav + hole + all':   {'axis_max': 1, 'stats': {'races': 0, 'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0}}
    }
    
    for race in test_races:
        horses = race.get('horses', [])
        if len(horses) < 8:
            continue
        
        # 実際の払い戻し
        real_trio = race.get('payouts', {}).get('trio', [])
        if not real_trio:
            continue
        winning_combo = set(real_trio[0]['combo'])
        winning_payout = real_trio[0]['payout']
        
        # ホース統計注入
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
        
        # 全馬番
        all_nums = set(h['num'] for h in calculated)
        
        # 穴馬
        hole_horses = [h for h in calculated if is_good_hole_horse(h)]
        hole_nums = set(h['num'] for h in hole_horses[:3])  # 上位3頭
        
        if len(hole_nums) < 1:
            continue
        
        # 各パターンをテスト
        for pattern_name, pattern_info in patterns.items():
            axis_max = pattern_info['axis_max']
            stats = pattern_info['stats']
            
            # 軸馬: 人気上位N頭
            axis_horses = [h for h in calculated if h.get('popularity', 99) <= axis_max]
            axis_nums = set(h['num'] for h in axis_horses)
            
            if len(axis_nums) == 0:
                continue
            
            stats['races'] += 1
            
            # ナガシ: 軸 + 穴 + 全
            # 組み合わせ: 軸から1頭 + 穴から1頭 + 残り全頭から1頭
            for axis in axis_horses:
                for hole in hole_horses[:3]:
                    if hole['num'] == axis['num']:
                        continue
                    
                    # 残りの馬
                    others = [h for h in calculated if h['num'] not in {axis['num'], hole['num']}]
                    
                    for other in others:
                        combo = {axis['num'], hole['num'], other['num']}
                        
                        stats['bets'] += 1
                        stats['investment'] += bet_unit
                        
                        if combo == winning_combo:
                            stats['hits'] += 1
                            stats['payout'] += winning_payout
    
    # 結果表示
    print("\n" + "=" * 90)
    print("RESULTS")
    print("=" * 90)
    print(f"{'Pattern':<25} {'Races':>8} {'Bets':>10} {'Hits':>6} {'Investment':>12} {'Payout':>12} {'P&L':>12} {'ROI':>8}")
    print("-" * 90)
    
    for pattern_name, pattern_info in patterns.items():
        stats = pattern_info['stats']
        profit = stats['payout'] - stats['investment']
        roi = (stats['payout'] / stats['investment'] * 100) if stats['investment'] > 0 else 0
        
        mark = "<<" if roi >= 100 else ""
        print(f"{pattern_name:<25} {stats['races']:>8} {stats['bets']:>10,} {stats['hits']:>6} {stats['investment']:>12,} {stats['payout']:>12,} {profit:>+12,} {roi:>7.1f}% {mark}")
    
    print("=" * 90)
    
    # 最良パターンを特定
    best = max(patterns.items(), key=lambda x: x[1]['stats']['payout'] - x[1]['stats']['investment'])
    print(f"\nBest: {best[0]}")


if __name__ == "__main__":
    run_comparison()
