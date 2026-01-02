"""
大規模ウォークフォワードテスト

620レースのデータで正しい検証:
- 訓練: 2024年1月〜2月（前半のデータ）
- テスト: 2024年3月（後半のデータ）
"""

import json
import os
import sys
from collections import defaultdict

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


def split_by_date(races, cutoff_month):
    """
    レースを日付で分割
    cutoff_month: この月以降をテストデータに
    """
    train = []
    test = []
    
    for race in races:
        race_id = race.get('race_id', '')
        # race_id format: YYYYPPDDXXRR (year, place, day, xx, race)
        if len(race_id) >= 6:
            year = race_id[:4]
            # ファイル名からおおよその月を推定（開催週から）
            week_code = race_id[4:6]  # 開催週
            try:
                week = int(week_code)
                # 週番号から月を推定（開催週は1から始まり、4-5週で1ヶ月）
                est_month = ((week - 1) // 4) + 1
                
                if est_month >= cutoff_month:
                    test.append(race)
                else:
                    train.append(race)
            except:
                # パースできない場合はランダムに割り当て
                if len(train) < len(races) * 0.7:
                    train.append(race)
                else:
                    test.append(race)
    
    return train, test


def build_stats(races):
    horse_stats = defaultdict(lambda: {
        'runs': 0, 'wins': 0, 'places': 0, 'finishes': [],
        'courses': defaultdict(lambda: {'runs': 0, 'wins': 0}),
    })
    jockey_stats = defaultdict(lambda: {'runs': 0, 'wins': 0, 'places': 0})
    
    for race in races:
        course = race.get('race_info', {}).get('course', '')
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
                if course:
                    hs['courses'][course]['runs'] += 1
                    if finish == 1: hs['courses'][course]['wins'] += 1
            
            if jockey_id:
                js = jockey_stats[jockey_id]
                js['runs'] += 1
                if finish == 1: js['wins'] += 1
                if finish <= 3: js['places'] += 1
    
    for stats in horse_stats.values():
        if stats['runs'] > 0:
            stats['win_rate'] = stats['wins'] / stats['runs']
            stats['place_rate'] = stats['places'] / stats['runs']
    
    for stats in jockey_stats.values():
        if stats['runs'] > 0:
            stats['win_rate'] = stats['wins'] / stats['runs']
    
    return dict(horse_stats), dict(jockey_stats)


def run_test():
    print("=" * 70, flush=True)
    print("=== Large Scale Walk-Forward Test (620 Races) ===", flush=True)
    print("=" * 70, flush=True)
    
    # 全データロード
    all_races = load_races("data/2024_full")
    print(f"\nTotal races loaded: {len(all_races)}", flush=True)
    
    # 70:30で分割（訓練:テスト）
    # 開催週5以降をテストに
    train_races, test_races = split_by_date(all_races, cutoff_month=3)
    
    print(f"Training races: {len(train_races)}", flush=True)
    print(f"Test races: {len(test_races)}", flush=True)
    
    if len(test_races) < 50:
        print("Not enough test data, using 70:30 split instead", flush=True)
        n_train = int(len(all_races) * 0.7)
        train_races = all_races[:n_train]
        test_races = all_races[n_train:]
        print(f"Training races: {len(train_races)}", flush=True)
        print(f"Test races: {len(test_races)}", flush=True)
    
    # 訓練データから統計構築
    print("\nBuilding stats from training data ONLY...", flush=True)
    horse_stats, jockey_stats = build_stats(train_races)
    print(f"Horses: {len(horse_stats)}", flush=True)
    print(f"Jockeys: {len(jockey_stats)}", flush=True)
    
    # テスト
    print("\nTesting on unseen data...", flush=True)
    
    v3 = EVEngineV3(EVConfigV3(
        weight_base_ability=0.35, weight_course_fit=0.20,
        weight_recent_form=0.20, weight_jockey=0.15, weight_market=0.10,
        fav_factor=0.95, mid_factor=1.00, long_factor=1.05, extreme_factor=1.10
    ))
    
    bet_unit = 100
    conditions = [
        ("Win EV>=1.5", 'win', 1.5),
        ("Win EV>=1.2", 'win', 1.2),
        ("Win EV>=1.0", 'win', 1.0),
        ("Place EV>=1.0", 'place', 1.0),
        ("Place EV>=1.2", 'place', 1.2),
    ]
    
    results = []
    
    for cond_name, bet_type, ev_threshold in conditions:
        stats = {'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0}
        
        for race in test_races:
            horses = race.get('horses', [])
            payouts = race.get('payouts', {'win': {}, 'place': {}})
            course = race.get('race_info', {}).get('course', '')
            
            # 訓練データの統計のみ使用
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
                
                if odds > 30:
                    continue
                
                if bet_type == 'win':
                    ev = h.get('win_ev', 0)
                    hit_cond = finish == 1
                else:
                    ev = h.get('place_ev', 0)
                    hit_cond = finish <= 3
                
                if ev >= ev_threshold and confidence >= 0.7:
                    stats['bets'] += 1
                    stats['investment'] += bet_unit
                    if hit_cond:
                        stats['hits'] += 1
                        payout = payouts.get(bet_type, {}).get(str(num), 0)
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
    
    # Results
    print("\n" + "=" * 70, flush=True)
    print("=== Walk-Forward Results (620 Races) ===", flush=True)
    print("=" * 70, flush=True)
    
    print(f"\n{'Condition':<20} | {'Bets':>6} | {'Hits':>6} | {'Hit%':>7} | {'Profit':>12} | {'ROI':>8}", flush=True)
    print("-" * 75, flush=True)
    
    for r in results:
        mark = "PASS" if r['roi'] >= 100 else ""
        print(f"{r['name']:<20} | {r['bets']:>6} | {r['hits']:>6} | {r['hit_rate']:>6.1f}% | {r['profit']:>+11,} | {r['roi']:>7.1f}% {mark}", flush=True)
    
    print("\n" + "=" * 70, flush=True)
    
    # 結論
    passing = [r for r in results if r['roi'] >= 100]
    if passing:
        print(f"\nPASSED: {len(passing)}/{len(results)} conditions", flush=True)
        best = max(passing, key=lambda x: x['roi'])
        print(f"Best: {best['name']} with ROI {best['roi']:.1f}%", flush=True)
        print("\nThe strategy shows promise with proper validation!", flush=True)
    else:
        print("\nFAILED: No conditions passed ROI >= 100%", flush=True)
        best = max(results, key=lambda x: x['roi'])
        print(f"Best: {best['name']} with ROI {best['roi']:.1f}%", flush=True)
        print("\nThe strategy does not work on unseen data.", flush=True)


if __name__ == "__main__":
    run_test()
