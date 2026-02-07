import os
import sys
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


BASE_URL = "https://evergreenjb.me"
ATTENDANCE_URL = f"{BASE_URL}/attendance"
KST = ZoneInfo("Asia/Seoul")


def kst_now_str() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")


def get_env(name: str) -> str:
    val = os.getenv(name, "").strip()
    if not val:
        raise RuntimeError(f"환경변수 {name} 가 비어있습니다. (GitHub Secrets 설정 필요)")
    return val


def make_driver() -> webdriver.Chrome:
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1280,900")
    opts.add_argument("--lang=ko-KR")

    # GitHub Actions ubuntu-latest 기준 (대부분 존재)
    chrome_bin = os.getenv("CHROME_BIN", "/usr/bin/google-chrome")
    if os.path.exists(chrome_bin):
        opts.binary_location = chrome_bin

    # chromedriver 경로 명시(있으면 더 안정)
    driver_path = os.getenv("CHROMEDRIVER", "/usr/bin/chromedriver")
    service = Service(driver_path) if os.path.exists(driver_path) else Service()

    driver = webdriver.Chrome(service=service, options=opts)
    driver.set_page_load_timeout(40)
    return driver


def open_login_modal(driver: webdriver.Chrome, wait: WebDriverWait) -> None:
    # 모달 DOM은 항상 존재하지만, active 붙어야 입력 가능해지는 구조.
    driver.execute_script("slPop('sl-login')")
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.sl-login.active")))
    wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "div.sl-login.active")))


def login(driver: webdriver.Chrome, user_id: str, password: str) -> None:
    wait = WebDriverWait(driver, 20)

    driver.get(ATTENDANCE_URL)
    open_login_modal(driver, wait)

    uid = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.sl-login input[name='user_id']")))
    pw = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.sl-login input[name='password']")))

    uid.clear()
    uid.send_keys(user_id)
    pw.clear()
    pw.send_keys(password)

    # submit 버튼 클릭 or 폼 submit
    submit_btn = wait.until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "div.sl-login form[name='memberLogin'] button.bt-submit"))
    )
    submit_btn.click()

    # 로그인 성공 시 /attendance 로 돌아오는 구조(success_return_url=/attendance)
    wait.until(lambda d: "attendance" in d.current_url)

    # “비로그인” 텍스트가 사라졌는지로 2차 확인(사이트에 따라 문구 달라질 수 있음)
    # 너무 엄격하진 않게: 로그인 유지/닉네임 영역 등으로 판단은 생략.
    return


def try_click_attendance(driver: webdriver.Chrome) -> str:
    """
    출석 버튼/링크 셀렉터가 스킨마다 달라서,
    '출석' 텍스트/onclick 키워드 기반으로 여러 후보를 시도한다.
    성공/이미출석/실패를 문자열로 반환.
    """
    wait = WebDriverWait(driver, 20)
    driver.get(ATTENDANCE_URL)

    page = driver.page_source

    # 이미 출석한 날엔 보통 문구가 뜰 수 있음(정확 문구는 스킨마다 다름)
    already_patterns = [
        "이미 출석",
        "출석하셨",
        "중복출석",
        "중복 출석",
        "출석 완료",
    ]
    if any(p in page for p in already_patterns):
        return "already"

    # 후보 요소들: 버튼/링크/인풋 등
    candidates = []

    # 1) 텍스트로 찾기 (출석/출석체크/출첵)
    xpaths = [
        "//button[contains(., '출석')]",
        "//a[contains(., '출석')]",
        "//button[contains(., '출석체크')]",
        "//a[contains(., '출석체크')]",
        "//button[contains(., '출첵')]",
        "//a[contains(., '출첵')]",
        "//input[@type='submit' and (contains(@value,'출석') or contains(@value,'출첵'))]",
    ]
    for xp in xpaths:
        try:
            els = driver.find_elements(By.XPATH, xp)
            candidates.extend(els)
        except Exception:
            pass

    # 2) onclick 힌트로 찾기 (attendance / procFilter / check 등)
    onclick_xpaths = [
        "//*[contains(@onclick,'attendance')]",
        "//*[contains(@onclick,'Attendance')]",
        "//*[contains(@onclick,'procFilter')]",
        "//*[contains(@onclick,'checkin')]",
        "//*[contains(@onclick,'check')]",
    ]
    for xp in onclick_xpaths:
        try:
            els = driver.find_elements(By.XPATH, xp)
            candidates.extend(els)
        except Exception:
            pass

    # 중복 제거(참조 기준)
    uniq = []
    seen = set()
    for el in candidates:
        try:
            key = (el.tag_name, el.get_attribute("outerHTML")[:200])
        except Exception:
            continue
        if key in seen:
            continue
        seen.add(key)
        uniq.append(el)

    # 클릭 시도
    for el in uniq:
        try:
            if not el.is_displayed():
                continue
            if not el.is_enabled():
                continue

            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            wait.until(EC.element_to_be_clickable(el))
            el.click()

            # 클릭 후 변화 기다리기: 로딩/알림/리스트 갱신 등.
            # 완벽한 판별은 어렵지만, 페이지 소스 변화나 알림 텍스트로 판단.
            wait.until(lambda d: True)  # 최소 대기
            new_page = driver.page_source

            if any(p in new_page for p in already_patterns):
                return "already"

            # 성공 힌트(스킨에 따라 다를 수 있음)
            success_patterns = [
                "출석 체크",
                "출석체크",
                "출석 성공",
                "축하",
                "완료",
                "포인트",
            ]
            if any(p in new_page for p in success_patterns) and new_page != page:
                return "success"

            # 페이지가 바뀌었는데 확신이 없으면 success로 처리(보수적으로)
            if new_page != page:
                return "success"
        except Exception:
            continue

    # 여기까지면 버튼을 못 찾거나 클릭이 먹지 않은 케이스
    return "fail"


