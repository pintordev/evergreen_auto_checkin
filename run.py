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

# 환경 변수에서 가져오기
USER_ID = os.environ.get('USER_ID')
USER_PW = os.environ.get('USER_PW')

def get_kst():
    return (datetime.datetime.now() + datetime.timedelta(hours=9)).strftime('%Y-%m-%d %H:%M:%S')

def log_to_readme(message):
    try:
        with open("README.md", "a", encoding="utf-8") as f:
            # 아이디 노출 없이 시간과 결과만 기록
            f.write(f"- {get_kst()} | {message}\n")
        print(f"📝 로그 기록 완료: {message}")
    except Exception as e:
        print(f"📝 로그 기록 실패: {e}")

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

    # 1. 로그인 시도
    try:
        id_input = wait.until(EC.presence_of_element_located((By.NAME, "user_id")))
        pw_input = driver.find_element(By.NAME, "password")
        
        driver.execute_script("arguments[0].value = arguments[1];", id_input, USER_ID)
        driver.execute_script("arguments[0].value = arguments[1];", pw_input, USER_PW)
        pw_input.send_keys(Keys.ENTER)
        time.sleep(5)
        print("✅ 로그인 정보 전송 완료")
    except:
        print("ℹ️ 로그인 창을 찾을 수 없거나 이미 로그인된 상태입니다.")

    # 2. 출석 페이지 이동 및 버튼 클릭
    driver.get("https://evergreenjb.me/attendance")
    time.sleep(5)

    try:
        # '출석' 텍스트를 포함한 버튼 클릭
        att_btn = driver.find_element(By.XPATH, "//*[contains(text(), '출석')]")
        driver.execute_script("arguments[0].click();", att_btn)
        time.sleep(2)
        driver.switch_to.active_element.send_keys(Keys.ENTER) # 팝업 확인
        log_to_readme("✅ 출석 체크 성공")
    except:
        log_to_readme("ℹ️ 출석 버튼 없음 (이미 완료되었거나 페이지 오류)")

except Exception as e:
    # 에러 메시지를 변수에 먼저 담아서 안전하게 처리했습니다.
    error_msg = str(e)[:30]
    log_to_readme(f"🚨 시스템 에러: {error_msg}")
    print(f"❌ 에러 발생: {e}")
finally:
    # 드라이버가 존재할 때만 종료하도록 안전하게 설정
    if 'driver' in locals():
        driver.quit()
