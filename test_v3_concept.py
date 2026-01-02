"""
V3コンセプト検証 - 推定プロファイルを使用

スクレイピングに時間がかかるため、オッズと人気から
過去成績を「推定」してV3コンセプトを検証する。

仮説:
- 人気上位馬は過去成績が良いはず
- オッズが低い馬は勝率が高いはず
- でも、それ以上の「実力差」があるかもしれない

テスト方法:
- 人気順から勝率を推定（人気1位: 勝率20%, 5位: 5% など）
- この推定値と実際の着順を比較
- V2（オッズのみ）とV3（推定プロファイル付き）を比較
"""

import json
import os
import sys
import numpy as np

sys.path.insert(0, 'app')
sys.stdout.reconfigure(line_buffering=True)

from ev_engine_v2 import EVEngineV2, BiasConfig
from ev_engine_v3 import EVEngineV3, EVConfigV3


def estimate_profile_from_popularity(popularity: int, field_size: int) -> dict:
    """
    人気順から過去成績を推定
    
    JRA統計に基づく近似値:
    - 1番人気の勝率: 約32%
    - 2番人気: 約19%
    - 3番人気: 約13%
    - 10番人気以降: 約1-2%
    """
    # 人気順別の期待勝率（JRA統計の近似）
    win_rates = {
        1: 0.32, 2: 0.19, 3: 0.13, 4: 0.09, 5: 0.07,
        6: 0.05, 7: 0.04, 8: 0.03, 9: 0.02, 10: 0.02
    }
    
    base_win_rate = win_rates.get(popularity, 0.01)
    
    # 連対率は勝率の約2.5倍
    place_rate = min(0.8, base_win_rate * 2.5)
    
    # 直近成績を人気から推定
    if popularity <= 3:
        recent_finishes = [2, 1, 3, 2, 1]  # 好調
    elif popularity <= 6:
        recent_finishes = [4, 3, 5, 2, 6]  # 中位
    else:
        recent_finishes = [8, 10, 7, 9, 12]  # 下位
    
    return {
        'total_runs': 10,
        'total_wins': int(base_win_rate * 10),
        'total_places': int(place_rate * 10),
        'win_rate': base_win_rate,
        'place_rate': place_rate,
        'recent_finishes': recent_finishes,
        'recent_avg_finish': sum(recent_finishes) / len(recent_finishes),
        'course_runs': 3,
        'course_wins': 1 if popularity <= 5 else 0,
        'course_win_rate': 0.33 if popularity <= 5 else 0.0,
        'distance_runs': 3,
        'distance_wins': 1 if popularity <= 4 else 0,
        'distance_win_rate': 0.33 if popularity <= 4 else 0.0,
    }


def estimate_jockey_profile(popularity: int) -> dict:
    """騎手プロファイルを推定"""
    # 人気馬には良い騎手が乗る傾向
    if popularity <= 3:
        win_rate = 0.15  # トップジョッキー
    elif popularity <= 6:
        win_rate = 0.10
    else:
        win_rate = 0.05
    
    return {
        'year_runs': 100,
        'year_wins': int(win_rate * 100),
        'year_win_rate': win_rate,
        'course_runs': 20,
        'course_wins': int(win_rate * 20),
        'course_win_rate': win_rate,
    }


