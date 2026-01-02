"""
実データバックテスト（軽量版）

目的:
1. Seleniumスクレイパーの動作確認
2. 最適化パラメータの実データでの検証
3. 合成データとの差異を確認

実行時間を短くするため、特定の月・日に限定
"""

import sys
import os
import json
from datetime import datetime

# 出力を即座にflush
sys.stdout.reconfigure(line_buffering=True)
print("Script started...", flush=True)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, 'app')

print("Importing modules...", flush=True)
from scraper_selenium import NetkeibaSeleniumScraper, DataCache, SELENIUM_AVAILABLE
from ev_engine_v2 import EVEngineV2, BiasConfig
print("Modules imported.", flush=True)


def run_light_backtest(target_dates: list, ev_threshold: float = 1.0):
    """
    軽量版バックテスト
    
    Args:
        target_dates: 対象日のリスト（YYYYMMDD形式）
        ev_threshold: EV閾値
    """
    print("=" * 70)
    print("=== 実データバックテスト（軽量版） ===")
    print("=" * 70)
    
    if not SELENIUM_AVAILABLE:
        print("ERROR: Selenium is not available")
        return
    
    # 最適化済みパラメータを使用
    config = BiasConfig(
        fav_factor=0.95,
        mid_factor=1.00,
        long_factor=1.20,
        extreme_factor=2.00
    )
    engine = EVEngineV2(config)
    print(f"\nEngine config: fav={config.fav_factor}, mid={config.mid_factor}, "
          f"long={config.long_factor}, extreme={config.extreme_factor}")
    print(f"EV threshold: {ev_threshold}")
    
    # キャッシュとスクレイパー
    cache = DataCache("data/cache")
    scraper = NetkeibaSeleniumScraper(headless=True, wait_time=2.0)
    
    bet_unit = 100
    stats = {
        'win_bets': 0, 'win_hits': 0, 'win_investment': 0, 'win_payout': 0,
        'place_bets': 0, 'place_hits': 0, 'place_investment': 0, 'place_payout': 0
    }
    bet_records = []
    total_races = 0
    
    try:
        for date_str in target_dates:
            print(f"\n--- {date_str} ---")
            
            # レースID取得
            race_ids = scraper.get_race_ids_for_date(date_str)
            print(f"Found {len(race_ids)} races")
            
            for race_id in race_ids:
                # キャッシュ確認
                cached = cache.get_cached_race(race_id)
                if cached:
                    race_data = cached
                    print(f"  [CACHE] {race_id}")
                else:
                    result = scraper.get_race_result(race_id)
                    if not result:
                        continue
                    race_data = {
                        'race_id': result.race_id,
                        'title': result.title,
                        'horses': result.horses,
                        'payouts': result.payouts
                    }
                    cache.cache_race(race_id, race_data)
                    print(f"  [FETCH] {race_id}: {result.title}")
                
                horses = race_data.get('horses', [])
                if not horses or len(horses) < 3:
                    continue
                
                total_races += 1
                
                # EV計算
                calculated = engine.calculate_ev([h.copy() for h in horses])
                payouts = race_data.get('payouts', {'win': {}, 'place': {}})
                
                for h in calculated:
                    num = h['num']
                    finish = h.get('finish', 0)
                    
                    # 単勝
                    if h.get('win_ev', 0) >= ev_threshold:
                        stats['win_bets'] += 1
                        stats['win_investment'] += bet_unit
                        
                        payout = 0
                        if finish == 1:
                            stats['win_hits'] += 1
                            payout = payouts.get('win', {}).get(num, 0)
                            stats['win_payout'] += payout
                        
                        bet_records.append({
                            'race_id': race_id,
                            'horse': h.get('name', ''),
                            'type': 'win',
                            'odds': h.get('odds', 0),
                            'ev': h.get('win_ev', 0),
                            'finish': finish,
                            'hit': finish == 1,
                            'payout': payout
                        })
                    
                    # 複勝
                    if h.get('place_ev', 0) >= ev_threshold:
                        stats['place_bets'] += 1
                        stats['place_investment'] += bet_unit
                        
                        payout = 0
                        if finish <= 3:
                            stats['place_hits'] += 1
                            payout = payouts.get('place', {}).get(num, 0)
                            stats['place_payout'] += payout
                        
                        bet_records.append({
                            'race_id': race_id,
                            'horse': h.get('name', ''),
                            'type': 'place',
                            'odds': h.get('odds', 0),
                            'ev': h.get('place_ev', 0),
                            'finish': finish,
                            'hit': finish <= 3,
                            'payout': payout
                        })
                        
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
    finally:
        scraper.close()
    
    # 結果表示
    print("\n" + "=" * 70)
    print("=== バックテスト結果 ===")
    print("=" * 70)
    print(f"対象日: {target_dates}")
    print(f"処理レース数: {total_races}")
    print()
    
    for bet_type, name in [('win', '単勝'), ('place', '複勝')]:
        bets = stats[f'{bet_type}_bets']
        hits = stats[f'{bet_type}_hits']
        invest = stats[f'{bet_type}_investment']
        payout = stats[f'{bet_type}_payout']
        
        roi = (payout / invest * 100) if invest > 0 else 0
        hit_rate = (hits / bets * 100) if bets > 0 else 0
        profit = payout - invest
        
        print(f"【{name}】(EV >= {ev_threshold})")
        print(f"  ベット数: {bets}件")
        print(f"  的中数: {hits}件 ({hit_rate:.1f}%)")
        print(f"  投資額: {invest:,}円")
        print(f"  払戻額: {payout:,}円")
        print(f"  損益: {profit:+,}円")
        print(f"  ROI: {roi:.1f}%")
        print()
    
    # 的中した賭けを表示
    hits_list = [r for r in bet_records if r['hit']]
    if hits_list:
        print("\n【的中リスト】")
        for r in hits_list[:10]:  # 最大10件
            print(f"  {r['type']}: {r['horse']} (EV={r['ev']:.2f}, 払戻={r['payout']}円)")
    
    # 高EVで外れたものを分析
    high_ev_misses = [r for r in bet_records if not r['hit'] and r['ev'] >= 2.0]
    if high_ev_misses:
        print(f"\n【高EV外れ (EV>=2.0)】: {len(high_ev_misses)}件")
        for r in high_ev_misses[:5]:
            print(f"  {r['type']}: {r['horse']} (EV={r['ev']:.2f}, 着順={r['finish']})")
    
    # 結果保存
    result = {
        'target_dates': target_dates,
        'total_races': total_races,
        'config': {
            'fav_factor': config.fav_factor,
            'mid_factor': config.mid_factor,
            'long_factor': config.long_factor,
            'extreme_factor': config.extreme_factor,
            'ev_threshold': ev_threshold
        },
        'stats': stats,
        'bet_records': bet_records,
        'timestamp': datetime.now().isoformat()
    }
    
    os.makedirs('data', exist_ok=True)
    with open('data/light_backtest_result.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"\n結果を data/light_backtest_result.json に保存しました")
    
    return result


if __name__ == "__main__":
    # 2024年12月の特定日（有馬記念週）でテスト
    # 週末のみ（競馬開催日）
    target_dates = [
        "20241221",  # 土曜
        "20241222",  # 日曜（有馬記念）
    ]
    
    run_light_backtest(target_dates, ev_threshold=1.0)
