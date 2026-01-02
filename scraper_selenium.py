"""
Selenium ベースのNetkeibaスクレイパー

改良点:
1. requests の代わりに Selenium を使用してアンチスクレイピング対策を回避
2. 動的に生成されるコンテンツも取得可能
3. リトライとエラーハンドリングを強化
4. レート制限を考慮した待機処理
"""

import time
import re
import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    print("Warning: Selenium not installed. Run: pip install selenium")


@dataclass
class RaceResult:
    """レース結果のデータ構造"""
    race_id: str
    title: str
    date: str
    course: str
    horses: List[Dict]
    payouts: Dict


class NetkeibaSeleniumScraper:
    """
    Seleniumを使用したNetkeibaスクレイパー
    
    使用方法:
        scraper = NetkeibaSeleniumScraper()
        race_ids = scraper.get_race_ids_for_date('20251228')
        for race_id in race_ids:
            result = scraper.get_race_result(race_id)
    """
    
    def __init__(self, headless: bool = True, wait_time: float = 1.5):
        """
        Args:
            headless: ヘッドレスモードで実行するか
            wait_time: リクエスト間の待機秒数
        """
        if not SELENIUM_AVAILABLE:
            raise ImportError("Selenium is required. Install with: pip install selenium")
        
        self.wait_time = wait_time
        self.driver = None
        self.headless = headless
        
    def _init_driver(self):
        """WebDriverを初期化"""
        if self.driver is not None:
            return
            
        options = Options()
        if self.headless:
            options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        # 画像の読み込みを無効化（高速化）
        prefs = {
            'profile.managed_default_content_settings.images': 2,
        }
        options.add_experimental_option('prefs', prefs)
        
        self.driver = webdriver.Chrome(options=options)
        self.driver.set_page_load_timeout(30)
        
    def _wait(self):
        """リクエスト間の待機"""
        time.sleep(self.wait_time)
        
    def close(self):
        """ブラウザを閉じる"""
        if self.driver:
            self.driver.quit()
            self.driver = None
            
    def get_race_ids_for_date(self, date_str: str) -> List[str]:
        """
        指定日のレースID一覧を取得
        
        Args:
            date_str: 日付 (YYYYMMDD形式)
            
        Returns:
            race_idのリスト（12桁）
        """
        self._init_driver()
        race_ids = []
        
        url = f"https://race.netkeiba.com/top/race_list.html?kaisai_date={date_str}"
        
        try:
            self.driver.get(url)
            self._wait()
            
            # レースリンクを探す
            links = self.driver.find_elements(By.CSS_SELECTOR, 'a[href*="race_id="]')
            
            for link in links:
                href = link.get_attribute('href')
                if href:
                    match = re.search(r'race_id=(\d{12})', href)
                    if match:
                        race_ids.append(match.group(1))
            
            race_ids = list(set(race_ids))  # 重複除去
            
        except Exception as e:
            print(f"Error fetching race list for {date_str}: {e}")
            
        return sorted(race_ids)
    
    def get_race_ids_for_month(self, year: int, month: int) -> List[str]:
        """
        指定月のレースID一覧を取得（週末のみ）
        
        Args:
            year: 年
            month: 月
            
        Returns:
            race_idのリスト
        """
        race_ids = []
        
        # 月の日数を計算
        if month == 12:
            next_month = datetime(year + 1, 1, 1)
        else:
            next_month = datetime(year, month + 1, 1)
        first_day = datetime(year, month, 1)
        days_in_month = (next_month - first_day).days
        
        for day in range(1, days_in_month + 1):
            date = datetime(year, month, day)
            # 土曜(5)か日曜(6)のみ
            if date.weekday() in [5, 6]:
                date_str = date.strftime('%Y%m%d')
                print(f"  Fetching races for {date_str}...")
                ids = self.get_race_ids_for_date(date_str)
                race_ids.extend(ids)
                print(f"    Found {len(ids)} races")
        
        return race_ids
    
    def get_race_result(self, race_id: str) -> Optional[RaceResult]:
        """
        レース結果を取得
        
        Args:
            race_id: 12桁のレースID
            
        Returns:
            RaceResultオブジェクト
        """
        self._init_driver()
        
        url = f"https://db.netkeiba.com/race/{race_id}/"
        
        try:
            self.driver.get(url)
            self._wait()
            
            # レースタイトル
            title = ""
            try:
                title_elem = self.driver.find_element(By.CSS_SELECTOR, 'h1')
                title = title_elem.text.strip()
            except NoSuchElementException:
                pass
            
            # 日付・コース情報
            date_str = ""
            course = ""
            try:
                info_elem = self.driver.find_element(By.CSS_SELECTOR, '.data_intro p')
                info_text = info_elem.text
                # 日付を抽出
                date_match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', info_text)
                if date_match:
                    date_str = f"{date_match.group(1)}{int(date_match.group(2)):02d}{int(date_match.group(3)):02d}"
            except NoSuchElementException:
                pass
            
            # 結果テーブル
            horses = []
            try:
                result_table = self.driver.find_element(By.CSS_SELECTOR, 'table.race_table_01')
                rows = result_table.find_elements(By.CSS_SELECTOR, 'tr')[1:]  # ヘッダー除く
                
                for row in rows:
                    cols = row.find_elements(By.CSS_SELECTOR, 'td')
                    if len(cols) < 13:
                        continue
                    
                    try:
                        # 着順
                        finish_text = cols[0].text.strip()
                        if not finish_text.isdigit():
                            continue
                        finish = int(finish_text)
                        
                        # 馬番
                        num_text = cols[2].text.strip()
                        if not num_text.isdigit():
                            continue
                        num = int(num_text)
                        
                        # 馬名
                        horse_name = ""
                        try:
                            name_elem = cols[3].find_element(By.CSS_SELECTOR, 'a')
                            horse_name = name_elem.text.strip()
                        except NoSuchElementException:
                            horse_name = cols[3].text.strip()
                        
                        # 騎手
                        jockey_name = ""
                        try:
                            jockey_elem = cols[6].find_element(By.CSS_SELECTOR, 'a')
                            jockey_name = jockey_elem.text.strip()
                        except NoSuchElementException:
                            pass
                        
                        # 単勝オッズ（複数列を試行）
                        odds = 0.0
                        for idx in [12, 11, 10]:
                            if idx < len(cols):
                                odds_text = cols[idx].text.strip()
                                try:
                                    odds = float(odds_text)
                                    if odds > 0:
                                        break
                                except ValueError:
                                    continue
                        
                        if odds <= 0:
                            continue
                        
                        # 人気
                        popularity = 0
                        for idx in [13, 12, 11]:
                            if idx < len(cols):
                                pop_text = cols[idx].text.strip()
                                if pop_text.isdigit():
                                    popularity = int(pop_text)
                                    break
                        
                        horses.append({
                            'num': num,
                            'name': horse_name,
                            'jockey': jockey_name,
                            'odds': odds,
                            'popularity': popularity,
                            'finish': finish
                        })
                        
                    except Exception as e:
                        continue
                        
            except NoSuchElementException:
                return None
            
            if len(horses) < 2:
                return None
            
            # 払戻金
            payouts = self._get_payouts()
            
            return RaceResult(
                race_id=race_id,
                title=title,
                date=date_str,
                course=course,
                horses=horses,
                payouts=payouts
            )
            
        except Exception as e:
            print(f"Error fetching race {race_id}: {e}")
            return None
    
    def _get_payouts(self) -> Dict:
        """払戻金テーブルを解析"""
        payouts = {'win': {}, 'place': {}, 'trifecta': {}}
        
        try:
            tables = self.driver.find_elements(By.CSS_SELECTOR, 'table.pay_table_01')
            
            for table in tables:
                rows = table.find_elements(By.CSS_SELECTOR, 'tr')
                
                for row in rows:
                    try:
                        header = row.find_element(By.CSS_SELECTOR, 'th')
                        header_text = header.text.strip()
                        cols = row.find_elements(By.CSS_SELECTOR, 'td')
                        
                        if '単勝' in header_text and len(cols) >= 2:
                            num_text = cols[0].text.strip()
                            pay_text = cols[1].text.strip().replace(',', '').replace('円', '')
                            
                            nums = re.findall(r'\d+', num_text)
                            pays = re.findall(r'\d+', pay_text)
                            
                            for i, num in enumerate(nums):
                                if i < len(pays):
                                    payouts['win'][int(num)] = int(pays[i])
                        
                        elif '複勝' in header_text and len(cols) >= 2:
                            num_text = cols[0].text.strip()
                            pay_text = cols[1].text.strip().replace(',', '').replace('円', '')
                            
                            nums = re.findall(r'\d+', num_text)
                            pays = re.findall(r'\d+', pay_text)
                            
                            for i, num in enumerate(nums):
                                if i < len(pays):
                                    payouts['place'][int(num)] = int(pays[i])
                        
                        elif '3連単' in header_text and len(cols) >= 2:
                            comb_text = cols[0].text.strip()
                            pay_text = cols[1].text.strip().replace(',', '').replace('円', '')
                            
                            # 組み合わせと払戻を紐付け
                            match = re.search(r'(\d+)\s*[→-]\s*(\d+)\s*[→-]\s*(\d+)', comb_text)
                            pay_match = re.search(r'(\d+)', pay_text)
                            if match and pay_match:
                                key = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
                                payouts['trifecta'][key] = int(pay_match.group(1))
                                
                    except NoSuchElementException:
                        continue
                        
        except Exception as e:
            print(f"Error parsing payouts: {e}")
            
        return payouts


