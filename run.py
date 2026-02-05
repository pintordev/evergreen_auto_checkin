import time
import os
import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# 환경 변수 설정
USER_ID = os.environ.get('USER_ID')
USER_PW = os.environ.get('USER_PW')

def get_kst():
    # 한국 시간 생성
    return (datetime.datetime.now() + datetime.timedelta(hours=9)).strftime('%Y-%m-%d %H:%M:%S')

def log_to_readme(message):
    try:
        # 다시 README.md에 기록하도록 수정했습니다.
        with open("README.md", "a", encoding="utf-8") as f:
            f.write(f"- {get_kst()} | {message}\n")
        print(f"📝 리드미 기록 완료: {message}")
    except Exception as e:
        print(f"📝 리드미 기록 실패: {e}")

# 브라우저 설정
options = Options()
options.add_argument("--headless")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36")

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
wait = WebDriverWait(driver, 15)

try:
    print(f"📅 실행 시작: {get_kst()}")
    driver.get("https://evergreenjb.me/")
    time.sleep(5)

    # 1. 로그인
    try:
        id_input = wait.until(EC.presence_of_element_located((By.NAME, "user_id")))
        pw_input = driver.find_element(By.NAME, "password")
        driver.execute_script("arguments[0].value = arguments[1];", id_input, USER_ID)
        driver.execute_script("arguments[0].value = arguments[1];", pw_input, USER_PW)
        pw_input.send_keys(Keys.ENTER)
        time.sleep(5)
    except:
        print("ℹ️ 로그인 창이 없거나 이미 로그인된 상태입니다.")

    # 2. 출석 체크
    driver.get("https://evergreenjb.me/attendance")
    time.sleep(5)

    try:
        # 버튼 찾기 강화
        att_btn = driver.find_element(By.XPATH, "//*[contains(text(), '출석')]")
        driver.execute_script("arguments[0].click();", att_btn)
        time.sleep(2)
        driver.switch_to.active_element.send_keys(Keys.ENTER)
        log_to_readme("✅ 출석 체크 성공")
    except:
        log_to_readme("ℹ️ 출석 버튼 없음 (이미 완료 가능성)")

except Exception as e:
    log_to_readme("🚨 시스템 에러 발생")
    print(f"❌ 에러 상세: {e}")
finally:
    if 'driver' in locals():
        driver.quit()
