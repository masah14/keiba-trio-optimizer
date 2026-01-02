"""
拡張スクレイパー - 馬・騎手の詳細情報を取得

取得する情報:
1. 馬の過去5走成績
2. コース・距離適性（該当コースでの成績）
3. 騎手の年間/コース別勝率
4. 前走からの体重変化
5. 調教評価（可能であれば）
"""

import time
import re
import json
import os
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False


@dataclass
class HorseProfile:
    """馬の詳細プロファイル"""
    horse_id: str
    name: str
    
    # 過去成績
    total_runs: int = 0
    total_wins: int = 0
    total_places: int = 0  # 3着以内
    win_rate: float = 0.0
    place_rate: float = 0.0
    
    # 直近5走
    recent_finishes: List[int] = None  # [1, 3, 2, 5, 1] など
    recent_avg_finish: float = 0.0
    
    # コース適性
    course_runs: int = 0
    course_wins: int = 0
    course_win_rate: float = 0.0
    
    # 距離適性
    distance_runs: int = 0
    distance_wins: int = 0
    distance_win_rate: float = 0.0
    
    def __post_init__(self):
        if self.recent_finishes is None:
            self.recent_finishes = []


@dataclass
class JockeyProfile:
    """騎手のプロファイル"""
    jockey_id: str
    name: str
    
    # 年間成績
    year_runs: int = 0
    year_wins: int = 0
    year_win_rate: float = 0.0
    
    # コース別成績
    course_runs: int = 0
    course_wins: int = 0
    course_win_rate: float = 0.0


