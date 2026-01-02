"""
バイアス係数最適化フレームワーク

目的:
1. グリッドサーチで最適なバイアス係数を探索
2. クロスバリデーションでオーバーフィットを検出
3. 感度分析でパラメータの安定性を検証
4. 最終的に「安全な」パラメータ範囲を特定

理論的背景:
- Favorite-Longshot Bias: 人気馬は過大評価される傾向がある
- 係数が大きすぎる → 穴馬に過度に賭けてしまう
- 係数が小さすぎる → 期待値の高い馬を見逃す
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, asdict
from typing import List, Dict, Tuple, Optional
import itertools
import json
import os
from datetime import datetime

import sys
sys.path.insert(0, 'app')
from ev_engine_v2 import EVEngineV2, BiasConfig


@dataclass
class OptimizationResult:
    """最適化結果"""
    fav_factor: float
    mid_factor: float
    long_factor: float
    extreme_factor: float
    win_roi: float
    place_roi: float
    win_hit_rate: float
    place_hit_rate: float
    win_bet_count: int
    place_bet_count: int
    total_profit: int
    stability_score: float  # パラメータ安定性スコア（高いほど良い）


class BiasOptimizer:
    """
    バイアス係数の最適化器
    
    使用方法:
    1. 過去のレースデータを読み込む
    2. グリッドサーチで候補パラメータを探索
    3. 最も安定した高ROIパラメータを選択
    """
    
    def __init__(self, bet_unit: int = 100):
        self.bet_unit = bet_unit
        self.results_cache = []
        
    def load_race_data(self, data_dir: str = "data/cache") -> List[Dict]:
        """
        キャッシュからレースデータを読み込む
        """
        races = []
        
        if not os.path.exists(data_dir):
            print(f"Warning: Cache directory {data_dir} does not exist")
            return races
        
        for filename in os.listdir(data_dir):
            if filename.startswith("race_") and filename.endswith(".json"):
                filepath = os.path.join(data_dir, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        race = json.load(f)
                        if race.get('horses') and len(race['horses']) >= 3:
                            races.append(race)
                except Exception as e:
                    continue
        
        print(f"Loaded {len(races)} races from cache")
        return races
    
    def generate_synthetic_races(self, n_races: int = 500, seed: int = 42) -> List[Dict]:
        """
        シミュレーション用の合成レースデータを生成
        
        実際の競馬データの統計的特性を模倣:
        - オッズ分布: 対数正規分布
        - 勝率と人気の相関
        - 複勝の的中率
        """
        np.random.seed(seed)
        races = []
        
        for race_id in range(n_races):
            n_horses = np.random.randint(8, 17)  # 8-16頭
            
            # オッズを生成（対数正規分布）
            log_odds = np.random.normal(2.5, 1.0, n_horses)
            odds = np.exp(log_odds)
            odds = np.clip(odds, 1.1, 300)  # 1.1倍〜300倍
            
            # 人気順はオッズ順
            rankings = np.argsort(odds) + 1
            
            horses = []
            for i in range(n_horses):
                horses.append({
                    'num': i + 1,
                    'name': f'Horse_{race_id}_{i+1}',
                    'odds': float(odds[i]),
                    'popularity': int(rankings[i]),
                    'finish': 0  # 後で設定
                })
            
            # 着順を決定（確率的に）
            # 真の実力 = オッズの逆数 + ノイズ
            true_strength = 1 / odds + np.random.normal(0, 0.1, n_horses)
            true_strength = np.maximum(true_strength, 0.01)
            true_probs = true_strength / true_strength.sum()
            
            # 着順をサンプリング（1着、2着、3着...）
            finish_order = np.random.choice(
                range(n_horses), 
                size=n_horses, 
                replace=False, 
                p=true_probs
            )
            
            for rank, horse_idx in enumerate(finish_order):
                horses[horse_idx]['finish'] = rank + 1
            
            # 払戻を生成
            payouts = {'win': {}, 'place': {}}
            for h in horses:
                if h['finish'] == 1:
                    # 単勝払戻 = オッズ × 100（100円あたり）
                    payouts['win'][h['num']] = int(h['odds'] * 100)
                if h['finish'] <= 3:
                    # 複勝払戻 = オッズ / 3.5 × 100（概算）
                    place_odds = max(1.1, h['odds'] / (3.5 + np.random.uniform(-0.5, 0.5)))
                    payouts['place'][h['num']] = int(place_odds * 100)
            
            races.append({
                'race_id': f'synthetic_{race_id:04d}',
                'title': f'Synthetic Race {race_id}',
                'horses': horses,
                'payouts': payouts
            })
        
        return races
    
    def evaluate_params(self, races: List[Dict], config: BiasConfig, 
                       ev_threshold: float = 1.0) -> Dict:
        """
        指定パラメータでレースを評価し、ROIを計算
        """
        engine = EVEngineV2(config)
        
        stats = {
            'win_bets': 0, 'win_hits': 0, 'win_investment': 0, 'win_payout': 0,
            'place_bets': 0, 'place_hits': 0, 'place_investment': 0, 'place_payout': 0
        }
        
        for race in races:
            horses = race.get('horses', [])
            if not horses:
                continue
            
            # EV計算
            calculated = engine.calculate_ev([h.copy() for h in horses])
            payouts = race.get('payouts', {'win': {}, 'place': {}})
            
            for h in calculated:
                num = h['num']
                finish = h.get('finish', 0)
                
                # 単勝
                if h.get('win_ev', 0) >= ev_threshold:
                    stats['win_bets'] += 1
                    stats['win_investment'] += self.bet_unit
                    
                    if finish == 1:
                        stats['win_hits'] += 1
                        payout = payouts.get('win', {}).get(num, 0)
                        stats['win_payout'] += payout
                
                # 複勝
                if h.get('place_ev', 0) >= ev_threshold:
                    stats['place_bets'] += 1
                    stats['place_investment'] += self.bet_unit
                    
                    if finish <= 3:
                        stats['place_hits'] += 1
                        payout = payouts.get('place', {}).get(num, 0)
                        stats['place_payout'] += payout
        
        # ROI計算
        win_roi = (stats['win_payout'] / stats['win_investment'] * 100) if stats['win_investment'] > 0 else 0
        place_roi = (stats['place_payout'] / stats['place_investment'] * 100) if stats['place_investment'] > 0 else 0
        win_hit_rate = (stats['win_hits'] / stats['win_bets'] * 100) if stats['win_bets'] > 0 else 0
        place_hit_rate = (stats['place_hits'] / stats['place_bets'] * 100) if stats['place_bets'] > 0 else 0
        
        return {
            'win_roi': win_roi,
            'place_roi': place_roi,
            'win_hit_rate': win_hit_rate,
            'place_hit_rate': place_hit_rate,
            'win_bets': stats['win_bets'],
            'place_bets': stats['place_bets'],
            'win_profit': stats['win_payout'] - stats['win_investment'],
            'place_profit': stats['place_payout'] - stats['place_investment'],
            'total_profit': (stats['win_payout'] + stats['place_payout']) - (stats['win_investment'] + stats['place_investment'])
        }
    
    def grid_search(self, races: List[Dict], 
                   fav_range: Tuple[float, float, float] = (0.70, 0.95, 0.05),
                   mid_range: Tuple[float, float, float] = (1.00, 1.30, 0.05),
                   long_range: Tuple[float, float, float] = (1.20, 1.60, 0.10),
                   extreme_range: Tuple[float, float, float] = (1.30, 2.00, 0.10),
                   ev_threshold: float = 1.0) -> pd.DataFrame:
        """
        グリッドサーチで最適パラメータを探索
        
        Args:
            races: レースデータ
            *_range: (開始, 終了, ステップ)のタプル
            ev_threshold: EV閾値
        """
        fav_values = np.arange(fav_range[0], fav_range[1] + 0.001, fav_range[2])
        mid_values = np.arange(mid_range[0], mid_range[1] + 0.001, mid_range[2])
        long_values = np.arange(long_range[0], long_range[1] + 0.001, long_range[2])
        extreme_values = np.arange(extreme_range[0], extreme_range[1] + 0.001, extreme_range[2])
        
        total_combinations = len(fav_values) * len(mid_values) * len(long_values) * len(extreme_values)
        print(f"Grid search: {total_combinations} combinations")
        
        results = []
        count = 0
        
        for fav, mid, lng, ext in itertools.product(fav_values, mid_values, long_values, extreme_values):
            config = BiasConfig(
                fav_factor=round(fav, 2),
                mid_factor=round(mid, 2),
                long_factor=round(lng, 2),
                extreme_factor=round(ext, 2)
            )
            
            eval_result = self.evaluate_params(races, config, ev_threshold)
            
            results.append({
                'fav_factor': config.fav_factor,
                'mid_factor': config.mid_factor,
                'long_factor': config.long_factor,
                'extreme_factor': config.extreme_factor,
                **eval_result
            })
            
            count += 1
            if count % 100 == 0:
                print(f"  Progress: {count}/{total_combinations}")
        
        df = pd.DataFrame(results)
        self.results_cache = results
        return df
    
    def cross_validate(self, races: List[Dict], config: BiasConfig, 
                      n_folds: int = 5, ev_threshold: float = 1.0) -> Dict:
        """
        クロスバリデーションでパラメータの安定性を検証
        
        過学習を検出するために、データを分割して評価
        """
        np.random.seed(42)
        indices = np.arange(len(races))
        np.random.shuffle(indices)
        
        fold_size = len(races) // n_folds
        fold_results = []
        
        for fold in range(n_folds):
            # テストセット
            test_start = fold * fold_size
            test_end = test_start + fold_size
            test_indices = indices[test_start:test_end]
            
            test_races = [races[i] for i in test_indices]
            
            result = self.evaluate_params(test_races, config, ev_threshold)
            fold_results.append(result)
        
        # 各フォールドの結果を集計
        win_rois = [r['win_roi'] for r in fold_results]
        place_rois = [r['place_roi'] for r in fold_results]
        
        return {
            'mean_win_roi': np.mean(win_rois),
            'std_win_roi': np.std(win_rois),
            'mean_place_roi': np.mean(place_rois),
            'std_place_roi': np.std(place_rois),
            'min_win_roi': np.min(win_rois),
            'max_win_roi': np.max(win_rois),
            'fold_results': fold_results,
            'stability_score': 1.0 / (1.0 + np.std(win_rois) + np.std(place_rois))  # 分散が小さいほど安定
        }
    
    def find_optimal_params(self, races: List[Dict], 
                           top_n: int = 10,
                           min_bets: int = 50,
                           stability_weight: float = 0.3) -> pd.DataFrame:
        """
        最適なパラメータを見つける
        
        考慮する要素:
        1. ROI（高いほど良い）
        2. 安定性（クロスバリデーションの分散が小さいほど良い）
        3. 十分なベット数（サンプルサイズ）
        
        Args:
            races: レースデータ
            top_n: 上位何件を返すか
            min_bets: 最低ベット数
            stability_weight: 安定性の重み（0-1）
        """
        # まずグリッドサーチ
        print("Phase 1: Grid Search")
        grid_results = self.grid_search(races)
        
        # 最低ベット数でフィルタ
        filtered = grid_results[
            (grid_results['win_bets'] >= min_bets) | 
            (grid_results['place_bets'] >= min_bets)
        ].copy()
        
        if len(filtered) == 0:
            print("Warning: No results with enough bets. Returning all results.")
            filtered = grid_results.copy()
        
        # 上位候補を抽出（複合ROIでソート）
        filtered['combined_roi'] = (filtered['win_roi'] + filtered['place_roi'] * 2) / 3  # 複勝を重視
        top_candidates = filtered.nlargest(min(50, len(filtered)), 'combined_roi')
        
        # クロスバリデーション
        print("\nPhase 2: Cross-Validation for top candidates")
        cv_results = []
        
        for _, row in top_candidates.iterrows():
            config = BiasConfig(
                fav_factor=row['fav_factor'],
                mid_factor=row['mid_factor'],
                long_factor=row['long_factor'],
                extreme_factor=row['extreme_factor']
            )
            
            cv = self.cross_validate(races, config)
            
            # スコア計算（ROI + 安定性）
            roi_score = (cv['mean_win_roi'] + cv['mean_place_roi'] * 2) / 3 / 100  # 正規化
            stability = cv['stability_score']
            
            final_score = roi_score * (1 - stability_weight) + stability * stability_weight
            
            cv_results.append({
                'fav_factor': row['fav_factor'],
                'mid_factor': row['mid_factor'],
                'long_factor': row['long_factor'],
                'extreme_factor': row['extreme_factor'],
                'mean_win_roi': cv['mean_win_roi'],
                'std_win_roi': cv['std_win_roi'],
                'mean_place_roi': cv['mean_place_roi'],
                'std_place_roi': cv['std_place_roi'],
                'stability_score': stability,
                'final_score': final_score,
                'win_bets': row['win_bets'],
                'place_bets': row['place_bets']
            })
        
        result_df = pd.DataFrame(cv_results)
        result_df = result_df.sort_values('final_score', ascending=False).head(top_n)
        
        return result_df
    
    def sensitivity_analysis(self, races: List[Dict], 
                            base_config: BiasConfig,
                            param_name: str,
                            delta_range: Tuple[float, float, float] = (-0.2, 0.2, 0.05)) -> pd.DataFrame:
        """
        特定パラメータの感度分析
        
        基準値から ±delta の範囲でROIの変化を測定
        """
        base_value = getattr(base_config, param_name)
        deltas = np.arange(delta_range[0], delta_range[1] + 0.001, delta_range[2])
        
        results = []
        
        for delta in deltas:
            test_value = base_value + delta
            if test_value <= 0:
                continue
            
            config = BiasConfig(
                fav_factor=base_config.fav_factor,
                mid_factor=base_config.mid_factor,
                long_factor=base_config.long_factor,
                extreme_factor=base_config.extreme_factor
            )
            setattr(config, param_name, test_value)
            
            eval_result = self.evaluate_params(races, config)
            
            results.append({
                'delta': delta,
                'value': test_value,
                'win_roi': eval_result['win_roi'],
                'place_roi': eval_result['place_roi'],
                'combined_roi': (eval_result['win_roi'] + eval_result['place_roi']) / 2
            })
        
        return pd.DataFrame(results)
    
    def generate_report(self, optimal_params: pd.DataFrame, 
                       sensitivity_results: Dict[str, pd.DataFrame],
                       output_path: str = "data/optimization_report.md"):
        """
        最適化レポートを生成
        """
        lines = []
        lines.append("# バイアス係数最適化レポート")
        lines.append(f"\n生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        lines.append("\n## 1. 最適パラメータ（上位5件）")
        lines.append("\n| Rank | fav | mid | long | extreme | Win ROI | Place ROI | Stability |")
        lines.append("|------|-----|-----|------|---------|---------|-----------|-----------|")
        
        for i, (_, row) in enumerate(optimal_params.head(5).iterrows()):
            lines.append(f"| {i+1} | {row['fav_factor']:.2f} | {row['mid_factor']:.2f} | "
                        f"{row['long_factor']:.2f} | {row['extreme_factor']:.2f} | "
                        f"{row['mean_win_roi']:.1f}% | {row['mean_place_roi']:.1f}% | "
                        f"{row['stability_score']:.3f} |")
        
        lines.append("\n## 2. 推奨パラメータ")
        best = optimal_params.iloc[0]
        lines.append(f"\n```python")
        lines.append(f"BiasConfig(")
        lines.append(f"    fav_factor={best['fav_factor']:.2f},")
        lines.append(f"    mid_factor={best['mid_factor']:.2f},")
        lines.append(f"    long_factor={best['long_factor']:.2f},")
        lines.append(f"    extreme_factor={best['extreme_factor']:.2f}")
        lines.append(f")")
        lines.append(f"```")
        
        lines.append(f"\n- 期待Win ROI: {best['mean_win_roi']:.1f}% (±{best['std_win_roi']:.1f}%)")
        lines.append(f"- 期待Place ROI: {best['mean_place_roi']:.1f}% (±{best['std_place_roi']:.1f}%)")
        lines.append(f"- 安定性スコア: {best['stability_score']:.3f}")
        
        lines.append("\n## 3. 感度分析")
        lines.append("\n各パラメータを ±0.2 変化させた場合のROI変動:")
        
        for param_name, df in sensitivity_results.items():
            lines.append(f"\n### {param_name}")
            lines.append(f"\n| Delta | Value | Win ROI | Place ROI |")
            lines.append(f"|-------|-------|---------|-----------|")
            for _, row in df.iterrows():
                lines.append(f"| {row['delta']:+.2f} | {row['value']:.2f} | "
                            f"{row['win_roi']:.1f}% | {row['place_roi']:.1f}% |")
        
        lines.append("\n## 4. 注意事項")
        lines.append("\n- この結果はシミュレーションデータに基づいています")
        lines.append("- 実際の市場では異なる結果になる可能性があります")
        lines.append("- 安定性スコアが低いパラメータはオーバーフィットのリスクがあります")
        lines.append("- 実運用前に実データでのバックテストを推奨します")
        
        content = "\n".join(lines)
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"\nReport saved to: {output_path}")
        return content


def run_optimization():
    """最適化を実行"""
    print("=" * 70)
    print("=== バイアス係数最適化 ===")
    print("=" * 70)
    
    optimizer = BiasOptimizer()
    
    # 実データがあれば読み込む、なければ合成データを生成
    races = optimizer.load_race_data()
    
    if len(races) < 100:
        print(f"\nInsufficient real data ({len(races)} races). Generating synthetic data...")
        races = optimizer.generate_synthetic_races(n_races=1000)
        print(f"Generated {len(races)} synthetic races")
    
    # 最適パラメータを探索
    print("\n" + "-" * 70)
    optimal = optimizer.find_optimal_params(races, top_n=10, min_bets=30)
    
    print("\n=== 最適パラメータ TOP 10 ===")
    print(optimal[['fav_factor', 'mid_factor', 'long_factor', 'extreme_factor', 
                   'mean_win_roi', 'mean_place_roi', 'stability_score', 'final_score']].to_string())
    
    # 最適パラメータに対する感度分析
    print("\n" + "-" * 70)
    print("=== 感度分析 ===")
    
    best_config = BiasConfig(
        fav_factor=optimal.iloc[0]['fav_factor'],
        mid_factor=optimal.iloc[0]['mid_factor'],
        long_factor=optimal.iloc[0]['long_factor'],
        extreme_factor=optimal.iloc[0]['extreme_factor']
    )
    
    sensitivity_results = {}
    for param in ['fav_factor', 'mid_factor', 'long_factor', 'extreme_factor']:
        print(f"\n{param}:")
        sens = optimizer.sensitivity_analysis(races, best_config, param)
        sensitivity_results[param] = sens
        print(sens[['delta', 'value', 'win_roi', 'place_roi']].to_string(index=False))
    
    # レポート生成
    report = optimizer.generate_report(optimal, sensitivity_results)
    
    print("\n" + "=" * 70)
    print("=== 最終推奨パラメータ ===")
    print("=" * 70)
    best = optimal.iloc[0]
    print(f"""
BiasConfig(
    fav_factor={best['fav_factor']:.2f},   # 人気馬の過大評価補正
    mid_factor={best['mid_factor']:.2f},   # 中位人気
    long_factor={best['long_factor']:.2f},  # 穴馬のプレミアム
    extreme_factor={best['extreme_factor']:.2f}   # 大穴馬
)

期待ROI:
  - 単勝: {best['mean_win_roi']:.1f}% (±{best['std_win_roi']:.1f}%)
  - 複勝: {best['mean_place_roi']:.1f}% (±{best['std_place_roi']:.1f}%)

安定性スコア: {best['stability_score']:.3f}
  (1.0に近いほど安定、オーバーフィットのリスクが低い)
""")
    
    return optimal, sensitivity_results


if __name__ == "__main__":
    run_optimization()