def run_concept_test():
    """V3コンセプトテスト"""
    print("=" * 70, flush=True)
    print("=== V3コンセプト検証（推定プロファイル使用） ===", flush=True)
    print("=" * 70, flush=True)
    
    cache_dir = "data/cache"
    
    files = [f for f in os.listdir(cache_dir) 
             if f.startswith('race_') and f.endswith('.json')]
    
    print(f"\nLoaded {len(files)} races from cache", flush=True)
    
    # V2: オリジナル（問題あったもの）
    v2 = EVEngineV2(BiasConfig(
        fav_factor=0.95,
        mid_factor=1.00, 
        long_factor=1.20,
        extreme_factor=2.00
    ))
    
    # V3: 推定プロファイル使用
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
    max_odds = 30.0  # オッズ30倍以下のみ
    
    v2_stats = {'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0}
    v3_stats = {'bets': 0, 'hits': 0, 'investment': 0, 'payout': 0}
    
    detailed_bets = []
    
    for filename in files:
        filepath = os.path.join(cache_dir, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            race = json.load(f)
        
        horses = race.get('horses', [])
        payouts = race.get('payouts', {'win': {}, 'place': {}})
        
        if len(horses) < 5:
            continue
        
        field_size = len(horses)
        
        # 馬に推定プロファイルを追加
        for h in horses:
            pop = h.get('popularity', field_size // 2)
            h['horse_profile'] = estimate_profile_from_popularity(pop, field_size)
            h['jockey_profile'] = estimate_jockey_profile(pop)
        
        # V2計算
        v2_result = v2.calculate_ev([{k: v for k, v in h.items() 
                                       if k not in ['horse_profile', 'jockey_profile']} 
                                      for h in horses])
        
        # V3計算
        v3_result = v3.calculate_ev([h.copy() for h in horses])
        
        # 賭け判定
        for v2h, v3h in zip(v2_result, v3_result):
            num = v2h['num']
            finish = v2h.get('finish', 0)
            odds = v2h.get('odds', 999)
            
            if odds > max_odds:
                continue
            
            # V2: EV >= 1.0 で賭け
            if v2h.get('win_ev', 0) >= ev_threshold:
                v2_stats['bets'] += 1
                v2_stats['investment'] += bet_unit
                if finish == 1:
                    v2_stats['hits'] += 1
                    payout = payouts.get('win', {}).get(str(num), 0)
                    v2_stats['payout'] += payout
            
            # V3: EV >= 1.0 + 信頼度 >= 0.7 で賭け
            confidence = v3h.get('_scores', {}).get('confidence', 0)
            if v3h.get('win_ev', 0) >= ev_threshold and confidence >= 0.7:
                v3_stats['bets'] += 1
                v3_stats['investment'] += bet_unit
                if finish == 1:
                    v3_stats['hits'] += 1
                    payout = payouts.get('win', {}).get(str(num), 0)
                    v3_stats['payout'] += payout
                    detailed_bets.append({
                        'race': filename,
                        'horse': v3h.get('name', '?'),
                        'ev': v3h.get('win_ev', 0),
                        'odds': odds,
                        'payout': payout
                    })
    
    # 結果表示
    print("\n" + "=" * 70, flush=True)
    print("=== 結果比較 (EV>=1.0, オッズ<=30倍) ===", flush=True)
    print("=" * 70, flush=True)
    
    for name, stats in [("V2 (オッズのみ)", v2_stats), ("V3 (推定プロファイル)", v3_stats)]:
        roi = (stats['payout'] / stats['investment'] * 100) if stats['investment'] > 0 else 0
        hit_rate = (stats['hits'] / stats['bets'] * 100) if stats['bets'] > 0 else 0
        profit = stats['payout'] - stats['investment']
        
        print(f"\n【{name}】", flush=True)
        print(f"  ベット: {stats['bets']}件", flush=True)
        print(f"  的中: {stats['hits']}件 ({hit_rate:.1f}%)", flush=True)
        print(f"  投資: {stats['investment']:,}円", flush=True)
        print(f"  払戻: {stats['payout']:,}円", flush=True)
        print(f"  損益: {profit:+,}円", flush=True)
        print(f"  ROI: {roi:.1f}%", flush=True)
    
    if detailed_bets:
        print("\n【V3で的中した馬】", flush=True)
        for b in detailed_bets[:5]:
            print(f"  {b['horse']}: EV={b['ev']:.2f}, オッズ={b['odds']}, 払戻={b['payout']}円", flush=True)
    
    # 差分分析
    print("\n" + "=" * 70, flush=True)
    print("=== 分析 ===", flush=True)
    print("=" * 70, flush=True)
    
    v2_roi = (v2_stats['payout'] / v2_stats['investment'] * 100) if v2_stats['investment'] > 0 else 0
    v3_roi = (v3_stats['payout'] / v3_stats['investment'] * 100) if v3_stats['investment'] > 0 else 0
    
    print(f"\nROI差: V3 - V2 = {v3_roi - v2_roi:+.1f}%", flush=True)
    print(f"ベット数差: {v3_stats['bets'] - v2_stats['bets']:+d}件", flush=True)
    
    if v3_roi > v2_roi:
        print("\n✓ V3が改善。追加情報の活用は有効。", flush=True)
    elif v3_roi == v2_roi:
        print("\n→ V3とV2は同等。追加情報の効果は限定的。", flush=True)
    else:
        print("\n✗ V2の方が良い。追加情報の使い方に問題あり。", flush=True)


if __name__ == "__main__":
    run_concept_test()
