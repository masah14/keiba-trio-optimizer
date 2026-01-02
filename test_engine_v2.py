"""EV Engine V2のテスト"""
import sys
sys.path.insert(0, 'app')

from ev_engine_v2 import EVEngineV2, BiasConfig, SensitivityAnalyzer

print("=== EV Engine V2 Test ===\n")

# サンプルデータ
sample_horses = [
    {'num': 1, 'name': 'レガレイラ', 'odds': 3.3, 'popularity': 1},
    {'num': 2, 'name': 'ダノンデサイル', 'odds': 3.8, 'popularity': 2},
    {'num': 3, 'name': 'ミュージアムマイル', 'odds': 3.8, 'popularity': 3},
    {'num': 4, 'name': 'メイショウタバル', 'odds': 5.8, 'popularity': 4},
    {'num': 5, 'name': 'ジャスティンパレス', 'odds': 12.7, 'popularity': 5},
    {'num': 6, 'name': 'シンエンペラー', 'odds': 26.6, 'popularity': 6},
    {'num': 7, 'name': 'タスティエーラ', 'odds': 35.4, 'popularity': 7},
    {'num': 8, 'name': 'コスモキュランダ', 'odds': 111.5, 'popularity': 8},
]

# デフォルト設定でEV計算
engine = EVEngineV2()
result = engine.calculate_ev(sample_horses)

print("【EV計算結果】")
print("-" * 70)
print(f"{'馬番':<6}{'馬名':<20}{'オッズ':<10}{'単勝EV':<12}{'複勝EV':<12}")
print("-" * 70)

for h in result:
    ev_marker = "★" if h['win_ev'] >= 1.0 else ""
    place_marker = "★" if h['place_ev'] >= 1.0 else ""
    print(f"{h['num']:<6}{h['name']:<20}{h['odds']:<10.1f}{h['win_ev']:<10.3f}{ev_marker:<2}{h['place_ev']:<10.3f}{place_marker}")

print("\n【推奨買い目】")
recs = engine.get_recommendations(result)
print(f"単勝推奨: {recs['summary']['win_count']}件")
print(f"複勝推奨: {recs['summary']['place_count']}件")

if recs['win']:
    print("\n単勝推奨馬:")
    for h in recs['win']:
        print(f"  {h['num']}. {h['name']} (EV: {h['win_ev']:.3f})")

if recs['place']:
    print("\n複勝推奨馬:")
    for h in recs['place']:
        print(f"  {h['num']}. {h['name']} (EV: {h['place_ev']:.3f})")

# 感度分析
print("\n\n=== 感度分析: long_factor ===")
sensitivity = SensitivityAnalyzer.analyze_bias_sensitivity(
    sample_horses, 
    'long_factor', 
    [1.0, 1.2, 1.4, 1.6, 1.8]
)
print(sensitivity.to_string(index=False))

print("\n=== Test Complete ===")
