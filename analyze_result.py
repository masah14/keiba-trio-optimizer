"""バックテスト結果の分析"""
import json

with open('data/light_backtest_result.json', 'r', encoding='utf-8') as f:
    d = json.load(f)

print("=" * 70)
print("=== バックテスト結果 詳細分析 ===")
print("=" * 70)

# 統計
stats = d['stats']
win_roi = stats['win_payout'] / stats['win_investment'] * 100 if stats['win_investment'] > 0 else 0
place_roi = stats['place_payout'] / stats['place_investment'] * 100 if stats['place_investment'] > 0 else 0

print(f"\n【単勝】")
print(f"  ベット数: {stats['win_bets']}")
print(f"  的中数: {stats['win_hits']}")
print(f"  的中率: {stats['win_hits']/stats['win_bets']*100:.2f}%")
print(f"  ROI: {win_roi:.1f}%")

print(f"\n【複勝】")
print(f"  ベット数: {stats['place_bets']}")
print(f"  的中数: {stats['place_hits']}")
print(f"  的中率: {stats['place_hits']/stats['place_bets']*100:.2f}%")
print(f"  ROI: {place_roi:.1f}%")

# EV分布
records = d['bet_records']
win_records = [r for r in records if r['type'] == 'win']
place_records = [r for r in records if r['type'] == 'place']

win_evs = [r['ev'] for r in win_records]
win_odds = [r['odds'] for r in win_records]

print(f"\n=== EV分布（単勝） ===")
print(f"  平均EV: {sum(win_evs)/len(win_evs):.2f}")
print(f"  最大EV: {max(win_evs):.2f}")
print(f"  最小EV: {min(win_evs):.2f}")
print(f"  平均オッズ: {sum(win_odds)/len(win_odds):.1f}")

# 問題発見: 超高オッズ馬ばかり買っている？
high_odds = [r for r in win_records if r['odds'] > 50]
print(f"\n=== オッズ50倍超の馬 ===")
print(f"  該当数: {len(high_odds)}/{len(win_records)} ({len(high_odds)/len(win_records)*100:.1f}%)")

# 的中した馬
print(f"\n=== 的中した馬（単勝） ===")
win_hits = [r for r in win_records if r['hit']]
for h in win_hits:
    print(f"  {h['horse']}: EV={h['ev']:.2f}, オッズ={h['odds']}, 払戻={h['payout']}円")

print(f"\n=== 的中した馬（複勝） ===")
place_hits = [r for r in place_records if r['hit']]
for h in place_hits[:10]:
    print(f"  {h['horse']}: EV={h['ev']:.2f}, オッズ={h['odds']}, 着順={h['finish']}")

# 高EV外れの分析
print(f"\n=== 高EV(>=5.0)で外れた馬 ===")
high_ev_miss = [r for r in win_records if not r['hit'] and r['ev'] >= 5.0]
print(f"  該当数: {len(high_ev_miss)}")

# オッズ帯別の成績
print(f"\n=== オッズ帯別 的中率（単勝） ===")
odds_ranges = [(1, 10), (10, 30), (30, 50), (50, 100), (100, 500)]
for low, high in odds_ranges:
    in_range = [r for r in win_records if low <= r['odds'] < high]
    hits = [r for r in in_range if r['hit']]
    if in_range:
        print(f"  {low}-{high}倍: {len(hits)}/{len(in_range)} ({len(hits)/len(in_range)*100:.1f}%)")