def update_readme(status: str) -> None:
    """
    README 규칙:
    - 1줄: 배지
    - 2줄부터: 로그 (최신이 위)
    """
    badge_line = (
        "[![Evergreen Auto Checkin]"
        "(https://github.com/pintordev/evergreen_auto_checkin/actions/workflows/evergreen_checkin.yml/badge.svg)]"
        "(https://github.com/pintordev/evergreen_auto_checkin/actions/workflows/evergreen_checkin.yml)"
    )

    ts = kst_now_str()
    if status == "success":
        log = f"- {ts} | ✅ 출석 체크 성공"
    elif status == "already":
        log = f"- {ts} | 🟨 이미 출석했거나 중복으로 처리됨"
    else:
        log = f"- {ts} | ❌ 출석 체크 실패"

    path = "README.md"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    else:
        lines = []

    # 배지 라인 확보
    if not lines:
        lines = [badge_line]
    else:
        # 첫 줄이 배지가 아니면 교체
        if lines[0].strip() != badge_line.strip():
            # 기존 첫 줄이 배지 유사면 교체, 아니면 맨 위에 삽입
            if lines[0].strip().startswith("[![Evergreen Auto Checkin]"):
                lines[0] = badge_line
            else:
                lines = [badge_line] + lines

    # 기존 로그들에서 빈 줄 제거(요구사항: 배지 다음 줄부터 바로 기록)
    rest = [ln for ln in lines[1:] if ln.strip() != ""]

    # 같은 타임스탬프 중복(재시도) 방지: 같은 분/초 중복이면 그냥 위에 또 쌓이게 놔둠
    new_lines = [lines[0], log] + rest

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(new_lines).rstrip() + "\n")


def main() -> int:
    user_id = get_env("EVERGREEN_ID")
    password = get_env("EVERGREEN_PW")

    driver = None
    status = "fail"
    try:
        driver = make_driver()
        login(driver, user_id, password)
        status = try_click_attendance(driver)
        update_readme(status)

        if status == "success":
            print("✅ 출석 체크 성공")
            return 0
        if status == "already":
            print("🟨 이미 출석했거나 중복으로 처리됨")
            return 0

        # 실패면 디버깅용 힌트 출력 (너무 길지 않게)
        html = driver.page_source if driver else ""
        print("❌ 출석 체크 실패: 버튼을 찾지 못했거나 클릭 후 변화가 없습니다.")
        print("---- DEBUG (partial) ----")
        print(re.sub(r"\s+", " ", html)[:2000])
        print("-------------------------")
        return 1

    except Exception as e:
        print(f"❌ 실패: {type(e).__name__} - {e}")
        return 1
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
