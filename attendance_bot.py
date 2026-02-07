import os
import sys
from datetime import datetime, timezone, timedelta

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

BASE_URL = "https://evergreenjb.me"
ATTENDANCE_URL = f"{BASE_URL}/attendance"

KST = timezone(timedelta(hours=9))
MARKER = "<!-- LOGS -->"

BADGE_LINE = (
    "[![Evergreen Auto Checkin]"
    "(https://github.com/pintordev/evergreen_auto_checkin/actions/workflows/evergreen_checkin.yml/badge.svg)]"
    "(https://github.com/pintordev/evergreen_auto_checkin/actions/workflows/evergreen_checkin.yml) "
    f"{MARKER}"
)

DEFAULT_GREETINGS = "오오~렐레!"


def now_kst_str() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")


def ensure_readme(readme_path: str = "README.md") -> None:
    if os.path.exists(readme_path):
        with open(readme_path, "r", encoding="utf-8") as f:
            content = f.read()
    else:
        content = ""

    lines = content.splitlines()

    if not lines:
        lines = [BADGE_LINE]
    else:
        # 첫 줄 배지 보장 + 마커 보장
        if "badge.svg" not in lines[0]:
            lines.insert(0, BADGE_LINE)
        elif MARKER not in lines[0]:
            lines[0] = lines[0].rstrip() + f" {MARKER}"

    with open(readme_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip() + "\n")


def prepend_log(message: str, readme_path: str = "README.md") -> None:
    ensure_readme(readme_path)

    with open(readme_path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines(keepends=False)

    # 마커가 있는 줄(보통 첫 줄) 바로 다음 줄에 로그를 prepend
    marker_idx = None
    for i, line in enumerate(lines):
        if MARKER in line:
            marker_idx = i
            break

    if marker_idx is None:
        # 혹시라도 마커가 없으면, 첫 줄 다음에 넣도록 fallback
        marker_idx = 0
        if lines:
            if MARKER not in lines[0]:
                lines[0] = lines[0].rstrip() + f" {MARKER}"

    log_line = f"- {now_kst_str()} | {message}"

    insert_at = marker_idx + 1
    lines.insert(insert_at, log_line)

    with open(readme_path, "w", encoding="utf-8") as f:
        f.write("".join([l + "\n" for l in lines]).rstrip() + "\n")


def build_driver() -> webdriver.Chrome:
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,900")

    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)


def login_if_needed(driver: webdriver.Chrome, user_id: str, user_pw: str) -> None:
    """
    로그인 폼 경로/필드명은 사이트 설정에 따라 다를 수 있어서
    가장 흔한 Rhymix/XE 계열 폼을 '시도'하는 방식으로 작성함.
    이미 로그인 상태면 그대로 통과.
    """
    driver.get(ATTENDANCE_URL)
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

    page = driver.page_source
    if "로그아웃" in page:
        return  # already logged in

    # 로그인 페이지로 이동 시도 (여러 경로 중 하나가 통하길 기대)
    candidate_urls = [
        f"{BASE_URL}/index.php?act=dispMemberLoginForm",
        f"{BASE_URL}/index.php?mid=attendance&act=dispMemberLoginForm",
        f"{BASE_URL}/member/login",
        f"{BASE_URL}/index.php?mid=member&act=dispMemberLoginForm",
    ]
    for u in candidate_urls:
        driver.get(u)
        WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        if "로그인" in driver.page_source:
            break

    # 흔한 로그인 input name/id 후보들을 순차 시도
    id_candidates = [
        (By.NAME, "user_id"),
        (By.NAME, "email_address"),
        (By.ID, "user_id"),
        (By.ID, "email_address"),
        (By.NAME, "userid"),
        (By.ID, "userid"),
    ]
    pw_candidates = [
        (By.NAME, "password"),
        (By.ID, "password"),
        (By.NAME, "user_password"),
        (By.ID, "user_password"),
    ]

    id_el = None
    pw_el = None

    for how, what in id_candidates:
        try:
            id_el = driver.find_element(how, what)
            if id_el:
                break
        except Exception:
            pass

    for how, what in pw_candidates:
        try:
            pw_el = driver.find_element(how, what)
            if pw_el:
                break
        except Exception:
            pass

    if not id_el or not pw_el:
        raise RuntimeError("로그인 폼의 ID/PW input을 찾지 못했습니다. (name/id가 다른 듯)")

    id_el.clear()
    id_el.send_keys(user_id)
    pw_el.clear()
    pw_el.send_keys(user_pw)
    pw_el.send_keys(Keys.ENTER)

    # 로그인 완료 대기: 출석 페이지로 돌아가서 로그아웃이 보이면 OK
    driver.get(ATTENDANCE_URL)
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    if "로그아웃" not in driver.page_source:
        raise RuntimeError("로그인 실패(로그아웃 메뉴가 안 보임). ID/PW 또는 로그인 폼 확인 필요")


def do_attendance(driver: webdriver.Chrome, greetings: str) -> str:
    driver.get(ATTENDANCE_URL)
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))

    # 이미 출석했는지 체크: 좌측 타이틀 영역의 상태 텍스트로 판별
    try:
        status_el = driver.find_element(By.CSS_SELECTOR, ".slac-title .sla-status")
        status_text = status_el.text.strip()
        if "출석안함" not in status_text:
            return "⏭️ 이미 출석 상태"
    except Exception:
        # 상태를 못 찾으면 계속 진행(사이트 스킨 변경 대비)
        pass

    # greetings 입력 + 출석 버튼 클릭
    greet_input = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "greetings"))
    )
    greet_input.clear()
    greet_input.send_keys(greetings)

    submit_btn = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "form#click_button button.bt-att"))
    )
    submit_btn.click()

    # 성공 판별: "출석안함"이 사라지거나, 우측 내 출석 리스트에 오늘 날짜가 찍히면 성공으로 처리
    def success_condition(drv: webdriver.Chrome) -> bool:
        src = drv.page_source
        if "중복출석" in src or "중복" in src:
            # 중복 메시지면 사실상 이미 찍힌 케이스로 처리 가능
            return True
        try:
            st = drv.find_element(By.CSS_SELECTOR, ".slac-title .sla-status").text.strip()
            if "출석안함" not in st:
                return True
        except Exception:
            pass
        return False

    WebDriverWait(driver, 12).until(success_condition)

    # 최종 재확인
    try:
        status_el = driver.find_element(By.CSS_SELECTOR, ".slac-title .sla-status")
        if "출석안함" in status_el.text:
            return "⚠️ 출석 시도했지만 상태 확인 불가(재확인 필요)"
    except Exception:
        pass

    return "✅ 출석 체크 성공"


def main():
    user_id = os.getenv("EVERGREEN_ID", "").strip()
    user_pw = os.getenv("EVERGREEN_PW", "").strip()
    greetings = os.getenv("EVERGREEN_GREETINGS", DEFAULT_GREETINGS).strip() or DEFAULT_GREETINGS

    if not user_id or not user_pw:
        prepend_log("❌ secrets 미설정(EVERGREEN_ID/EVERGREEN_PW)")
        print("Missing EVERGREEN_ID / EVERGREEN_PW", file=sys.stderr)
        sys.exit(1)

    driver = build_driver()
    try:
        login_if_needed(driver, user_id, user_pw)
        result = do_attendance(driver, greetings)
        prepend_log(result)
        print(result)
    except Exception as e:
        msg = f"❌ 실패: {type(e).__name__} - {e}"
        prepend_log(msg)
        print(msg, file=sys.stderr)
        sys.exit(1)
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
