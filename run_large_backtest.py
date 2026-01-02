"""
大規模バックテスト実行

複数のキャッシュディレクトリからデータを統合し、
V2 vs V3の検証を行う
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
    """複数のキャッシュからレースデータを読み込み"""
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


def build_stats_from_races(races: list) -> tuple:
    """レースデータから馬・騎手統計を構築"""
    horse_stats = defaultdict(lambda: {
        'name': '',
        'runs': 0,
        'wins': 0,
        'places': 0,
        'finishes': [],
        'courses': defaultdict(lambda: {'runs': 0, 'wins': 0}),
        'distances': defaultdict(lambda: {'runs': 0, 'wins': 0}),
    })
    
    jockey_stats = defaultdict(lambda: {
        'name': '',
        'runs': 0,
        'wins': 0,
        'places': 0,
    })
    
    for race in races:
        race_info = race.get('race_info', {})
        course = race_info.get('course', 'unknown')
        distance = race_info.get('distance', 0)
        
        for h in race.get('horses', []):
            horse_id = h.get('horse_id', '')
            jockey_id = h.get('jockey_id', '')
            finish = h.get('finish', 0)
            
            if horse_id:
                hs = horse_stats[horse_id]
                hs['name'] = h.get('name', '')
                hs['runs'] += 1
                if finish == 1:
                    hs['wins'] += 1
                if finish <= 3:
                    hs['places'] += 1
                hs['finishes'].append(finish)
                
                if course:
                    hs['courses'][course]['runs'] += 1
                    if finish == 1:
                        hs['courses'][course]['wins'] += 1
                
                if distance:
                    dist_key = f"{distance//100*100}"
                    hs['distances'][dist_key]['runs'] += 1
                    if finish == 1:
                        hs['distances'][dist_key]['wins'] += 1
            
            if jockey_id:
                js = jockey_stats[jockey_id]
                js['name'] = h.get('jockey', '')
                js['runs'] += 1
                if finish == 1:
                    js['wins'] += 1
                if finish <= 3:
                    js['places'] += 1
    
    # 勝率計算
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


def run_large_backtest():
    """大規模バックテスト実行"""
    print("=" * 70, flush=True)
    print("=== 大規模バックテスト ===", flush=True)
    print("=" * 70, flush=True)
    
    # 全キャッシュからデータ読み込み
    races = load_all_races(
        "data/cache_with_ids",
        "data/backtest_2023_2024"
    )
    
    print(f"\nTotal races: {len(races)}", flush=True)
    
    if len(races) < 10:
        print("Not enough races for testing")
        return
    
    # 統計データベース構築
    horse_stats, jockey_stats = build_stats_from_races(races)
    print(f"Horse stats: {len(horse_stats)} horses", flush=True)
    print(f"Jockey stats: {len(jockey_stats)} jockeys", flush=True)
    
    # エンジン初期化
    v2 = EVEngineV2(BiasConfig(
        fav_factor=0.95, mid_factor=1.00, long_factor=1.20, extreme_factor=2.00
    ))
    
    v3 = EVEngineV3(EVConfigV3(
        weight_base_ability=0.35,
        weight_course_fit=0.20,
        weight_recent_form=0.20,
        weight_jockey=0.15,
        weight_market=0.10,
        fav_factor=0.95,
        mid_factor=1.00,
        long_factor=1.05,
        extreme_factor=1.10
    ))
    
    bet_unit = 100
    ev_threshold = 1.0
    max_odds = 30.0
    
    v2_stats = {'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0}
    v3_stats = {'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0}
    
    # 各レースを処理
    for race in races:
        horses = race.get('horses', [])
        payouts = race.get('payouts', {'win': {}, 'place': {}})
        race_info = race.get('race_info', {})
        course = race_info.get('course', '')
        distance = race_info.get('distance', 0)
        dist_key = f"{distance//100*100}" if distance else ""
        
        # 馬に実際の統計データを付与
        for h in horses:
            horse_id = h.get('horse_id', '')
            jockey_id = h.get('jockey_id', '')
            
            if horse_id and horse_id in horse_stats:
                hs = horse_stats[horse_id]
                h['horse_profile'] = {
                    'total_runs': hs['runs'],
                    'total_wins': hs['wins'],
                    'total_places': hs['places'],
                    'win_rate': hs.get('win_rate', 0),
                    'place_rate': hs.get('place_rate', 0),
                    'recent_finishes': hs['finishes'][-5:],
                    'course_runs': hs['courses'].get(course, {}).get('runs', 0),
                    'course_wins': hs['courses'].get(course, {}).get('wins', 0),
                    'course_win_rate': (hs['courses'].get(course, {}).get('wins', 0) / 
                                       max(1, hs['courses'].get(course, {}).get('runs', 1))),
                    'distance_runs': hs['distances'].get(dist_key, {}).get('runs', 0),
                    'distance_wins': hs['distances'].get(dist_key, {}).get('wins', 0),
                    'distance_win_rate': (hs['distances'].get(dist_key, {}).get('wins', 0) / 
                                         max(1, hs['distances'].get(dist_key, {}).get('runs', 1))),
                }
            
            if jockey_id and jockey_id in jockey_stats:
                js = jockey_stats[jockey_id]
                h['jockey_profile'] = {
                    'year_runs': js['runs'],
                    'year_wins': js['wins'],
                    'year_win_rate': js.get('win_rate', 0),
                }
        
        # V2計算（プロファイルなし）
        v2_horses = [
            {k: v for k, v in h.items() 
             if k not in ['horse_profile', 'jockey_profile', 'horse_id', 'jockey_id']}
            for h in horses
        ]
        v2_result = v2.calculate_ev(v2_horses)
        
        # V3計算（プロファイル付き）
        v3_result = v3.calculate_ev([h.copy() for h in horses])
        
        # 賭け判定
        for v2h, v3h in zip(v2_result, v3_result):
            num = v2h['num']
            finish = v2h.get('finish', 0)
            odds = v2h.get('odds', 999)
            
            if odds > max_odds:
                continue
            
            # V2
            if v2h.get('win_ev', 0) >= ev_threshold:
                v2_stats['bets'] += 1
                v2_stats['investment'] += bet_unit
                if finish == 1:
                    v2_stats['hits'] += 1
                    payout = payouts.get('win', {}).get(str(num), 0)
                    v2_stats['payout'] += payout
            
            # V3
            confidence = v3h.get('_scores', {}).get('confidence', 0)
            if v3h.get('win_ev', 0) >= ev_threshold and confidence >= 0.7:
                v3_stats['bets'] += 1
                v3_stats['investment'] += bet_unit
                if finish == 1:
                    v3_stats['hits'] += 1
                    payout = payouts.get('win', {}).get(str(num), 0)
                    v3_stats['payout'] += payout
    
    # 結果表示
    print("\n" + "=" * 70, flush=True)
    print("=== 結果比較 ===", flush=True)
    print("=" * 70, flush=True)
    
    for name, stats in [("V2 (オッズのみ)", v2_stats), ("V3 (実統計使用)", v3_stats)]:
        roi = (stats['payout'] / stats['investment'] * 100) if stats['investment'] > 0 else 0
        hit_rate = (stats['hits'] / stats['bets'] * 100) if stats['bets'] > 0 else 0
        profit = stats['payout'] - stats['investment']
        
        print(f"\n[{name}]", flush=True)
        print(f"  レース数: {len(races)}", flush=True)
        print(f"  ベット: {stats['bets']}件", flush=True)
        print(f"  的中: {stats['hits']}件 ({hit_rate:.1f}%)", flush=True)
        print(f"  投資: {stats['investment']:,}円", flush=True)
        print(f"  払戻: {stats['payout']:,}円", flush=True)
        print(f"  損益: {profit:+,}円", flush=True)
        print(f"  ROI: {roi:.1f}%", flush=True)
    
    v2_roi = (v2_stats['payout'] / v2_stats['investment'] * 100) if v2_stats['investment'] > 0 else 0
    v3_roi = (v3_stats['payout'] / v3_stats['investment'] * 100) if v3_stats['investment'] > 0 else 0
    
    print(f"\n{'=' * 70}", flush=True)
    print(f"ROI差: V3 - V2 = {v3_roi - v2_roi:+.1f}%", flush=True)
    
    if v3_roi > v2_roi + 10:
        print("結果: V3が明確に優位", flush=True)
    elif v3_roi > v2_roi:
        print("結果: V3がやや優位", flush=True)
    elif v3_roi < v2_roi - 10:
        print("結果: V2が明確に優位", flush=True)
    else:
        print("結果: 同等", flush=True)


if __name__ == "__main__":
    run_large_backtest()