class EnhancedScraper:
    """
    拡張版Netkeibaスクレイパー
    
    馬・騎手の詳細情報を取得
    """
    
    def __init__(self, headless: bool = True, wait_time: float = 1.5):
        if not SELENIUM_AVAILABLE:
            raise ImportError("Selenium required")
        
        self.wait_time = wait_time
        self.driver = None
        self.headless = headless
        
        # キャッシュ
        self.horse_cache = {}
        self.jockey_cache = {}
        
    def _init_driver(self):
        if self.driver is not None:
            return
            
        options = Options()
        if self.headless:
            options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
        prefs = {'profile.managed_default_content_settings.images': 2}
        options.add_experimental_option('prefs', prefs)
        
        self.driver = webdriver.Chrome(options=options)
        self.driver.set_page_load_timeout(30)
        
    def close(self):
        if self.driver:
            self.driver.quit()
            self.driver = None
    
    def _wait(self):
        time.sleep(self.wait_time)
    
    def get_horse_profile(self, horse_id: str, target_course: str = None, 
                          target_distance: int = None) -> Optional[HorseProfile]:
        """
        馬の詳細情報を取得
        
        Args:
            horse_id: 馬ID（10桁）
            target_course: 対象コース（"中山", "阪神" など）
            target_distance: 対象距離（2500 など）
        """
        if horse_id in self.horse_cache:
            return self.horse_cache[horse_id]
        
        self._init_driver()
        
        url = f"https://db.netkeiba.com/horse/{horse_id}/"
        
        try:
            self.driver.get(url)
            self._wait()
            
            # 馬名
            name = ""
            try:
                name_elem = self.driver.find_element(By.CSS_SELECTOR, '.horse_title h1')
                name = name_elem.text.strip()
            except NoSuchElementException:
                pass
            
            profile = HorseProfile(horse_id=horse_id, name=name)
            
            # 成績テーブルを取得
            try:
                result_table = self.driver.find_element(By.CSS_SELECTOR, 'table.db_h_race_results')
                rows = result_table.find_elements(By.CSS_SELECTOR, 'tr')[1:]  # ヘッダー除く
                
                recent_finishes = []
                course_wins = 0
                course_runs = 0
                distance_wins = 0
                distance_runs = 0
                
                for i, row in enumerate(rows[:20]):  # 最大20走
                    cols = row.find_elements(By.CSS_SELECTOR, 'td')
                    if len(cols) < 12:
                        continue
                    
                    try:
                        # 着順
                        finish_text = cols[11].text.strip()
                        if finish_text.isdigit():
                            finish = int(finish_text)
                            profile.total_runs += 1
                            
                            if finish == 1:
                                profile.total_wins += 1
                            if finish <= 3:
                                profile.total_places += 1
                            
                            if i < 5:
                                recent_finishes.append(finish)
                        
                        # コース情報
                        course_info = cols[1].text.strip()  # "中山" など
                        
                        # 距離情報
                        distance_text = cols[14].text.strip() if len(cols) > 14 else ""
                        distance_match = re.search(r'(\d+)', distance_text)
                        distance = int(distance_match.group(1)) if distance_match else 0
                        
                        # コース適性チェック
                        if target_course and target_course in course_info:
                            course_runs += 1
                            if finish_text.isdigit() and int(finish_text) == 1:
                                course_wins += 1
                        
                        # 距離適性チェック（±200m）
                        if target_distance and distance:
                            if abs(distance - target_distance) <= 200:
                                distance_runs += 1
                                if finish_text.isdigit() and int(finish_text) == 1:
                                    distance_wins += 1
                                    
                    except Exception:
                        continue
                
                profile.recent_finishes = recent_finishes
                if recent_finishes:
                    profile.recent_avg_finish = sum(recent_finishes) / len(recent_finishes)
                
                if profile.total_runs > 0:
                    profile.win_rate = profile.total_wins / profile.total_runs
                    profile.place_rate = profile.total_places / profile.total_runs
                
                profile.course_runs = course_runs
                profile.course_wins = course_wins
                if course_runs > 0:
                    profile.course_win_rate = course_wins / course_runs
                
                profile.distance_runs = distance_runs
                profile.distance_wins = distance_wins
                if distance_runs > 0:
                    profile.distance_win_rate = distance_wins / distance_runs
                    
            except NoSuchElementException:
                pass
            
            self.horse_cache[horse_id] = profile
            return profile
            
        except Exception as e:
            print(f"Error fetching horse {horse_id}: {e}")
            return None
    
    def get_jockey_profile(self, jockey_id: str, target_course: str = None) -> Optional[JockeyProfile]:
        """
        騎手の詳細情報を取得
        """
        if jockey_id in self.jockey_cache:
            return self.jockey_cache[jockey_id]
        
        self._init_driver()
        
        url = f"https://db.netkeiba.com/jockey/result/recent/{jockey_id}/"
        
        try:
            self.driver.get(url)
            self._wait()
            
            # 騎手名
            name = ""
            try:
                name_elem = self.driver.find_element(By.CSS_SELECTOR, '.Name_L h1')
                name = name_elem.text.strip()
            except NoSuchElementException:
                pass
            
            profile = JockeyProfile(jockey_id=jockey_id, name=name)
            
            # 年間成績を取得
            try:
                # 成績テーブルを探す
                tables = self.driver.find_elements(By.CSS_SELECTOR, 'table.race_table_01')
                for table in tables:
                    header = table.find_element(By.CSS_SELECTOR, 'tr th')
                    if '年度' in header.text or '成績' in header.text:
                        rows = table.find_elements(By.CSS_SELECTOR, 'tr')[1:]
                        if rows:
                            # 最新年度の成績
                            cols = rows[0].find_elements(By.CSS_SELECTOR, 'td')
                            if len(cols) >= 3:
                                try:
                                    wins = int(cols[1].text.strip())
                                    runs = int(cols[0].text.strip())
                                    profile.year_wins = wins
                                    profile.year_runs = runs
                                    if runs > 0:
                                        profile.year_win_rate = wins / runs
                                except ValueError:
                                    pass
                        break
                        
            except NoSuchElementException:
                pass
            
            self.jockey_cache[jockey_id] = profile
            return profile
            
        except Exception as e:
            print(f"Error fetching jockey {jockey_id}: {e}")
            return None
    
    def get_race_enhanced_data(self, race_id: str) -> Optional[Dict]:
        """
        レースの拡張データを取得（馬・騎手の詳細情報込み）
        """
        self._init_driver()
        
        url = f"https://db.netkeiba.com/race/{race_id}/"
        
        try:
            self.driver.get(url)
            self._wait()
            
            # レース情報を取得
            race_info = {}
            
            # コース情報
            try:
                info_elem = self.driver.find_element(By.CSS_SELECTOR, '.data_intro p')
                info_text = info_elem.text
                
                # コース名抽出
                course_match = re.search(r'(札幌|函館|福島|新潟|東京|中山|中京|京都|阪神|小倉)', info_text)
                if course_match:
                    race_info['course'] = course_match.group(1)
                
                # 距離抽出
                distance_match = re.search(r'(\d{4})m', info_text)
                if distance_match:
                    race_info['distance'] = int(distance_match.group(1))
                    
            except NoSuchElementException:
                pass
            
            # 出走馬情報
            horses = []
            
            try:
                result_table = self.driver.find_element(By.CSS_SELECTOR, 'table.race_table_01')
                rows = result_table.find_elements(By.CSS_SELECTOR, 'tr')[1:]
                
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
                        
                        # 馬名・ID
                        horse_link = cols[3].find_element(By.CSS_SELECTOR, 'a')
                        horse_name = horse_link.text.strip()
                        horse_href = horse_link.get_attribute('href')
                        horse_id = re.search(r'/horse/(\d+)', horse_href).group(1) if horse_href else ""
                        
                        # 騎手名・ID
                        jockey_link = cols[6].find_element(By.CSS_SELECTOR, 'a')
                        jockey_name = jockey_link.text.strip()
                        jockey_href = jockey_link.get_attribute('href')
                        # URL例: /jockey/result/recent/05386/ または /jockey/05386/
                        jockey_match = re.search(r'/jockey/(?:result/recent/)?(\d+)', jockey_href)
                        jockey_id = jockey_match.group(1) if jockey_match else ""
                        
                        # オッズ
                        odds = 0.0
                        for idx in [12, 11, 10]:
                            if idx < len(cols):
                                try:
                                    odds = float(cols[idx].text.strip())
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
                            'horse_id': horse_id,
                            'jockey': jockey_name,
                            'jockey_id': jockey_id,
                            'odds': odds,
                            'popularity': popularity,
                            'finish': finish
                        })
                        
                    except Exception:
                        continue
                        
            except NoSuchElementException:
                return None
            
            if len(horses) < 2:
                return None
            
            # 各馬の詳細情報を取得
            target_course = race_info.get('course')
            target_distance = race_info.get('distance')
            
            for h in horses:
                if h['horse_id']:
                    horse_profile = self.get_horse_profile(
                        h['horse_id'], 
                        target_course=target_course,
                        target_distance=target_distance
                    )
                    if horse_profile:
                        h['horse_profile'] = asdict(horse_profile)
                
                if h['jockey_id']:
                    jockey_profile = self.get_jockey_profile(
                        h['jockey_id'],
                        target_course=target_course
                    )
                    if jockey_profile:
                        h['jockey_profile'] = asdict(jockey_profile)
            
            # 払戻金
            payouts = self._get_payouts()
            
            return {
                'race_id': race_id,
                'race_info': race_info,
                'horses': horses,
                'payouts': payouts
            }
            
        except Exception as e:
            print(f"Error fetching race {race_id}: {e}")
            return None
    
    def _get_payouts(self) -> Dict:
        """払戻金を取得"""
        payouts = {'win': {}, 'place': {}}
        
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
                                    
                    except NoSuchElementException:
                        continue
                        
        except Exception:
            pass
            
        return payouts


