import os
import datetime
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# 환경 변수
USER_ID = os.environ.get('USER_ID')
USER_PW = os.environ.get('USER_PW')

if not USER_ID or not USER_PW:
    print("❌ USER_ID 또는 USER_PW 환경 변수가 설정되지 않았습니다.")
    exit(1)

def get_kst():
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=9)).strftime('%Y-%m-%d %H:%M:%S')

def log_to_readme(message):
    try:
        with open("README.md", "a", encoding="utf-8") as f:
            f.write(f"- {get_kst()} | {message}\n")
        print(f"📝 리드미 기록 완료: {message}")
    except Exception as e:
        print(f"📝 리드미 기록 실패: {e}")

# 브라우저 옵션
options = Options()
options.add_argument("--headless")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36")

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
wait = WebDriverWait(driver, 20)

try:
    print(f"📅 실행 시작: {get_kst()}")
    driver.get("https://evergreenjb.me/")
    time.sleep(3)

    # 로그인
    try:
        print("📌 로그인 시도")
        id_input = wait.until(EC.presence_of_element_located((By.NAME, "user_id")))
        pw_input = driver.find_element(By.NAME, "password")
        driver.execute_script("arguments[0].value = arguments[1];", id_input, USER_ID)
        driver.execute_script("arguments[0].value = arguments[1];", pw_input, USER_PW)
        pw_input.send_keys(Keys.ENTER)
        time.sleep(5)

        if "로그아웃" not in driver.page_source:
            log_to_readme("🚨 로그인 실패")
            print("❌ 로그인 실패")
            exit(1)
        else:
            print("✅ 로그인 성공")
    except Exception as e:
        print(f"ℹ️ 로그인 창 없음 또는 이미 로그인됨: {e}")

    # 출석 페이지 이동
    print("📌 출석 페이지 접근")
    driver.get("https://evergreenjb.me/attendance")
    time.sleep(3)

    # 출석 버튼 클릭
    try:
        att_btn = wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//button[contains(text(),'출석') or contains(@class,'attendance')]")
        ))
        driver.execute_script("arguments[0].click();", att_btn)
        time.sleep(2)
        log_to_readme("✅ 출석 체크 성공")
        print("✅ 출석 체크 완료")
    except Exception as e:
        log_to_readme(f"ℹ️ 출석 버튼 없음 또는 클릭 실패: {e}")
        print(f"ℹ️ 출석 버튼 없음 또는 클릭 실패: {e}")

except Exception as e:
    log_to_readme(f"🚨 시스템 에러 발생: {e}")
    print(f"❌ 에러 상세: {e}")

finally:
    driver.quit()
