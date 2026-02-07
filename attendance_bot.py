import os
import sys
from datetime import datetime, timezone, timedelta

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


BASE_URL = "https://evergreenjb.me"
ATTENDANCE_URL = f"{BASE_URL}/attendance"

KST = timezone(timedelta(hours=9))


def now_kst_str() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")


def build_driver() -> webdriver.Chrome:
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1280,2000")
    chrome_options.add_argument("--lang=ko-KR")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")

    driver = webdriver.Chrome(options=chrome_options)
    driver.set_page_load_timeout(30)
    return driver


from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def login_if_needed(driver, user_id: str, password: str) -> None:
    wait = WebDriverWait(driver, 30)

    driver.get(ATTENDANCE_URL)
    wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

    # 이미 로그인 상태면 패스
    if "로그아웃" in driver.page_source:
        return

    # 1) 로그인 버튼 클릭 (onclick에 slPop('sl-login')가 있는 a 태그)
    login_btn = wait.until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, "a[onclick*=\"slPop('sl-login')\"], a[onclick*=\"slPop(\\\"sl-login\\\")\"]")
        )
    )
    driver.execute_script("arguments[0].click();", login_btn)

    # 2) 로그인 모달이 열릴 때까지 대기
    #    (id가 아니라 class=sl-login 인 경우가 많음)
    modal = wait.until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, ".sl-login.active, .sl-login")
        )
    )

    # 3) 모달 내부에서 input 찾기 (presence 기준)
    #    (혹시 name이 바뀌어도 최대한 커버)
    id_input = wait.until(lambda d: (
        modal.find_element(By.CSS_SELECTOR, "input[name='user_id'], input#user_id")
    ))
    pw_input = wait.until(lambda d: (
        modal.find_element(By.CSS_SELECTOR, "input[name='password'], input#password, input[type='password']")
    ))

    # 4) 값 주입 (headless 안정용: JS로 value 넣고 엔터)
    driver.execute_script("arguments[0].value = arguments[1];", id_input, user_id)
    driver.execute_script("arguments[0].value = arguments[1];", pw_input, password)
    pw_input.send_keys(Keys.ENTER)

    # 5) 로그인 성공 확인
    wait.until(lambda d: "로그아웃" in d.page_source)

    # 6) 출석 페이지 다시 진입
    driver.get(ATTENDANCE_URL)
    wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

def is_already_checked_in_today(driver: webdriver.Chrome) -> bool:
    """
    오늘 출석 여부 판단:
    - 좌측 상단 상태가 '출석안함'이면 False
    - 이미 출석이면 보통 '출석함' 류로 바뀌거나, 폼이 안 보이거나, 안내 문구가 바뀜
    """
    src = driver.page_source
    if "출석안함" in src:
        return False
    # 보수적으로 폼이 없으면 이미 했을 가능성이 큼
    forms = driver.find_elements(By.CSS_SELECTOR, "form#click_button")
    if not forms:
        return True
    return True


def do_checkin(driver: webdriver.Chrome, message: str) -> None:
    wait = WebDriverWait(driver, 20)
    driver.get(ATTENDANCE_URL)
    wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

    if is_already_checked_in_today(driver):
        raise RuntimeError("이미 오늘 출석이 된 상태로 보입니다.")

    # greetings 입력
    greetings = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input#greetings")))
    greetings.clear()
    greetings.send_keys(message)

    # 출석 버튼 클릭
    btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "form#click_button button.bt-att")))
    try:
        btn.click()
    except Exception:
        driver.execute_script("arguments[0].click();", btn)

    # 성공 판정: 페이지에 출석안함이 사라지거나, 내 출석 리스트에 오늘이 생기거나 등
    # 간단히 '출석안함'이 사라지는 걸 먼저 확인
    wait.until(lambda d: "출석안함" not in d.page_source)


def update_readme(status_line: str) -> None:
    """
    README.md
    - 첫 줄: 배지(유지)
    - 둘째 줄부터 기록. 최신이 위로.
    """
    path = "README.md"
    if not os.path.exists(path):
        raise RuntimeError("README.md가 없습니다. 리포지토리 루트에서 실행 중인지 확인하세요.")

    with open(path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    if not lines:
        raise RuntimeError("README.md가 비어 있습니다.")

    badge = lines[0].strip()

    # 기존 기록 라인들(첫 줄 제외)
    history = [ln.rstrip() for ln in lines[1:] if ln.strip()]

    # 최신 기록을 최상단에 삽입
    new_history = [status_line] + history

    out = "\n".join([badge] + new_history) + "\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(out)


def main() -> None:
    user_id = os.getenv("EVERGREEN_ID", "").strip()
    user_pw = os.getenv("EVERGREEN_PW", "").strip()

    if not user_id or not user_pw:
        raise RuntimeError("환경변수 EVERGREEN_ID / EVERGREEN_PW 가 필요합니다.")

    message = os.getenv("CHECKIN_MESSAGE", "오오~렐레!").strip() or "오오~렐레!"

    driver = None
    try:
        driver = build_driver()
        login_if_needed(driver, user_id, user_pw)
        do_checkin(driver, message)

        ts = now_kst_str()
        line = f"- {ts} | ✅ 출석 체크 성공"
        update_readme(line)
        print(line)

    finally:
        if driver:
            driver.quit()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        ts = now_kst_str()
        msg = f"❌ 실패: {type(e).__name__} - {e}"
        print(msg)
        # 실패도 기록하고 싶으면 아래 주석 해제
        # update_readme(f"- {ts} | {msg}")
        sys.exit(1)
