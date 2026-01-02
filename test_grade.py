from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time

options = Options()
options.add_argument('--headless')
options.add_argument('--no-sandbox')

driver = webdriver.Chrome(options=options)
driver.get('https://race.netkeiba.com/race/shutuba.html?race_id=202608010111')
time.sleep(2)

# RaceData01とRaceData02の内容を取得
try:
    data01 = driver.find_element(By.CSS_SELECTOR, '.RaceData01').text
    print("RaceData01:", data01)
except:
    print("RaceData01 not found")

try:
    data02 = driver.find_element(By.CSS_SELECTOR, '.RaceData02').text
    print("RaceData02:", data02)
except:
    print("RaceData02 not found")

try:
    race_name = driver.find_element(By.CSS_SELECTOR, '.RaceName').text
    print("RaceName:", race_name)
except:
    print("RaceName not found")

# ページタイトルも確認
print("Title:", driver.title)

# HTMLソースの一部を確認
html = driver.page_source
if 'G3' in html or 'GⅢ' in html or 'GIII' in html:
    print("Found G3/GⅢ/GIII in HTML source")
    idx = html.find('G3') if 'G3' in html else html.find('GⅢ') if 'GⅢ' in html else html.find('GIII')
    print("Context:", html[max(0,idx-50):idx+100])
else:
    print("G3/GⅢ/GIII NOT found in HTML source")
    # RaceNameクラス周辺のHTMLを確認
    idx = html.find('RaceName')
    if idx > 0:
        print("RaceName HTML:", html[idx:idx+500])

driver.quit()
