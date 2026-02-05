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
    return (datetime.datetime.now() + datetime.timedelta(hours=9)).strftime('%Y-%m-%d %H:%M:%S')

def log_to_readme(message):
    try:
        with open("README.md", "a", encoding="utf-8") as f:
            f.write(f"- {get_kst()} | {message}\n")
        print(f"📝 결과 기록: {message}")
    except Exception as e:
        print(f"📝 기록 실패: {e}")

options = Options()
options.add_argument("--headless")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36")

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
wait = WebDriverWait(driver, 15)

try:
    print(f"🚀 작업 시작: {get_kst()}")
    driver.get("https://evergreenjb.me/")
    time.sleep(5)

    # 1. 로그인 수행
    try:
        id_input = wait.until(EC.presence_of_element_located((By.NAME, "user_id")))
        pw_input = driver.find_element(By.NAME, "password")
        
        driver.execute_script("arguments[0].value = arguments[1];", id_input, USER_ID)
        driver.execute_script("arguments[0].value = arguments[1];", pw_input, USER_PW)
        
        # 로그인 버튼 클릭 (정확히 버튼 개체를 찾아서 클릭)
        try:
            login_btn = driver.find_element(By.XPATH, "//button[contains(text(), '로그인')]")
        except:
            login_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            
        driver.execute_script("arguments[0].click();", login_btn)
        time.sleep(5)
        print("✅ 로그인 시도 완료")
    except Exception as e:
        print(f"ℹ️ 로그인 입력창을 찾을 수 없거나 이미 로그인됨: {e}")

    # 2. 출석 페이지 이동
    driver.get("https://evergreenjb.me/attendance")
    time.sleep(5)

    # 3. 출석 버튼 클릭 및 결과 확인
    try:
        # '출석' 텍스트를 포함한 버튼이 나타날 때까지 대기
        att_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), '출석')]")))
        
        # 버튼으로 스크롤 후 자바스크립트로 클릭 (가장 확실함)
        driver.execute_script("arguments[0].scrollIntoView(true);", att_btn)
        time.sleep(1)
        driver.execute_script("arguments[0].click();", att_btn)
        print("✅ 버튼 클릭 완료, 팝업 대기 중...")
        
        # 4. 알림창(Alert) 처리
        time.sleep(3)
        try:
            alert = driver.switch_to.alert
            result_msg = alert.text  # "이미 출석했습니다" 혹은 "출석되었습니다"
            alert.accept()
            log_to_readme(f"✅ 결과: {result_msg}")
        except:
            # 브라우저 알림창이 아닌 레이어 팝업인 경우 엔터 입력
            driver.switch_to.active_element.send_keys(Keys.ENTER)
            log_to_readme("✅ 출석 버튼 클릭 성공 (팝업 자동 닫기)")

    except Exception as e:
        # 버튼이 없는 경우 (이미 출석했거나 로그인 실패)
        page_source = driver.page_source
        if "이미" in page_source:
            log_to_readme("ℹ️ 이미 출석을 완료한 상태입니다.")
        else:
            log_to_readme("🚨 출석 버튼을 찾지 못함 (로그인 상태 확인 필요)")
            print(f"상세 에러: {e}")

except Exception as e:
    log_to_readme(f"🚨 시스템 에러 발생")
    print(f"최종 에러: {e}")
finally:
    if 'driver' in locals():
        driver.quit()
