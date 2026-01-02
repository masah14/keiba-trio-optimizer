"""
修正版バックテスト分析

問題: extreme_factor=2.0 が穴馬を過大評価していた
修正: 
1. extreme_factor を 1.2 に下げる
2. オッズ100倍以上は購入対象外
3. EV閾値を1.0から段階的に検証
"""

import json
import sys
sys.path.insert(0, 'app')
from ev_engine_v2 import EVEngineV2, BiasConfig

# 過去のバックテストデータを再分析
with open('data/light_backtest_result.json', 'r', encoding='utf-8') as f:
    original_data = json.load(f)

# キャッシュされたレースを再取得
import os
cache_dir = 'data/cache'
races = []
for filename in os.listdir(cache_dir):
    if filename.startswith('race_') and filename.endswith('.json'):
        with open(os.path.join(cache_dir, filename), 'r', encoding='utf-8') as f:
            race = json.load(f)
            if race.get('horses') and len(race['horses']) >= 3:
                races.append(race)

print(f"Loaded {len(races)} races from cache")

def run_analysis(config, ev_threshold, max_odds=None, name=""):
    """指定設定でバックテストを再実行"""
    engine = EVEngineV2(config)
    bet_unit = 100
    
    stats = {
        'win_bets': 0, 'win_hits': 0, 'win_investment': 0, 'win_payout': 0,
        'place_bets': 0, 'place_hits': 0, 'place_investment': 0, 'place_payout': 0
    }
    
    for race in races:
        horses = race.get('horses', [])
        if not horses:
            continue
        
        calculated = engine.calculate_ev([h.copy() for h in horses])
        payouts = race.get('payouts', {'win': {}, 'place': {}})
        
        for h in calculated:
            num = h['num']
            finish = h.get('finish', 0)
            odds = h.get('odds', 0)
            
            # オッズ上限チェック
            if max_odds and odds > max_odds:
                continue
            
            # 単勝
            if h.get('win_ev', 0) >= ev_threshold:
                stats['win_bets'] += 1
                stats['win_investment'] += bet_unit
                
                if finish == 1:
                    stats['win_hits'] += 1
                    payout = payouts.get('win', {}).get(num, 0)
                    stats['win_payout'] += payout
            
            # 複勝
            if h.get('place_ev', 0) >= ev_threshold:
                stats['place_bets'] += 1
                stats['place_investment'] += bet_unit
                
                if finish <= 3:
                    stats['place_hits'] += 1
                    payout = payouts.get('place', {}).get(num, 0)
                    stats['place_payout'] += payout
    
    win_roi = (stats['win_payout'] / stats['win_investment'] * 100) if stats['win_investment'] > 0 else 0
    place_roi = (stats['place_payout'] / stats['place_investment'] * 100) if stats['place_investment'] > 0 else 0
    
    return {
        'name': name,
        'config': f"fav={config.fav_factor}, mid={config.mid_factor}, long={config.long_factor}, ext={config.extreme_factor}",
        'ev_threshold': ev_threshold,
        'max_odds': max_odds,
        'win_bets': stats['win_bets'],
        'win_hits': stats['win_hits'],
        'win_roi': win_roi,
        'place_bets': stats['place_bets'],
        'place_hits': stats['place_hits'],
        'place_roi': place_roi,
        'total_profit': (stats['win_payout'] + stats['place_payout']) - (stats['win_investment'] + stats['place_investment'])
    }

print("\n" + "=" * 80)
print("=== パラメータ修正テスト ===")
print("=" * 80)

# テスト設定
configs = [
    ("オリジナル(問題あり)", BiasConfig(fav_factor=0.95, mid_factor=1.00, long_factor=1.20, extreme_factor=2.00)),
    ("extreme=1.5", BiasConfig(fav_factor=0.95, mid_factor=1.00, long_factor=1.20, extreme_factor=1.50)),
    ("extreme=1.2", BiasConfig(fav_factor=0.95, mid_factor=1.00, long_factor=1.20, extreme_factor=1.20)),
    ("extreme=1.0(無補正)", BiasConfig(fav_factor=0.95, mid_factor=1.00, long_factor=1.20, extreme_factor=1.00)),
    ("保守的", BiasConfig(fav_factor=0.90, mid_factor=1.00, long_factor=1.10, extreme_factor=1.00)),
]

ev_thresholds = [1.0, 1.2, 1.5]
max_odds_list = [None, 50, 30]

results = []

for config_name, config in configs:
    for ev_th in ev_thresholds:
        for max_odds in max_odds_list:
            name = f"{config_name} | EV>={ev_th}"
            if max_odds:
                name += f" | max{max_odds}x"
            
            result = run_analysis(config, ev_th, max_odds, name)
            results.append(result)

# 結果表示
print(f"\n{'設定':<50} | {'単勝':<20} | {'複勝':<20} | {'損益':>10}")
print("-" * 110)

for r in results:
    win_info = f"{r['win_hits']}/{r['win_bets']} ROI:{r['win_roi']:.0f}%"
    place_info = f"{r['place_hits']}/{r['place_bets']} ROI:{r['place_roi']:.0f}%"
    print(f"{r['name']:<50} | {win_info:<20} | {place_info:<20} | {r['total_profit']:>+10,}円")

# 最も良い結果を抽出
print("\n" + "=" * 80)
print("=== ROI 100% 以上の設定 ===")
print("=" * 80)

profitable = [r for r in results if r['win_roi'] >= 100 or r['place_roi'] >= 100]
if profitable:
    for r in profitable:
        print(f"\n{r['name']}")
        print(f"  単勝: {r['win_hits']}/{r['win_bets']} = ROI {r['win_roi']:.1f}%")
        print(f"  複勝: {r['place_hits']}/{r['place_bets']} = ROI {r['place_roi']:.1f}%")
        print(f"  損益: {r['total_profit']:+,}円")
else:
    print("なし - すべての設定でROI < 100%")

# 最も損失の少ない設定
print("\n=== 損失最小の設定 ===")
best = min(results, key=lambda x: abs(x['total_profit']))
print(f"{best['name']}")
print(f"  単勝: {best['win_hits']}/{best['win_bets']} = ROI {best['win_roi']:.1f}%")
print(f"  複勝: {best['place_hits']}/{best['place_bets']} = ROI {best['place_roi']:.1f}%")
print(f"  損益: {best['total_profit']:+,}円")
