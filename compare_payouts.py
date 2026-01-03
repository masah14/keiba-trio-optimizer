"""
推定式 vs 実際の払い戻し比較
"""
import json
import os

data_dir = 'data/2024_full'

print('Estimated vs Actual Trio Payout Comparison')
print('=' * 80)
print(f"{'Race':<25} {'Combo':<15} {'Est.':>10} {'Actual':>10} {'Diff%':>10}")
print('-' * 80)

diffs = []

for f in os.listdir(data_dir):
    if not f.endswith('.json'):
        continue
    
    with open(os.path.join(data_dir, f), 'r', encoding='utf-8') as fp:
        race = json.load(fp)
    
    trio = race.get('payouts', {}).get('trio', [])
    horses = race.get('horses', [])
    
    if not trio or not horses:
        continue
    
    # 実際の払い戻し
    actual_combo = trio[0]['combo']
    actual_payout = trio[0]['payout']
    
    # 推定計算: 該当馬のオッズを取得
    combo_horses = [h for h in horses if h.get('num') in actual_combo]
    
    if len(combo_horses) != 3:
        continue
    
    odds_product = 1.0
    for h in combo_horses:
        odds = h.get('odds', 10)
        if odds:
            odds_product *= odds
    
    estimated = max(200, odds_product * 0.04 * 100)  # 100円賭けた場合
    
    diff_pct = ((actual_payout - estimated) / estimated) * 100 if estimated > 0 else 0
    
    diffs.append({
        'race': f.replace('race_', '').replace('.json', ''),
        'combo': str(actual_combo),
        'estimated': estimated,
        'actual': actual_payout,
        'diff_pct': diff_pct
    })

# 表示（最大15件）
for d in diffs[:15]:
    print(f"{d['race']:<25} {d['combo']:<15} {d['estimated']:>10,.0f} {d['actual']:>10,} {d['diff_pct']:>+9.1f}%")

print('-' * 80)
if diffs:
    avg_diff = sum(d['diff_pct'] for d in diffs) / len(diffs)
    under = sum(1 for d in diffs if d['diff_pct'] < 0)
    over = sum(1 for d in diffs if d['diff_pct'] >= 0)
    print(f"Sample size: {len(diffs)} races")
    print(f"Average difference: {avg_diff:+.1f}%")
    print(f"Underestimated: {under}, Overestimated: {over}")