def save_enhanced_cache(race_id: str, data: Dict, cache_dir: str = "data/enhanced_cache"):
    """拡張データをキャッシュに保存"""
    os.makedirs(cache_dir, exist_ok=True)
    filepath = os.path.join(cache_dir, f"race_{race_id}_enhanced.json")
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_enhanced_cache(race_id: str, cache_dir: str = "data/enhanced_cache") -> Optional[Dict]:
    """拡張データをキャッシュから読み込み"""
    filepath = os.path.join(cache_dir, f"race_{race_id}_enhanced.json")
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


if __name__ == "__main__":
    print("=== Enhanced Scraper Test ===", flush=True)
    
    scraper = EnhancedScraper(headless=True, wait_time=2.0)
    
    try:
        # テスト: 有馬記念2024のレースID
        test_race_id = "202406050811"  # 2024年有馬記念
        
        print(f"\nFetching enhanced data for race {test_race_id}...", flush=True)
        
        data = scraper.get_race_enhanced_data(test_race_id)
        
        if data:
            print(f"\nRace info: {data['race_info']}")
            print(f"Horses: {len(data['horses'])}")
            
            for h in data['horses'][:3]:
                print(f"\n{h['num']}. {h['name']} (Odds: {h['odds']})")
                if 'horse_profile' in h:
                    hp = h['horse_profile']
                    print(f"   Win Rate: {hp['win_rate']:.1%}, Place Rate: {hp['place_rate']:.1%}")
                    print(f"   Recent: {hp['recent_finishes']}")
                if 'jockey_profile' in h:
                    jp = h['jockey_profile']
                    print(f"   Jockey Win Rate: {jp['year_win_rate']:.1%}")
            
            save_enhanced_cache(test_race_id, data)
            print(f"\nSaved to cache.")
        else:
            print("Failed to fetch data")
            
    finally:
        scraper.close()
