"""
多条件バックテスト

EV閾値と賭け方（単勝/複勝）を変えて最適条件を探索
"""

import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, 'app')
sys.stdout.reconfigure(line_buffering=True)

from ev_engine_v2 import EVEngineV2, BiasConfig
from ev_engine_v3 import EVEngineV3, EVConfigV3


def load_all_races(*cache_dirs) -> list:
    races = []
    seen_ids = set()
    
    for cache_dir in cache_dirs:
        if not os.path.exists(cache_dir):
            continue
        
        for filename in os.listdir(cache_dir):
            if not filename.startswith('race_') or not filename.endswith('.json'):
                continue
            
            race_id = filename.replace('race_', '').replace('.json', '')
            if race_id in seen_ids:
                continue
            seen_ids.add(race_id)
            
            filepath = os.path.join(cache_dir, filename)
            with open(filepath, 'r', encoding='utf-8') as f:
                race = json.load(f)
            
            if race.get('horses') and len(race['horses']) >= 5:
                races.append(race)
    
    return races


def build_stats_from_races(races):
    horse_stats = defaultdict(lambda: {
        'name': '', 'runs': 0, 'wins': 0, 'places': 0, 'finishes': [],
        'courses': defaultdict(lambda: {'runs': 0, 'wins': 0}),
        'distances': defaultdict(lambda: {'runs': 0, 'wins': 0}),
    })
    jockey_stats = defaultdict(lambda: {
        'name': '', 'runs': 0, 'wins': 0, 'places': 0,
    })
    
    for race in races:
        race_info = race.get('race_info', {})
        course = race_info.get('course', '')
        distance = race_info.get('distance', 0)
        
        for h in race.get('horses', []):
            horse_id = h.get('horse_id', '')
            jockey_id = h.get('jockey_id', '')
            finish = h.get('finish', 0)
            
            if horse_id:
                hs = horse_stats[horse_id]
                hs['name'] = h.get('name', '')
                hs['runs'] += 1
                if finish == 1: hs['wins'] += 1
                if finish <= 3: hs['places'] += 1
                hs['finishes'].append(finish)
                if course:
                    hs['courses'][course]['runs'] += 1
                    if finish == 1: hs['courses'][course]['wins'] += 1
                if distance:
                    dist_key = f"{distance//100*100}"
                    hs['distances'][dist_key]['runs'] += 1
                    if finish == 1: hs['distances'][dist_key]['wins'] += 1
            
            if jockey_id:
                js = jockey_stats[jockey_id]
                js['name'] = h.get('jockey', '')
                js['runs'] += 1
                if finish == 1: js['wins'] += 1
                if finish <= 3: js['places'] += 1
    
    for stats in horse_stats.values():
        if stats['runs'] > 0:
            stats['win_rate'] = stats['wins'] / stats['runs']
            stats['place_rate'] = stats['places'] / stats['runs']
            if stats['finishes']:
                stats['avg_finish'] = sum(stats['finishes']) / len(stats['finishes'])
    
    for stats in jockey_stats.values():
        if stats['runs'] > 0:
            stats['win_rate'] = stats['wins'] / stats['runs']
            stats['place_rate'] = stats['places'] / stats['runs']
    
    return dict(horse_stats), dict(jockey_stats)