class DataCache:
    """スクレイピング結果のキャッシュ管理"""
    
    def __init__(self, cache_dir: str = "data/cache"):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        
    def get_cached_race(self, race_id: str) -> Optional[Dict]:
        """キャッシュからレース結果を取得"""
        filepath = os.path.join(self.cache_dir, f"race_{race_id}.json")
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None
    
    def cache_race(self, race_id: str, data: Dict):
        """レース結果をキャッシュに保存"""
        filepath = os.path.join(self.cache_dir, f"race_{race_id}.json")
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
    def get_cached_race_ids(self, year: int, month: int) -> Optional[List[str]]:
        """キャッシュからレースID一覧を取得"""
        filepath = os.path.join(self.cache_dir, f"race_ids_{year}_{month:02d}.json")
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None
    
    def cache_race_ids(self, year: int, month: int, race_ids: List[str]):
        """レースID一覧をキャッシュに保存"""
        filepath = os.path.join(self.cache_dir, f"race_ids_{year}_{month:02d}.json")
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(race_ids, f, ensure_ascii=False)


# 使用例
if __name__ == "__main__":
    print("=== Netkeiba Selenium Scraper ===")
    
    if not SELENIUM_AVAILABLE:
        print("Selenium not available. Install with: pip install selenium")
        exit(1)
    
    scraper = NetkeibaSeleniumScraper(headless=True)
    cache = DataCache()
    
    try:
        # 2025年12月28日（有馬記念の日）のレースを取得
        date = "20251228"
        print(f"\nFetching races for {date}...")
        
        race_ids = scraper.get_race_ids_for_date(date)
        print(f"Found {len(race_ids)} races")
        
        if race_ids:
            # 最初のレースの詳細を取得
            race_id = race_ids[0]
            print(f"\nFetching details for race {race_id}...")
            
            result = scraper.get_race_result(race_id)
            if result:
                print(f"Title: {result.title}")
                print(f"Horses: {len(result.horses)}")
                for h in result.horses[:3]:
                    print(f"  {h['num']}. {h['name']} - Finish: {h['finish']}, Odds: {h['odds']}")
                    
    finally:
        scraper.close()
