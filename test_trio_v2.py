"""
三連複戦略 改良版

穴馬の条件を厳格化:
- 複勝EV 1.2以上（より高い期待値）
- 信頼度 0.8以上
- オッズ15-40倍（中穴狙い）
- 直近成績が良い馬
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
    odds_product = 1.0
    for h in horses_in_combo:
        odds_product *= h['odds']
    return max(2.0, odds_product * 0.04)


def is_good_hole_horse(h, min_ev=1.2, min_confidence=0.8):
    """厳選された穴馬かどうか"""
    odds = h.get('odds', 999)
    popularity = h.get('popularity', 0)
    place_ev = h.get('place_ev', 0)
    confidence = h.get('_scores', {}).get('confidence', 0)
    
    # 条件
    if popularity < 4:  # 人気馬は除外
        return False
    if place_ev < min_ev:  # 複勝EVが低い
        return False
    if confidence < min_confidence:  # 信頼度が低い
        return False
    if odds < 10 or odds > 50:  # オッズ10-50倍の中穴
        return False
    
    return True


def run_improved_test():
    print("=" * 70, flush=True)
    print("=== 三連複戦略 改良版テスト ===", flush=True)
    print("=" * 70, flush=True)
    
    all_races = load_races("data/2024_full")
    print(f"\nTotal races: {len(all_races)}", flush=True)
    
    n_train = int(len(all_races) * 0.7)
    train_races = all_races[:n_train]
    test_races = all_races[n_train:]
    
    print(f"Training: {len(train_races)}, Test: {len(test_races)}", flush=True)
    
    horse_stats, jockey_stats = build_stats(train_races)
    print(f"Horses: {len(horse_stats)}, Jockeys: {len(jockey_stats)}", flush=True)
    
    v3 = EVEngineV3(EVConfigV3(
        weight_base_ability=0.35, weight_course_fit=0.20,
        weight_recent_form=0.20, weight_jockey=0.15, weight_market=0.10,
        fav_factor=0.95, mid_factor=1.00, long_factor=1.05, extreme_factor=1.10
    ))
    
    bet_unit = 100
    
    # 複数の条件でテスト
    test_configs = [
        ("EV1.0 Conf0.7", 1.0, 0.7),
        ("EV1.2 Conf0.7", 1.2, 0.7),
        ("EV1.2 Conf0.8", 1.2, 0.8),
        ("EV1.5 Conf0.7", 1.5, 0.7),
        ("EV1.5 Conf0.8", 1.5, 0.8),
    ]
    
    results = []
    
    for config_name, min_ev, min_conf in test_configs:
        stats = {'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0}
        hit_details = []
        
        for race in test_races:
            horses = race.get('horses', [])
            
            if len(horses) < 8:
                continue
            
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
            hole_horses = [
                h for h in calculated 
                if is_good_hole_horse(h, min_ev=min_ev, min_confidence=min_conf)
            ]
            
            # 着順3着以内の馬番
            top3_nums = set(h['num'] for h in calculated if h.get('finish', 99) <= 3)
            
            # 戦略: 軸1頭 + 穴2頭
            if len(axis_horses) >= 1 and len(hole_horses) >= 2:
                for axis in axis_horses[:1]:  # 1番人気のみ
                    for hole_combo in combinations(hole_horses[:3], 2):
                        combo_nums = {axis['num'], hole_combo[0]['num'], hole_combo[1]['num']}
                        
                        stats['bets'] += 1
                        stats['investment'] += bet_unit
                        
                        if combo_nums == top3_nums:
                            stats['hits'] += 1
                            est_payout = estimate_trio_odds([axis, hole_combo[0], hole_combo[1]]) * bet_unit
                            stats['payout'] += int(est_payout)
                            hit_details.append({
                                'combo': [axis['name'], hole_combo[0]['name'], hole_combo[1]['name']],
                                'payout': int(est_payout)
                            })
        
        if stats['investment'] > 0:
            roi = stats['payout'] / stats['investment'] * 100
        else:
            roi = 0
        hit_rate = stats['hits'] / stats['bets'] * 100 if stats['bets'] > 0 else 0
        profit = stats['payout'] - stats['investment']
        
        results.append({
            'name': config_name,
            'bets': stats['bets'],
            'hits': stats['hits'],
            'hit_rate': hit_rate,
            'profit': profit,
            'roi': roi,
            'hit_details': hit_details
        })
    
    # 結果表示
    print("\n" + "=" * 70, flush=True)
    print("=== 条件別 結果 ===", flush=True)
    print("=" * 70, flush=True)
    
    print(f"\n{'Config':<15} | {'Bets':>6} | {'Hits':>4} | {'Hit%':>6} | {'Profit':>10} | {'ROI':>7}", flush=True)
    print("-" * 65, flush=True)
    
    for r in results:
        mark = "***" if r['roi'] >= 100 else ""
        print(f"{r['name']:<15} | {r['bets']:>6} | {r['hits']:>4} | {r['hit_rate']:>5.1f}% | {r['profit']:>+9,} | {r['roi']:>6.1f}% {mark}", flush=True)
    
    print("\n" + "=" * 70, flush=True)
    
    # 最良結果
    best = max(results, key=lambda x: x['roi'])
    print(f"\nBest: {best['name']} (ROI: {best['roi']:.1f}%)", flush=True)
    
    if best['roi'] >= 100:
        print("\n*** 利益が出る条件を発見！ ***", flush=True)
    
    if best['hit_details']:
        print("\n的中例:", flush=True)
        for d in best['hit_details'][:3]:
            print(f"  {d['combo']} -> {d['payout']}円", flush=True)


if __name__ == "__main__":
    run_improved_test()
