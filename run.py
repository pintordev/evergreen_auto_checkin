import os
import datetime
import time
import base64
import requests
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
GH_PAT = os.environ.get('GH_PAT')  # GitHub Personal Access Token
REPO = os.environ.get('GITHUB_REPOSITORY')  # 예: user/repo

if not USER_ID or not USER_PW or not GH_PAT or not REPO:
    print("❌ 필수 환경 변수가 설정되지 않았습니다.")
    exit(1)

def get_kst():
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=9)).strftime('%Y-%m-%d %H:%M:%S')

def update_readme(message):
    """GitHub API를 통해 README.md를 업데이트"""
    api_url = f"https://api.github.com/repos/{REPO}/contents/README.md"
    headers = {"Authorization": f"token {GH_PAT}"}

    # 현재 README.md 가져오기
    r = requests.get(api_url, headers=headers)
    if r.status_code != 200:
        print(f"❌ README.md 불러오기 실패: {r.status_code}")
        return

    data = r.json()
    sha = data["sha"]
    content = base64.b64decode(data["content"]).decode("utf-8")

    # 새 기록 추가
    new_content = content + f"- {get_kst()} | {message}\n"
    encoded_content = base64.b64encode(new_content.encode("utf-8")).decode("utf-8")

    # 업데이트
    payload = {
        "message": f"📝 출석 기록 업데이트",
        "content": encoded_content,
        "sha": sha
    }
    r = requests.put(api_url, headers=headers, json=payload)
    if r.status_code == 200 or r.status_code == 201:
        print(f"📝 README.md 업데이트 성공: {message}")
    else:
        print(f"❌ README.md 업데이트 실패: {r.status_code} {r.text}")

# 브라우저 설정
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
            update_readme("🚨 로그인 실패")
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
        update_readme("✅ 출석 체크 성공")
        print("✅ 출석 체크 완료")
    except Exception as e:
        update_readme(f"ℹ️ 출석 버튼 없음 또는 클릭 실패: {e}")
        print(f"ℹ️ 출석 버튼 없음 또는 클릭 실패: {e}")

except Exception as e:
    update_readme(f"🚨 시스템 에러 발생: {e}")
    print(f"❌ 에러 상세: {e}")

finally:
    driver.quit()