def run_multi_condition_test():
    print("=" * 70, flush=True)
    print("=== 多条件バックテスト ===", flush=True)
    print("=" * 70, flush=True)
    
    races = load_all_races("data/cache_with_ids", "data/backtest_2023_2024")
    print(f"\nTotal races: {len(races)}", flush=True)
    
    horse_stats, jockey_stats = build_stats_from_races(races)
    print(f"Horses: {len(horse_stats)}, Jockeys: {len(jockey_stats)}", flush=True)
    
    v3 = EVEngineV3(EVConfigV3(
        weight_base_ability=0.35, weight_course_fit=0.20,
        weight_recent_form=0.20, weight_jockey=0.15, weight_market=0.10,
        fav_factor=0.95, mid_factor=1.00, long_factor=1.05, extreme_factor=1.10
    ))
    
    bet_unit = 100
    
    # テスト条件
    conditions = [
        ("単勝 EV>=1.0", 'win', 1.0, 30),
        ("単勝 EV>=1.2", 'win', 1.2, 30),
        ("単勝 EV>=1.5", 'win', 1.5, 30),
        ("複勝 EV>=1.0", 'place', 1.0, 30),
        ("複勝 EV>=1.2", 'place', 1.2, 30),
        ("複勝 EV>=1.5", 'place', 1.5, 30),
    ]
    
    results = []
    
    for cond_name, bet_type, ev_threshold, max_odds in conditions:
        stats = {'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0}
        
        for race in races:
            horses = race.get('horses', [])
            payouts = race.get('payouts', {'win': {}, 'place': {}})
            race_info = race.get('race_info', {})
            course = race_info.get('course', '')
            distance = race_info.get('distance', 0)
            dist_key = f"{distance//100*100}" if distance else ""
            
            # プロファイル付与
            for h in horses:
                horse_id = h.get('horse_id', '')
                jockey_id = h.get('jockey_id', '')
                
                if horse_id and horse_id in horse_stats:
                    hs = horse_stats[horse_id]
                    h['horse_profile'] = {
                        'total_runs': hs['runs'], 'win_rate': hs.get('win_rate', 0),
                        'place_rate': hs.get('place_rate', 0),
                        'recent_finishes': hs['finishes'][-5:],
                        'course_runs': hs['courses'].get(course, {}).get('runs', 0),
                        'course_win_rate': (hs['courses'].get(course, {}).get('wins', 0) / 
                                           max(1, hs['courses'].get(course, {}).get('runs', 1))),
                    }
                
                if jockey_id and jockey_id in jockey_stats:
                    js = jockey_stats[jockey_id]
                    h['jockey_profile'] = {
                        'year_runs': js['runs'],
                        'year_win_rate': js.get('win_rate', 0),
                    }
            
            calculated = v3.calculate_ev([h.copy() for h in horses])
            
            for h in calculated:
                num = h['num']
                finish = h.get('finish', 0)
                odds = h.get('odds', 999)
                confidence = h.get('_scores', {}).get('confidence', 0)
                
                if odds > max_odds:
                    continue
                
                if bet_type == 'win':
                    ev = h.get('win_ev', 0)
                    hit_condition = finish == 1
                    payout_key = 'win'
                else:  # place
                    ev = h.get('place_ev', 0)
                    hit_condition = finish <= 3
                    payout_key = 'place'
                
                if ev >= ev_threshold and confidence >= 0.7:
                    stats['bets'] += 1
                    stats['investment'] += bet_unit
                    if hit_condition:
                        stats['hits'] += 1
                        payout = payouts.get(payout_key, {}).get(str(num), 0)
                        stats['payout'] += payout
        
        roi = (stats['payout'] / stats['investment'] * 100) if stats['investment'] > 0 else 0
        hit_rate = (stats['hits'] / stats['bets'] * 100) if stats['bets'] > 0 else 0
        profit = stats['payout'] - stats['investment']
        
        results.append({
            'name': cond_name,
            'bets': stats['bets'],
            'hits': stats['hits'],
            'hit_rate': hit_rate,
            'profit': profit,
            'roi': roi
        })
    
    # 結果表示
    print("\n" + "=" * 70, flush=True)
    print("=== 結果一覧 ===", flush=True)
    print("=" * 70, flush=True)
    
    print(f"\n{'条件':<20} | {'ベット':>8} | {'的中':>8} | {'的中率':>8} | {'損益':>12} | {'ROI':>10}", flush=True)
    print("-" * 80, flush=True)
    
    for r in results:
        mark = "***" if r['roi'] >= 100 else ""
        print(f"{r['name']:<20} | {r['bets']:>8} | {r['hits']:>8} | {r['hit_rate']:>7.1f}% | {r['profit']:>+11,} | {r['roi']:>9.1f}% {mark}", flush=True)
    
    # 最良条件
    best = max(results, key=lambda x: x['roi'])
    print(f"\n{'=' * 70}", flush=True)
    print(f"最良条件: {best['name']} (ROI: {best['roi']:.1f}%, 損益: {best['profit']:+,}円)", flush=True)


if __name__ == "__main__":
    run_multi_condition_test()
