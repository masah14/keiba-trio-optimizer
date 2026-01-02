"""
EV Engine V3 - 追加情報を活用した期待値計算エンジン

V2からの改良点:
1. 馬の過去成績（勝率、連対率）を使用
2. コース・距離適性を考慮
3. 騎手の勝率を加味
4. 直近成績のトレンドを反映
5. オッズへの依存度を下げ、独自スコアを重視
"""

import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Optional
import itertools


@dataclass
class EVConfigV3:
    """V3エンジンの設定"""
    # 重み付け（合計1.0）
    weight_base_ability: float = 0.35   # 基礎能力（勝率、連対率）
    weight_course_fit: float = 0.20    # コース適性
    weight_recent_form: float = 0.20   # 直近成績
    weight_jockey: float = 0.15        # 騎手
    weight_market: float = 0.10        # 市場評価（オッズ）
    
    # バイアス補正（控えめに）
    fav_factor: float = 0.95
    mid_factor: float = 1.00
    long_factor: float = 1.05
    extreme_factor: float = 1.10
    
    # 閾値
    min_horse_runs: int = 3   # 最低出走回数（これ未満は信頼度低）
    min_jockey_runs: int = 20  # 騎手の最低騎乗回数


class EVEngineV3:
    """
    拡張版期待値計算エンジン
    
    独自情報を活用して市場を上回る
    """
    
    def __init__(self, config: Optional[EVConfigV3] = None):
        self.config = config or EVConfigV3()
    
    def calculate_base_ability_score(self, horse: Dict) -> float:
        """
        基礎能力スコア（過去成績ベース）
        """
        profile = horse.get('horse_profile', {})
        
        if not profile:
            # プロファイルがない場合はオッズから推定
            odds = horse.get('odds', 10.0)
            return 0.75 / max(odds, 1.0)
        
        total_runs = profile.get('total_runs', 0)
        
        if total_runs < self.config.min_horse_runs:
            # 出走回数が少ない → 不確実性高い
            odds = horse.get('odds', 10.0)
            return 0.75 / max(odds, 1.0) * 0.8
        
        win_rate = profile.get('win_rate', 0.0)
        place_rate = profile.get('place_rate', 0.0)
        
        # 勝率と連対率を組み合わせ
        score = (win_rate * 0.6) + (place_rate * 0.4)
        
        return score
    
    def calculate_course_fit_score(self, horse: Dict) -> float:
        """
        コース適性スコア
        """
        profile = horse.get('horse_profile', {})
        
        if not profile:
            return 0.5  # 中立
        
        course_runs = profile.get('course_runs', 0)
        course_win_rate = profile.get('course_win_rate', 0.0)
        distance_runs = profile.get('distance_runs', 0)
        distance_win_rate = profile.get('distance_win_rate', 0.0)
        
        # コース成績
        if course_runs >= 2:
            course_score = course_win_rate
        else:
            course_score = 0.5  # データ不足は中立
        
        # 距離成績
        if distance_runs >= 2:
            distance_score = distance_win_rate
        else:
            distance_score = 0.5
        
        # 組み合わせ
        return (course_score * 0.5) + (distance_score * 0.5)
    
    def calculate_recent_form_score(self, horse: Dict) -> float:
        """
        直近成績スコア（調子を反映）
        """
        profile = horse.get('horse_profile', {})
        
        if not profile:
            return 0.5
        
        recent = profile.get('recent_finishes', [])
        
        if not recent:
            return 0.5
        
        # 直近成績を重み付け（最新ほど重要）
        weights = [1.0, 0.8, 0.6, 0.4, 0.2][:len(recent)]
        
        score = 0.0
        total_weight = sum(weights)
        
        for i, finish in enumerate(recent):
            if i >= len(weights):
                break
            # 着順を0-1のスコアに変換（1着=1.0, 10着以降=0）
            finish_score = max(0, 1.0 - (finish - 1) * 0.1)
            score += finish_score * weights[i]
        
        return score / total_weight if total_weight > 0 else 0.5
    
    def calculate_jockey_score(self, horse: Dict) -> float:
        """
        騎手スコア
        """
        jockey = horse.get('jockey_profile', {})
        
        if not jockey:
            return 0.5
        
        year_runs = jockey.get('year_runs', 0)
        year_win_rate = jockey.get('year_win_rate', 0.0)
        course_runs = jockey.get('course_runs', 0)
        course_win_rate = jockey.get('course_win_rate', 0.0)
        
        # 年間成績
        if year_runs >= self.config.min_jockey_runs:
            year_score = year_win_rate * 10  # 勝率10%で1.0
        else:
            year_score = 0.5
        
        # コース成績（ボーナス）
        if course_runs >= 5 and course_win_rate > year_win_rate:
            course_bonus = 0.1
        else:
            course_bonus = 0.0
        
        return min(1.0, year_score + course_bonus)
    
    def calculate_market_score(self, horse: Dict, field_size: int) -> float:
        """
        市場評価スコア（オッズベース）
        """
        odds = horse.get('odds', 10.0)
        popularity = horse.get('popularity', field_size // 2)
        
        # オッズから市場が示す勝率
        market_prob = 0.75 / max(odds, 1.0)
        
        # 人気順位からのスコア
        pop_score = (field_size - popularity + 1) / field_size
        
        return (market_prob * 0.6) + (pop_score * 0.4)
    
    def get_bias_factor(self, odds: float) -> float:
        """バイアス補正係数を取得"""
        if odds < 5:
            return self.config.fav_factor
        elif odds < 20:
            return self.config.mid_factor
        elif odds < 50:
            return self.config.long_factor
        else:
            return self.config.extreme_factor
    
    def calculate_strength_score(self, horse: Dict, field_size: int) -> float:
        """
        統合実力スコアを計算
        """
        cfg = self.config
        
        # 各コンポーネントスコアを計算
        base = self.calculate_base_ability_score(horse)
        course = self.calculate_course_fit_score(horse)
        recent = self.calculate_recent_form_score(horse)
        jockey = self.calculate_jockey_score(horse)
        market = self.calculate_market_score(horse, field_size)
        
        # 重み付け統合
        raw_score = (
            base * cfg.weight_base_ability +
            course * cfg.weight_course_fit +
            recent * cfg.weight_recent_form +
            jockey * cfg.weight_jockey +
            market * cfg.weight_market
        )
        
        # 信頼度調整（プロファイルがあるほど信頼度高い）
        has_horse_profile = 'horse_profile' in horse
        has_jockey_profile = 'jockey_profile' in horse
        
        if has_horse_profile and has_jockey_profile:
            confidence = 1.0
        elif has_horse_profile:
            confidence = 0.8
        elif has_jockey_profile:
            confidence = 0.7
        else:
            confidence = 0.5
        
        # デバッグ用に各スコアを保存
        horse['_scores'] = {
            'base': base,
            'course': course,
            'recent': recent,
            'jockey': jockey,
            'market': market,
            'raw': raw_score,
            'confidence': confidence
        }
        
        return raw_score * confidence
    
    def calculate_ev(self, horses: List[Dict]) -> List[Dict]:
        """
        期待値を計算
        """
        if not horses:
            return []
        
        field_size = len(horses)
        
        # 1. 実力スコア計算
        for h in horses:
            h['strength_score'] = self.calculate_strength_score(h, field_size)
        
        # 2. バイアス補正
        for h in horses:
            h['bias_factor'] = self.get_bias_factor(h['odds'])
            h['adjusted_strength'] = h['strength_score'] * h['bias_factor']
        
        # 3. 確率正規化
        total = sum(h['adjusted_strength'] for h in horses)
        if total > 0:
            for h in horses:
                h['true_win_prob'] = h['adjusted_strength'] / total
        else:
            for h in horses:
                h['true_win_prob'] = 1.0 / field_size
        
        # 4. 単勝EV
        for h in horses:
            h['win_ev'] = h['true_win_prob'] * h['odds']
        
        # 5. 複勝EV
        for h in horses:
            pop = h.get('popularity', field_size // 2)
            place_slots = 3 if field_size >= 8 else 2
            
            # 複勝確率
            mult = place_slots * 0.9 if h['true_win_prob'] > 0.1 else place_slots * 1.0
            h['true_place_prob'] = min(0.95, h['true_win_prob'] * mult)
            
            # 複勝オッズ推定
            h['est_place_odds'] = h['odds'] / (field_size / place_slots)
            h['place_ev'] = h['true_place_prob'] * h['est_place_odds']
        
        return horses
    
    def get_recommendations(self, horses: List[Dict], 
                           win_threshold: float = 1.2,
                           place_threshold: float = 1.2,
                           max_odds: float = 50.0) -> Dict:
        """
        推奨買い目を取得
        
        改良点:
        - EVだけでなく、信頼度も考慮
        - オッズ上限を設定
        """
        filtered = [h for h in horses if h.get('odds', 999) <= max_odds]
        
        win_recs = [
            h for h in filtered 
            if h.get('win_ev', 0) >= win_threshold
            and h.get('_scores', {}).get('confidence', 0) >= 0.7
        ]
        
        place_recs = [
            h for h in filtered 
            if h.get('place_ev', 0) >= place_threshold
            and h.get('_scores', {}).get('confidence', 0) >= 0.7
        ]
        
        return {
            'win': sorted(win_recs, key=lambda x: x['win_ev'], reverse=True),
            'place': sorted(place_recs, key=lambda x: x['place_ev'], reverse=True),
            'summary': {
                'win_count': len(win_recs),
                'place_count': len(place_recs),
            }
        }


def compare_with_v2():
    """V2とV3の比較テスト"""
    print("=== EV Engine V2 vs V3 Comparison ===\n")
    
    # テストデータ（プロファイル付き）
    test_horses = [
        {
            'num': 1, 'name': '実績馬', 'odds': 3.5, 'popularity': 1,
            'horse_profile': {
                'win_rate': 0.25, 'place_rate': 0.55, 
                'course_win_rate': 0.30, 'course_runs': 5,
                'recent_finishes': [1, 2, 1, 3, 2]
            },
            'jockey_profile': {'year_win_rate': 0.15, 'year_runs': 100}
        },
        {
            'num': 2, 'name': '穴馬', 'odds': 25.0, 'popularity': 5,
            'horse_profile': {
                'win_rate': 0.08, 'place_rate': 0.20,
                'course_win_rate': 0.20, 'course_runs': 5,
                'recent_finishes': [5, 1, 8, 4, 2]  # 直近で激走
            },
            'jockey_profile': {'year_win_rate': 0.08, 'year_runs': 80}
        },
        {
            'num': 3, 'name': '人気薄', 'odds': 80.0, 'popularity': 8,
            'horse_profile': {
                'win_rate': 0.02, 'place_rate': 0.10,
                'course_win_rate': 0.0, 'course_runs': 3,
                'recent_finishes': [10, 12, 8, 9, 11]
            },
            'jockey_profile': {'year_win_rate': 0.05, 'year_runs': 50}
        },
    ]
    
    from ev_engine_v2 import EVEngineV2
    
    v2 = EVEngineV2()
    v3 = EVEngineV3()
    
    v2_result = v2.calculate_ev([h.copy() for h in test_horses])
    v3_result = v3.calculate_ev([h.copy() for h in test_horses])
    
    print(f"{'馬名':<12} | {'V2単勝EV':>10} | {'V3単勝EV':>10} | {'差':>8}")
    print("-" * 50)
    
    for v2h, v3h in zip(v2_result, v3_result):
        diff = v3h['win_ev'] - v2h['win_ev']
        print(f"{v2h['name']:<12} | {v2h['win_ev']:>10.3f} | {v3h['win_ev']:>10.3f} | {diff:>+8.3f}")
    
    print("\n【V3の詳細スコア】")
    for h in v3_result:
        scores = h.get('_scores', {})
        print(f"\n{h['name']}:")
        print(f"  基礎能力: {scores.get('base', 0):.3f}")
        print(f"  コース適性: {scores.get('course', 0):.3f}")
        print(f"  直近成績: {scores.get('recent', 0):.3f}")
        print(f"  騎手: {scores.get('jockey', 0):.3f}")
        print(f"  市場: {scores.get('market', 0):.3f}")
        print(f"  信頼度: {scores.get('confidence', 0):.3f}")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, 'app')
    compare_with_v2()
