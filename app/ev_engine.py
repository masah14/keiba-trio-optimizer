
import pandas as pd
import numpy as np

class EVEngine:
    def __init__(self):
        # Coefficients for probability adjustment (Outsider Bias)
        self.bias_factors = {
            "fav": 0.85,    # Favorite correction (public often overbets favorites)
            "mid": 1.1,     # Mid-range
            "long": 1.4,    # Long shots (public often underbets value longshots)
            "extreme": 1.8  # Extreme outsiders
        }

    def calculate_ev(self, horses):
        """
        horses: list of dicts {num, name, odds, training, performance, j_rank}
        """
        df = pd.DataFrame(horses)
        
        # 1. Calculate "True Strength" Score
        def score_horse(h):
            base = h["performance"] * 2.5
            j_bonus = h["j_rank"] * 1.2
            t_mult = {"A": 1.4, "B": 1.0, "C": 0.7}[h.get("training", "B")]
            return (base + j_bonus) * t_mult

        df["strength_score"] = df.apply(score_horse, axis=1)
        
        # 2. Probability Adjustment (Outsider Bias Correction)
        def get_bias(odds):
            if odds < 5: return self.bias_factors["fav"]
            elif odds < 20: return self.bias_factors["mid"]
            elif odds < 50: return self.bias_factors["long"]
            else: return self.bias_factors["extreme"]

        df["bias_factor"] = df["odds"].apply(get_bias)
        df["adjusted_strength"] = df["strength_score"] * df["bias_factor"]
        
        # Normalize to get True Probabilities
        sum_strength = df["adjusted_strength"].sum()
        df["true_win_prob"] = df["adjusted_strength"] / sum_strength
        
        # 3. Calculate Win EV
        df["win_ev"] = df["true_win_prob"] * df["odds"]
        
        # 4. Estimate Place (Fuku) Prob & EV
        # Harville model approximation for 3 slots
        def estimate_place(idx, probs):
            p_i = probs[idx]
            # Simple heuristic based on WinProb for speed in real-time
            # Place prob is higher for favorites, much higher multiplier for outsiders
            mult = 2.8 if p_i > 0.1 else 3.5
            return min(0.95, p_i * mult)

        probs = df["true_win_prob"].values
        df["true_place_prob"] = [estimate_place(i, probs) for i in range(len(probs))]
        df["est_place_odds"] = df["odds"] / 3.8 # Heuristic for average place payout
        df["place_ev"] = df["true_place_prob"] * df["est_place_odds"]
        
        return df.to_dict(orient="records")

    def get_top_trifectas(self, horses, limit=10):
        # High complexity calculation for top 3-tuple EVs
        # Since Trifecta pool is deep, we focus on TrueProb Combinations
        df = pd.DataFrame(horses)
        probs = df.set_index("num")["true_win_prob"].to_dict()
        odds = df.set_index("num")["odds"].to_dict()
        names = df.set_index("num")["name"].to_dict()
        
        res = []
        nums = df["num"].tolist()
        import itertools
        
        for p1_num, p2_num, p3_num in itertools.permutations(nums, 3):
            pr1 = probs[p1_num]
            pr2 = probs[p2_num] / (1 - pr1)
            pr3 = probs[p3_num] / (1 - pr1 - probs[p2_num])
            
            total_prob = pr1 * pr2 * pr3
            # Estimate Trifecta Odds: roughly product of win odds * 0.07 adjustment
            est_tri_odds = (odds[p1_num] * odds[p2_num] * odds[p3_num]) * 0.08
            ev = total_prob * est_tri_odds
            
            if ev > 1.2:
                res.append({
                    "comb": f"{p1_num}-{p2_num}-{p3_num}",
                    "names": f"{names[p1_num]}-{names[p2_num]}-{names[p3_num]}",
                    "prob": total_prob,
                    "est_odds": est_tri_odds,
                    "ev": ev
                })
        
        return sorted(res, key=lambda x: x["ev"], reverse=True)[:limit]
