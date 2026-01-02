"""
既存キャッシュデータの拡張

既存のレースキャッシュに馬・騎手の詳細情報を追加
"""

import json
import os
import sys
import time
import re

sys.path.insert(0, 'app')
sys.stdout.reconfigure(line_buffering=True)

from scraper_enhanced import EnhancedScraper, save_enhanced_cache, load_enhanced_cache

def enhance_cached_races(cache_dir: str = "data/cache", 
                         output_dir: str = "data/enhanced_cache",
                         max_races: int = 5):
    """
    キャッシュされたレースデータを拡張
    """
    print("=== Enhancing Cached Race Data ===", flush=True)
    
    os.makedirs(output_dir, exist_ok=True)
    
    # キャッシュからレースIDを取得
    race_files = [f for f in os.listdir(cache_dir) 
                  if f.startswith('race_') and f.endswith('.json')]
    
    print(f"Found {len(race_files)} cached races", flush=True)
    
    scraper = EnhancedScraper(headless=True, wait_time=2.5)
    
    enhanced_count = 0
    
    try:
        for filename in race_files[:max_races]:
            race_id = filename.replace('race_', '').replace('.json', '')
            
            # 既に拡張済みならスキップ
            if load_enhanced_cache(race_id, output_dir):
                print(f"  [SKIP] {race_id} (already enhanced)", flush=True)
                continue
            
            print(f"  [ENHANCING] {race_id}...", flush=True)
            
            # 拡張データを取得
            enhanced_data = scraper.get_race_enhanced_data(race_id)
            
            if enhanced_data and enhanced_data.get('horses'):
                save_enhanced_cache(race_id, enhanced_data, output_dir)
                enhanced_count += 1
                
                # サンプル表示
                horses = enhanced_data['horses']
                print(f"    Enhanced {len(horses)} horses", flush=True)
                for h in horses[:2]:
                    profile = h.get('horse_profile', {})
                    if profile:
                        print(f"      {h['name']}: WinRate={profile.get('win_rate', 0):.1%}", flush=True)
            else:
                print(f"    Failed to enhance", flush=True)
            
            time.sleep(1)
            
    finally:
        scraper.close()
    
    print(f"\nEnhanced {enhanced_count} races", flush=True)
    return enhanced_count


def test_v3_with_enhanced_data():
    """
    拡張データでV3エンジンをテスト
    """
    print("\n=== Testing V3 with Enhanced Data ===", flush=True)
    
    from ev_engine_v3 import EVEngineV3, EVConfigV3
    from ev_engine_v2 import EVEngineV2
    
    # 拡張キャッシュからデータを読み込み
    enhanced_dir = "data/enhanced_cache"
    
    if not os.path.exists(enhanced_dir):
        print("No enhanced data available. Run enhance_cached_races first.")
        return
    
    files = [f for f in os.listdir(enhanced_dir) if f.endswith('.json')]
    
    if not files:
        print("No enhanced race files found.")
        return
    
    v2 = EVEngineV2()
    v3 = EVEngineV3()
    
    total_v2_profit = 0
    total_v3_profit = 0
    total_investment = 0
    bet_unit = 100
    
    for filename in files:
        filepath = os.path.join(enhanced_dir, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            race_data = json.load(f)
        
        horses = race_data.get('horses', [])
        payouts = race_data.get('payouts', {'win': {}, 'place': {}})
        
        if len(horses) < 3:
            continue
        
        print(f"\nRace: {race_data.get('race_id', 'Unknown')}", flush=True)
        
        # V2計算
        v2_horses = v2.calculate_ev([h.copy() for h in horses])
        
        # V3計算
        v3_horses = v3.calculate_ev([h.copy() for h in horses])
        
        # 結果比較(単勝 EV>=1.2)
        for v2h, v3h in zip(v2_horses, v3_horses):
            num = v2h['num']
            finish = v2h.get('finish', 0)
            
            # V2推奨
            if v2h.get('win_ev', 0) >= 1.2 and v2h.get('odds', 999) <= 50:
                total_investment += bet_unit
                if finish == 1:
                    payout = payouts.get('win', {}).get(num, 0)
                    total_v2_profit += payout - bet_unit
                else:
                    total_v2_profit -= bet_unit
            
            # V3推奨
            if v3h.get('win_ev', 0) >= 1.2 and v3h.get('odds', 999) <= 50:
                total_investment += bet_unit
                if finish == 1:
                    payout = payouts.get('win', {}).get(num, 0)
                    total_v3_profit += payout - bet_unit
                else:
                    total_v3_profit -= bet_unit
        
        # 各馬のEV比較を表示
        print("  馬名           | V2 EV | V3 EV | 着順", flush=True)
        print("  " + "-" * 45, flush=True)
        for v2h, v3h in zip(v2_horses[:5], v3_horses[:5]):  # 上位5頭
            print(f"  {v2h['name'][:10]:<12} | {v2h['win_ev']:>5.2f} | {v3h['win_ev']:>5.2f} | {v2h.get('finish', '?')}", flush=True)
    
    print("\n" + "=" * 50, flush=True)
    print("=== 総合結果 ===", flush=True)
    print(f"V2 損益: {total_v2_profit:+,}円", flush=True)
    print(f"V3 損益: {total_v3_profit:+,}円", flush=True)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--enhance', action='store_true', help='Enhance cached data')
    parser.add_argument('--test', action='store_true', help='Test V3 engine')
    parser.add_argument('--max-races', type=int, default=3, help='Max races to enhance')
    
    args = parser.parse_args()
    
    if args.enhance:
        enhance_cached_races(max_races=args.max_races)
    
    if args.test:
        test_v3_with_enhanced_data()
    
    if not args.enhance and not args.test:
        # デフォルト: 両方実行
        enhance_cached_races(max_races=3)
        test_v3_with_enhanced_data()
