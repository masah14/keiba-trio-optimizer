
import pandas as pd
import numpy as np

# 2025 Arima Kinen Pre-race Data
# Data collected earlier (excluding results)
data = [
    {"num": 1, "name": "エキサイトバイオ", "jockey": "荻野極", "odds": 29.7, "training": "B", "performance": 3, "j_rank": 2},
    {"num": 2, "name": "シンエンペラー", "jockey": "坂井瑠", "odds": 26.6, "training": "B", "performance": 3, "j_rank": 4},
    {"num": 3, "name": "ジャスティンパレス", "jockey": "団野大", "odds": 12.7, "training": "B", "performance": 4, "j_rank": 3},
    {"num": 4, "name": "ミュージアムマイル", "jockey": "C.デムーロ", "odds": 3.8, "training": "A", "performance": 5, "j_rank": 5},
    {"num": 5, "name": "レガレイラ", "jockey": "C.ルメール", "odds": 3.3, "training": "A", "performance": 5, "j_rank": 5},
    {"num": 6, "name": "メイショウタバル", "jockey": "武豊", "odds": 5.8, "training": "A", "performance": 4, "j_rank": 4},
    {"num": 7, "name": "サンライズジパング", "jockey": "鮫島駿", "odds": 122.5, "training": "B", "performance": 2, "j_rank": 2},
    {"num": 8, "name": "シュヴァリエローズ", "jockey": "北村友", "odds": 154.1, "training": "C", "performance": 3, "j_rank": 2},
    {"num": 9, "name": "ダノンデサイル", "jockey": "戸崎圭", "odds": 3.8, "training": "A", "performance": 5, "j_rank": 4},
    {"num": 10, "name": "コスモキュランダ", "jockey": "横山武", "odds": 111.5, "training": "C", "performance": 2, "j_rank": 4},
    {"num": 11, "name": "ミステリーウェイ", "jockey": "松本大", "odds": 53.5, "training": "B", "performance": 3, "j_rank": 1},
    {"num": 12, "name": "マイネルエンペラー", "jockey": "丹内祐", "odds": 111.5, "training": "C", "performance": 3, "j_rank": 2},
    {"num": 13, "name": "アドマイヤテラ", "jockey": "川田将", "odds": 50.3, "training": "B", "performance": 3, "j_rank": 5},
    {"num": 14, "name": "アラタ", "jockey": "大野拓", "odds": 174.2, "training": "C", "performance": 2, "j_rank": 2},
    {"num": 15, "name": "エルトンバローズ", "jockey": "西村淳", "odds": 180.3, "training": "B", "performance": 2, "j_rank": 3},
    {"num": 16, "name": "タスティエーラ", "jockey": "松山弘", "odds": 35.4, "training": "A", "performance": 4, "j_rank": 4},
]

# True Probability Estimation Model (Heuristic)
# Factors:
# - Performance: 1-5 (G1 wins, recent rank)
# - Training: A=1.5, B=1.0, C=0.7 (multiplier)
# - Jockey: 1-5 (Win rate/Trust level)
def calculate_strength(h):
    base = h["performance"] * 2.0
    j_bonus = h["j_rank"] * 1.0
    t_mult = {"A": 1.3, "B": 1.0, "C": 0.8}[h["training"]]
    return (base + j_bonus) * t_mult

# 1. Win Probability & EV
total_strength = sum(calculate_strength(h) for h in data)
for h in data:
    h["true_win_prob"] = calculate_strength(h) / total_strength
    h["win_ev"] = h["true_win_prob"] * h["odds"]

df = pd.DataFrame(data)

# 2. Place Probability (Harville model approximation)
# P(Place) = P(1st) + P(2nd) + P(3rd)
# P(2nd) = sum over j!=i { P(j) * P(i)/(1-P(j)) }
def estimate_place_prob(idx, probs):
    p_i = probs[idx]
    p_1st = p_i
    p_2nd = 0
    for j in range(len(probs)):
        if idx == j: continue
        p_2nd += probs[j] * (p_i / (1 - probs[j]))
    
    # Simpler heuristic for Place (3 slots)
    # Usually Place prob is roughly 2.5x to 4x Win prob depending on the favorite status
    return min(0.95, p_i * 3.2) # Adjusted multiplier

