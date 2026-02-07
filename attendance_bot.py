import os
import sys
import time
from datetime import datetime, timedelta

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


URL = "https://evergreenjb.me/attendance"


# -------------------------
# 시간 (KST 고정)
# -------------------------
def now_kst():
    return datetime.utcnow() + timedelta(hours=9)


# -------------------------
# README 기록 (최신이 위)
# -------------------------
def update_readme(message: str):
    ts = now_kst().strftime("%Y-%m-%d %H:%M:%S")
    new_line = f"- {ts} | {message}\n"

    with open("README.md", "r", encoding="utf-8") as f:
        lines = f.readlines()

    badge = lines[0]
    logs = lines[1:]

    logs.insert(0, new_line)

    with open("README.md", "w", encoding="utf-8") as f:
        f.write(badge)
        f.writelines(logs)


# -------------------------
# 드라이버
# -------------------------
def create_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,900")
    return webdriver.Chrome(options=options)


# -------------------------
# 로그인
# -------------------------
def login(driver, wait, user_id, password):
    driver.get(URL)

    # 로그인 버튼 클릭
    wait.until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "a.bt-login"))
    ).click()

    # 🔥 로그인 모달 활성화 대기
    wait.until(
        EC.presence_of_element_located((By.CSS_SELECTOR, ".slmd.sl-login.active"))
    )

    modal = driver.find_element(By.CSS_SELECTOR, ".slmd.sl-login.active")

    id_input = modal.find_element(By.NAME, "user_id")
    pw_input = modal.find_element(By.NAME, "password")

    id_input.clear()
    id_input.send_keys(user_id)

    pw_input.clear()
    pw_input.send_keys(password)

    modal.find_element(By.CSS_SELECTOR, "button.bt-submit").click()

    # 로그인 완료 대기 (비로그인 문구 제거)
    wait.until(lambda d: "비로그인" not in d.page_source)


# -------------------------
# 출석 체크
# -------------------------
def check_attendance(driver, wait):
    driver.get(URL)

    # 이미 출석했으면 버튼 없음 → 정상 종료
    if "이미 출석" in driver.page_source:
        print("ℹ️ 이미 출석 완료")
        return "already"

    # 오늘 날짜 셀 클릭
    today = wait.until(
        EC.element_to_be_clickable(
            (By.CSS_SELECTOR, ".slac-day.today.selected a.sllk-plane")
        )
    )
    today.click()
    time.sleep(2)

    # 출석 성공 여부 판단
    if "출석" in driver.page_source:
        return "success"

    return "unknown"


# -------------------------
# 메인
# -------------------------
def main():
    user_id = os.getenv("EVERGREEN_ID")
    password = os.getenv("EVERGREEN_PW")

    if not user_id or not password:
        raise RuntimeError("EVERGREEN_ID / EVERGREEN_PW 환경변수가 없습니다.")

    driver = create_driver()
    wait = WebDriverWait(driver, 15)

    try:
        login(driver, wait, user_id, password)

        result = check_attendance(driver, wait)

        if result == "success":
            print("✅ 출석 체크 성공")
            update_readme("✅ 출석 체크 성공")

        elif result == "already":
            print("ℹ️ 이미 출석 완료 (기록 안 함)")

        else:
            raise RuntimeError("출석 결과 확인 불가")

    except Exception as e:
        print(f"❌ 실패: {type(e).__name__} - {e}")
        update_readme(f"🚨 시스템 에러: {e}")
        sys.exit(1)

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
