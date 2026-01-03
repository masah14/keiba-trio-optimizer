"""
GIIIレースの距離別収支分析 - light_backtest_resultから
"""
import json
from collections import defaultdict

# バックテスト結果を読み込む
with open(r'c:\Users\まさし\Desktop\uma2\data\light_backtest_result.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# レース情報を取得するために、キャッシュからレースデータを読み込む
import os

cache_dirs = [
    r'c:\Users\まさし\Desktop\uma2\data\cache',
    r'c:\Users\まさし\Desktop\uma2\data\cache_with_ids',
    r'c:\Users\まさし\Desktop\uma2\data\backtest_2023_2024'
]

# レースID -> レース情報のマッピング
race_info_map = {}

for cache_dir in cache_dirs:
    if not os.path.exists(cache_dir):
        continue
    for filename in os.listdir(cache_dir):
        if not filename.endswith('.json'):
            continue
        filepath = os.path.join(cache_dir, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                race = json.load(f)
            race_id = race.get('race_id', '')
            race_info = race.get('race_info', {})
            if race_id:
                race_info_map[race_id] = race_info
        except:
            continue

print(f"Loaded {len(race_info_map)} race info records")

# 距離カテゴリ
def get_distance_category(distance):
    if distance <= 1400:
        return 'スプリント（～1400m）'
    elif distance <= 1800:
        return 'マイル（1401-1800m）'
    elif distance <= 2200:
        return '中距離（1801-2200m）'
    else:
        return '長距離（2201m～）'

# 三連複結果を抽出
trio_results = data.get('trio_results', [])
print(f"Total trio bets: {len(trio_results)}")

# 距離別集計
results = defaultdict(lambda: {'races': set(), 'bets': 0, 'investment': 0, 'return': 0, 'hits': 0})

for bet in trio_results:
    race_id = bet.get('race_id', '')
    race_info = race_info_map.get(race_id, {})
    race_class = race_info.get('class', '')
    distance = race_info.get('distance', 0)
    
    if race_class != 'GIII':
        continue
    
    if distance == 0:
        continue
    
    category = get_distance_category(distance)
    
    investment = bet.get('investment', 100)  # デフォルト100円
    payout = bet.get('payout', 0)
    hit = bet.get('hit', False)
    
    results[category]['races'].add(race_id)
    results[category]['bets'] += 1
    results[category]['investment'] += investment
    results[category]['return'] += payout
    if hit:
        results[category]['hits'] += 1

print("\n" + "="*80)
print("GIIIレース 距離別収支分析（三連複）")
print("="*80)
print(f"{'距離カテゴリ':<25} {'レース数':>8} {'ベット数':>8} {'的中':>6} {'投資':>12} {'回収':>12} {'収支':>12} {'ROI':>8}")
print("-"*80)

total_investment = 0
total_return = 0
total_races = 0
total_bets = 0
total_hits = 0

for category in ['スプリント（～1400m）', 'マイル（1401-1800m）', '中距離（1801-2200m）', '長距離（2201m～）']:
    data_cat = results[category]
    if len(data_cat['races']) == 0:
        continue
    
    profit = data_cat['return'] - data_cat['investment']
    roi = (data_cat['return'] / data_cat['investment'] * 100) if data_cat['investment'] > 0 else 0
    
    print(f"{category:<25} {len(data_cat['races']):>8} {data_cat['bets']:>8} {data_cat['hits']:>6} {data_cat['investment']:>12,} {data_cat['return']:>12,} {profit:>+12,} {roi:>7.1f}%")
    
    total_investment += data_cat['investment']
    total_return += data_cat['return']
    total_races += len(data_cat['races'])
    total_bets += data_cat['bets']
    total_hits += data_cat['hits']

print("-"*80)
total_profit = total_return - total_investment
total_roi = (total_return / total_investment * 100) if total_investment > 0 else 0
print(f"{'合計':<25} {total_races:>8} {total_bets:>8} {total_hits:>6} {total_investment:>12,} {total_return:>12,} {total_profit:>+12,} {total_roi:>7.1f}%")
print("="*80)
