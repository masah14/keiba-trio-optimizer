"""
改良版バックテスト 2023-2025

改良点:
1. Seleniumベースのスクレイパーを使用
2. EVエンジンV2を使用
3. 感度分析を組み込み
4. 詳細なログ出力
5. 中断・再開可能な設計
"""

import os
import sys
import json
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict

# 同一ディレクトリのモジュールをインポート
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scraper_selenium import NetkeibaSeleniumScraper, DataCache, SELENIUM_AVAILABLE
from app.ev_engine_v2 import EVEngineV2, BiasConfig, SensitivityAnalyzer


@dataclass
class BetRecord:
    """賭けの記録"""
    race_id: str
    race_title: str
    horse_num: int
    horse_name: str
    bet_type: str  # 'win' or 'place'
    odds: float
    ev: float
    invested: int
    finish: int
    payout: int
    profit: int


@dataclass
class BacktestResult:
    """バックテスト結果"""
    period: str
    total_races: int
    win_bets: int
    win_hits: int
    win_investment: int
    win_payout: int
    win_roi: float
    place_bets: int
    place_hits: int
    place_investment: int
    place_payout: int
    place_roi: float
    bet_records: List[BetRecord]


class ImprovedBacktester:
    """
    改良版バックテスター
    
    特徴:
    - Seleniumスクレイパーで確実にデータ取得
    - キャッシュ機能で再実行時の高速化
    - 詳細な賭け記録を保存
    - 感度分析で最適パラメータを探索
    """
    
    def __init__(self, 
                 data_dir: str = "data",
                 bet_unit: int = 100,
                 ev_threshold: float = 1.0):
        """
        Args:
            data_dir: データ保存ディレクトリ
            bet_unit: 1口の賭け金（円）
            ev_threshold: 賭ける期待値の閾値
        """
        self.data_dir = data_dir
        self.bet_unit = bet_unit
        self.ev_threshold = ev_threshold
        
        os.makedirs(data_dir, exist_ok=True)
        
        self.scraper = None
        self.cache = DataCache(os.path.join(data_dir, "cache"))
        self.engine = EVEngineV2()
        
    def _init_scraper(self):
        """スクレイパーを初期化"""
        if self.scraper is None:
            if not SELENIUM_AVAILABLE:
                raise ImportError("Selenium is required. Install with: pip install selenium")
            self.scraper = NetkeibaSeleniumScraper(headless=True, wait_time=2.0)
            
    def _close_scraper(self):
        """スクレイパーを閉じる"""
        if self.scraper:
            self.scraper.close()
            self.scraper = None
    
    def get_race_ids(self, year: int, month: int, use_cache: bool = True) -> List[str]:
        """
        レースID一覧を取得（キャッシュ優先）
        """
        if use_cache:
            cached = self.cache.get_cached_race_ids(year, month)
            if cached:
                print(f"  Using cached race IDs for {year}/{month}: {len(cached)} races")
                return cached
        
        self._init_scraper()
        race_ids = self.scraper.get_race_ids_for_month(year, month)
        
        if race_ids:
            self.cache.cache_race_ids(year, month, race_ids)
            
        return race_ids
    
    def get_race_data(self, race_id: str, use_cache: bool = True) -> Optional[Dict]:
        """
        レースデータを取得（キャッシュ優先）
        """
        if use_cache:
            cached = self.cache.get_cached_race(race_id)
            if cached:
                return cached
        
        self._init_scraper()
        result = self.scraper.get_race_result(race_id)
        
        if result:
            data = {
                'race_id': result.race_id,
                'title': result.title,
                'date': result.date,
                'horses': result.horses,
                'payouts': result.payouts
            }
            self.cache.cache_race(race_id, data)
            return data
        
        return None
    
    def evaluate_race(self, race_data: Dict) -> Tuple[List[BetRecord], Dict]:
        """
        1レースを評価して賭け記録を生成
        
        Returns:
            (賭け記録リスト, 集計)
        """
        records = []
        stats = {
            'win_bets': 0, 'win_hits': 0, 'win_investment': 0, 'win_payout': 0,
            'place_bets': 0, 'place_hits': 0, 'place_investment': 0, 'place_payout': 0
        }
        
        horses = race_data.get('horses', [])
        if not horses or len(horses) < 2:
            return records, stats
        
        # EVを計算
        calculated = self.engine.calculate_ev(horses.copy())
        
        payouts = race_data.get('payouts', {'win': {}, 'place': {}})
        
        for h in calculated:
            num = h['num']
            finish = h.get('finish', 0)
            
            # 単勝
            if h.get('win_ev', 0) >= self.ev_threshold:
                stats['win_bets'] += 1
                stats['win_investment'] += self.bet_unit
                
                payout = 0
                if finish == 1:
                    stats['win_hits'] += 1
                    payout = payouts.get('win', {}).get(num, 0)
                    stats['win_payout'] += payout
                
                records.append(BetRecord(
                    race_id=race_data['race_id'],
                    race_title=race_data.get('title', ''),
                    horse_num=num,
                    horse_name=h.get('name', ''),
                    bet_type='win',
                    odds=h.get('odds', 0),
                    ev=h.get('win_ev', 0),
                    invested=self.bet_unit,
                    finish=finish,
                    payout=payout,
                    profit=payout - self.bet_unit
                ))
            
            # 複勝
            if h.get('place_ev', 0) >= self.ev_threshold:
                stats['place_bets'] += 1
                stats['place_investment'] += self.bet_unit
                
                payout = 0
                if finish <= 3:
                    stats['place_hits'] += 1
                    payout = payouts.get('place', {}).get(num, 0)
                    stats['place_payout'] += payout
                
                records.append(BetRecord(
                    race_id=race_data['race_id'],
                    race_title=race_data.get('title', ''),
                    horse_num=num,
                    horse_name=h.get('name', ''),
                    bet_type='place',
                    odds=h.get('odds', 0),
                    ev=h.get('place_ev', 0),
                    invested=self.bet_unit,
                    finish=finish,
                    payout=payout,
                    profit=payout - self.bet_unit
                ))
        
        return records, stats
    
    def run(self, start_year: int = 2023, end_year: int = 2025,
            start_month: int = 1, end_month: int = 12,
            max_races_per_month: int = None) -> BacktestResult:
        """
        バックテストを実行
        
        Args:
            start_year: 開始年
            end_year: 終了年
            start_month: 開始月（start_year用）
            end_month: 終了月（end_year用）
            max_races_per_month: 月あたりの最大レース数（デバッグ用）
        """
        print("=" * 70)
        print(f"=== 改良版バックテスト: {start_year}年{start_month}月 〜 {end_year}年{end_month}月 ===")
        print("=" * 70)
        print(f"EV閾値: {self.ev_threshold}, 賭け単位: {self.bet_unit}円")
        print()
        
        all_records = []
        total_stats = {
            'win_bets': 0, 'win_hits': 0, 'win_investment': 0, 'win_payout': 0,
            'place_bets': 0, 'place_hits': 0, 'place_investment': 0, 'place_payout': 0
        }
        total_races = 0
        
        try:
            for year in range(start_year, end_year + 1):
                year_stats = {
                    'win_bets': 0, 'win_hits': 0, 'win_investment': 0, 'win_payout': 0,
                    'place_bets': 0, 'place_hits': 0, 'place_investment': 0, 'place_payout': 0
                }
                year_races = 0
                
                month_start = start_month if year == start_year else 1
                month_end = end_month if year == end_year else 12
                
                for month in range(month_start, month_end + 1):
                    # 未来の月はスキップ
                    now = datetime.now()
                    if datetime(year, month, 1) > now:
                        continue
                    
                    print(f"\n--- {year}年{month}月 ---")
                    
                    race_ids = self.get_race_ids(year, month)
                    print(f"  レース数: {len(race_ids)}")
                    
                    if max_races_per_month:
                        race_ids = race_ids[:max_races_per_month]
                    
                    month_races = 0
                    
                    for i, race_id in enumerate(race_ids):
                        race_data = self.get_race_data(race_id)
                        if not race_data:
                            continue
                        
                        records, stats = self.evaluate_race(race_data)
                        
                        all_records.extend(records)
                        month_races += 1
                        
                        for key in stats:
                            year_stats[key] += stats[key]
                            total_stats[key] += stats[key]
                        
                        if (i + 1) % 20 == 0:
                            print(f"    処理中: {i+1}/{len(race_ids)}")
                    
                    year_races += month_races
                    print(f"  処理完了: {month_races}レース")
                
                total_races += year_races
                
                # 年次サマリー
                print(f"\n=== {year}年 年間サマリー ===")
                print(f"  処理レース数: {year_races}")
                
                for bet_type, name in [('win', '単勝'), ('place', '複勝')]:
                    bets = year_stats[f'{bet_type}_bets']
                    hits = year_stats[f'{bet_type}_hits']
                    invest = year_stats[f'{bet_type}_investment']
                    payout = year_stats[f'{bet_type}_payout']
                    
                    if invest > 0:
                        roi = (payout / invest) * 100
                        hit_rate = (hits / bets) * 100 if bets > 0 else 0
                        profit = payout - invest
                        print(f"  {name}: {bets}件, 的中{hits}件 ({hit_rate:.1f}%), "
                              f"ROI {roi:.1f}%, 損益 {profit:+,}円")
                
        finally:
            self._close_scraper()
        
        # 最終結果
        print("\n" + "=" * 70)
        print("=== バックテスト最終結果 ===")
        print("=" * 70)
        print(f"期間: {start_year}年{start_month}月 〜 {end_year}年{end_month}月")
        print(f"処理レース数: {total_races:,}")
        print()
        
        results = {}
        
        for bet_type, name in [('win', '単勝'), ('place', '複勝')]:
            bets = total_stats[f'{bet_type}_bets']
            hits = total_stats[f'{bet_type}_hits']
            invest = total_stats[f'{bet_type}_investment']
            payout = total_stats[f'{bet_type}_payout']
            
            roi = (payout / invest * 100) if invest > 0 else 0
            hit_rate = (hits / bets * 100) if bets > 0 else 0
            profit = payout - invest
            
            results[bet_type] = {
                'bets': bets, 'hits': hits, 'investment': invest,
                'payout': payout, 'roi': roi, 'hit_rate': hit_rate, 'profit': profit
            }
            
            print(f"\n【{name}】(EV >= {self.ev_threshold})")
            print(f"  総ベット数: {bets:,}件")
            print(f"  的中数: {hits:,}件")
            print(f"  的中率: {hit_rate:.2f}%")
            print(f"  総投資額: {invest:,}円")
            print(f"  総払戻額: {payout:,}円")
            print(f"  純利益: {profit:+,}円")
            print(f"  ROI: {roi:.1f}%")
        
        # 結果を保存
        result = BacktestResult(
            period=f"{start_year}-{end_year}",
            total_races=total_races,
            win_bets=results['win']['bets'],
            win_hits=results['win']['hits'],
            win_investment=results['win']['investment'],
            win_payout=results['win']['payout'],
            win_roi=results['win']['roi'],
            place_bets=results['place']['bets'],
            place_hits=results['place']['hits'],
            place_investment=results['place']['investment'],
            place_payout=results['place']['payout'],
            place_roi=results['place']['roi'],
            bet_records=all_records
        )
        
        self._save_results(result)
        
        return result
    
    def _save_results(self, result: BacktestResult):
        """結果をファイルに保存"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # サマリーを保存
        summary_path = os.path.join(self.data_dir, f"backtest_summary_{timestamp}.json")
        summary = {
            'period': result.period,
            'total_races': result.total_races,
            'ev_threshold': self.ev_threshold,
            'bet_unit': self.bet_unit,
            'win': {
                'bets': result.win_bets,
                'hits': result.win_hits,
                'investment': result.win_investment,
                'payout': result.win_payout,
                'roi': result.win_roi
            },
            'place': {
                'bets': result.place_bets,
                'hits': result.place_hits,
                'investment': result.place_investment,
                'payout': result.place_payout,
                'roi': result.place_roi
            },
            'timestamp': timestamp
        }
        
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        
        # 詳細記録を保存
        records_path = os.path.join(self.data_dir, f"backtest_records_{timestamp}.json")
        records = [asdict(r) for r in result.bet_records]
        
        with open(records_path, 'w', encoding='utf-8') as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        
        print(f"\n結果を保存しました:")
        print(f"  サマリー: {summary_path}")
        print(f"  詳細記録: {records_path}")


def run_sensitivity_analysis():
    """
    感度分析を実行
    - バイアス係数を変動させてROIへの影響を調べる
    """
    print("=" * 70)
    print("=== 感度分析 ===")
    print("=" * 70)
    
    # サンプルデータで分析（実際のバックテストは時間がかかるため）
    sample_horses = [
        {'num': 1, 'name': 'A', 'odds': 2.5, 'popularity': 1},
        {'num': 2, 'name': 'B', 'odds': 5.0, 'popularity': 2},
        {'num': 3, 'name': 'C', 'odds': 12.0, 'popularity': 3},
        {'num': 4, 'name': 'D', 'odds': 25.0, 'popularity': 4},
        {'num': 5, 'name': 'E', 'odds': 80.0, 'popularity': 5},
    ]
    
    params = ['fav_factor', 'mid_factor', 'long_factor', 'extreme_factor']
    
    for param in params:
        print(f"\n--- {param} の感度分析 ---")
        
        if 'fav' in param:
            values = [0.7, 0.8, 0.85, 0.9, 1.0]
        else:
            values = [1.0, 1.2, 1.4, 1.6, 1.8]
        
        result = SensitivityAnalyzer.analyze_bias_sensitivity(
            sample_horses, param, values
        )
        print(result.to_string(index=False))


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='改良版バックテスト')
    parser.add_argument('--start-year', type=int, default=2024, help='開始年')
    parser.add_argument('--end-year', type=int, default=2024, help='終了年')
    parser.add_argument('--start-month', type=int, default=1, help='開始月')
    parser.add_argument('--end-month', type=int, default=12, help='終了月')
    parser.add_argument('--ev-threshold', type=float, default=1.0, help='EV閾値')
    parser.add_argument('--max-races', type=int, default=None, help='月あたり最大レース数')
    parser.add_argument('--sensitivity', action='store_true', help='感度分析のみ実行')
    
    args = parser.parse_args()
    
    if args.sensitivity:
        run_sensitivity_analysis()
    else:
        backtester = ImprovedBacktester(ev_threshold=args.ev_threshold)
        backtester.run(
            start_year=args.start_year,
            end_year=args.end_year,
            start_month=args.start_month,
            end_month=args.end_month,
            max_races_per_month=args.max_races
        )