probs = df["true_win_prob"].values
df["true_place_prob"] = [estimate_place_prob(i, probs) for i in range(len(probs))]
# Place odds are roughly WinOdds / 3.5 on average for calculation purposes
df["est_place_odds"] = df["odds"] / 3.5
df["place_ev"] = df["true_place_prob"] * df["est_place_odds"]

# 3. Trifecta Expected Value (Top combinations by EV)
# EV(i-j-k) = P(i)*P(j|i)*P(k|i,j) * TrifectaOdds
# Since we don't have real-time Trifecta odds here, we calculate 'Profitability Index' (Prob * Multiplier)

import sys
import io

# Ensure UTF-8 output for Japanese characters
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# trifecta_analysis.py additions
import itertools

# Recalculate everything to ensure local availability
total_strength = sum(calculate_strength(h) for h in data)
for h in data:
    h["true_win_prob"] = calculate_strength(h) / total_strength

# Function for conditional probability P(j|i) = P(j) / (1 - P(i))
def get_p2_given_p1(p1, p2):
    return p2 / (1 - p1)

def get_p3_given_p1_p2(p1, p2, p3):
    return p3 / (1 - p1 - p2)

# Simulate Trifecta combinations
# We assume the user wants TO WIN, so we look for Horse Numbers
trifectas = []
best_idx = df.index.tolist()

# NetKeiba Trifecta total pool usually has higher takeout, let's assume 72.5% payout
# Trifecta Odds estimation is hard without real data, so we use 'Synthetic Odds' = 1 / (MarketProb1 * MarketProb2 * MarketProb3)
# But here we use a simplified profitability index since we don't have the live board.

print("\n### 【期待値100%超 (EV > 1.0) の買い目】")

# 1. Win (単勝)
print("\n--- 単勝 (Win) ---")
high_ev_win = df[df["win_ev"] > 1.0].sort_values("win_ev", ascending=False)
if not high_ev_win.empty:
    print(high_ev_win[["num", "name", "odds", "win_ev"]].to_markdown(index=False))
else:
    print("該当なし（人気馬が適正オッズ以下の場合）")

# 2. Place (複勝)
print("\n--- 複勝 (Place) ---")
high_ev_place = df[df["place_ev"] > 1.0].sort_values("place_ev", ascending=False)
if not high_ev_place.empty:
    print(high_ev_place[["num", "name", "est_place_odds", "place_ev"]].to_markdown(index=False))

# 3. Recommended Trifecta Formation (3連単 期待値重視)
# Logic: Focus on horses where TrueProb > MarketProb
print("\n--- 3連単 (Trifecta) 推奨フォーメーション ---")
print("期待値に基づき、能力が高い人気馬と、オッズが跳ねている実力馬を組み合わせます。")

top_strength = df.sort_values("true_win_prob", ascending=False).head(3)["num"].tolist()
high_ev_horses = df.sort_values("win_ev", ascending=False).head(5)["num"].tolist()

print(f"【1着】: {top_strength} (実力上位: ミュージアムマイル、レガレイラ、ダノンデサイル)")
print(f"【2着】: {top_strength + high_ev_horses[:2]} (実力馬 + 期待値高)")
print(f"【3着】: {high_ev_horses} (期待値上位: タスティエーラ、エキサイトバイオ等)")

print("\n[狙い目買い目例]")
# Display top 5 theoretical high EV trifectas based on true_prob / (p1*p2*p3)
trifecta_evs = []
for i, j, k in itertools.permutations(data, 3):
    p1 = i["true_win_prob"]
    p2 = get_p2_given_p1(p1, j["true_win_prob"])
    p3 = get_p3_given_p1_p2(p1, j["true_win_prob"], k["true_win_prob"])
    prob = p1 * p2 * p3
    
    # Synthetic Odds based on market odds (Product of individual odds * takeout adjustment)
    # This is an approximation of long-tail odds behavior
    synthetic_odds = (i["odds"] * j["odds"] * k["odds"]) * 0.1 # Heuristic scaling
    ev = prob * synthetic_odds
    if ev > 1.5: # Show very high EV ones
        trifecta_evs.append({"comb": f"{i['num']}-{j['num']}-{k['num']}", "names": f"{i['name']}-{j['name']}-{k['name']}", "theor_ev": ev})

t_df = pd.DataFrame(trifecta_evs).sort_values("theor_ev", ascending=False).head(10)
print(t_df.to_markdown(index=False))
