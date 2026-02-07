import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait


KST = ZoneInfo("Asia/Seoul")
BASE_URL = "https://evergreenjb.me"
ATTENDANCE_URL = f"{BASE_URL}/attendance"


@dataclass
class Result:
    ok: bool
    message: str


def now_kst_str() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")


def build_driver() -> webdriver.Chrome:
    opts = Options()
    # GitHub Actions / headless 안정 옵션
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1440,900")
    opts.add_argument("--lang=ko-KR")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(30)
    return driver


def js_click(driver: webdriver.Chrome, el):
    driver.execute_script("arguments[0].click();", el)


def js_set_value(driver: webdriver.Chrome, el, value: str):
    driver.execute_script("arguments[0].value = arguments[1];", el, value)
    # input 이벤트 트리거 (가끔 프론트가 이벤트를 보고 값 반영)
    driver.execute_script(
        "arguments[0].dispatchEvent(new Event('input', {bubbles:true}));"
        "arguments[0].dispatchEvent(new Event('change', {bubbles:true}));",
        el,
    )


def safe_find(driver: webdriver.Chrome, by, sel):
    try:
        return driver.find_element(by, sel)
    except NoSuchElementException:
        return None


def wait_presence(driver: webdriver.Chrome, by, sel, timeout=15):
    return WebDriverWait(driver, timeout).until(lambda d: d.find_element(by, sel))


def is_logged_in(driver: webdriver.Chrome) -> bool:
    # 비로그인 상태면 .sla-status 텍스트가 "비로그인"으로 보임
    el = safe_find(driver, By.CSS_SELECTOR, ".sla-status")
    if not el:
        return False
    return "비로그인" not in (el.text or "")


def open_login_modal(driver: webdriver.Chrome):
    # 로그인 버튼은 여러 위치에 있음 (a.bt-login 등)
    btn = safe_find(driver, By.CSS_SELECTOR, "a.bt-login.slbt")
    if not btn:
        btn = safe_find(driver, By.CSS_SELECTOR, "a.bt-login")
    if not btn:
        # 최후: onclick=slPop('sl-login') 인 링크
        btn = safe_find(driver, By.CSS_SELECTOR, "[onclick*=\"slPop('sl-login'\"]")
    if not btn:
        raise RuntimeError("로그인 버튼을 찾지 못했습니다.")
    js_click(driver, btn)

    # 모달은 애니메이션 때문에 visible 판단이 잘 안 됨 → presence만
    wait_presence(driver, By.CSS_SELECTOR, ".slmd.sl-login", timeout=15)
    time.sleep(1.2)  # 애니메이션 안정화


def do_login(driver: webdriver.Chrome, user_id: str, password: str):
    open_login_modal(driver)

    # 모달 내부가 아니라 DOM 전체에서 name으로 바로 찾는 게 가장 안정적
    id_input = wait_presence(driver, By.NAME, "user_id", timeout=15)
    pw_input = wait_presence(driver, By.NAME, "password", timeout=15)

    js_set_value(driver, id_input, user_id)
    js_set_value(driver, pw_input, password)

    # submit 버튼도 JS 클릭 (clickable 대기 X)
    submit_btn = safe_find(driver, By.CSS_SELECTOR, "button.bt-login.bt-submit")
    if not submit_btn:
        submit_btn = safe_find(driver, By.CSS_SELECTOR, "button.bt-submit")
    if not submit_btn:
        # 최후: form submit
        form = safe_find(driver, By.CSS_SELECTOR, "form[name='memberLogin']")
        if not form:
            raise RuntimeError("로그인 submit 버튼/폼을 찾지 못했습니다.")
        driver.execute_script("arguments[0].submit();", form)
    else:
        js_click(driver, submit_btn)

    # 로그인 처리/리다이렉트 안정화
    time.sleep(1.0)

    # 로그인 완료 판정:
    # 1) sla-status가 비로그인이 아니거나
    # 2) 로그인 모달이 active 상태가 아니거나
    # 둘 중 하나라도 만족하면 통과
    def _logged_in(_d):
        if is_logged_in(_d):
            return True
        src = _d.page_source or ""
        if "sl-login active" not in src:
            # 모달이 닫혔으면 로그인 진행된 것으로 간주 (세션 반영은 아래에서 재확인)
            return True
        return False

    WebDriverWait(driver, 20).until(_logged_in)

    # 출석 페이지를 다시 로드해서 세션 반영 확실히
    driver.get(ATTENDANCE_URL)
    time.sleep(1.2)

    if not is_logged_in(driver):
        raise RuntimeError("로그인 후에도 비로그인 상태입니다. (ID/PW 또는 추가 보안/차단 가능)")


def get_today_status_class(driver: webdriver.Chrome) -> str:
    # 오늘 칸 status div class 확인
    status = safe_find(driver, By.CSS_SELECTOR, ".slac-day.today .slac-day-status")
    if not status:
        status = safe_find(driver, By.CSS_SELECTOR, ".slac-day.today.selected .slac-day-status")
    if not status:
        return ""
    return status.get_attribute("class") or ""


def already_checked(driver: webdriver.Chrome) -> bool:
    cls = get_today_status_class(driver)
    # 기본은 "att-face att-face--" 처럼 끝이 비어있음
    # 출석하면 보통 att-face--something 으로 suffix가 붙음
    return bool(re.search(r"att-face--[a-zA-Z0-9_]+", cls))


def try_click_attendance(driver: webdriver.Chrome) -> bool:
    """
    로그인 후, 출석 버튼을 최대한 범용적으로 찾아 클릭한다.
    사이트 스킨/버튼 문구가 바뀌어도 버티게 XPath/selector를 여러 개 시도.
    """
    candidates = []

    # 흔한 class 후보들
    css_list = [
        "a.bt-att", "button.bt-att",
        "a.bt-attendance", "button.bt-attendance",
        "a.bt-checkin", "button.bt-checkin",
        "a.attendance", "button.attendance",
        "a.bt-submit-att", "button.bt-submit-att",
    ]
    for sel in css_list:
        el = safe_find(driver, By.CSS_SELECTOR, sel)
        if el:
            candidates.append(el)

    # 텍스트 기반 후보 (출석/체크/출석하기 등)
    xpath_list = [
        # 링크/버튼 중 "출석" 포함 + "정보" 제외
        "//a[contains(., '출석') and not(contains(., '출석정보'))]",
        "//button[contains(., '출석') and not(contains(., '출석정보'))]",
        # "체크" 포함
        "//a[contains(., '체크')]",
        "//button[contains(., '체크')]",
        # "출석하기"
        "//a[contains(., '출석') and contains(., '하기')]",
        "//button[contains(., '출석') and contains(., '하기')]",
    ]
    for xp in xpath_list:
        try:
            els = driver.find_elements(By.XPATH, xp)
            for e in els[:5]:
                candidates.append(e)
        except Exception:
            pass

    # 중복 제거 (id/outerHTML 기반)
    uniq = []
    seen = set()
    for e in candidates:
        try:
            key = (e.tag_name, e.get_attribute("id"), e.get_attribute("class"), e.text.strip()[:20])
        except Exception:
            continue
        if key in seen:
            continue
        seen.add(key)
        uniq.append(e)

    # 실제 클릭 시도
    for el in uniq:
        try:
            js_click(driver, el)
            time.sleep(2.0)  # AJAX 반영 대기
            # 출석 상태 class 변하면 성공으로 간주
            if already_checked(driver):
                return True
        except Exception:
            continue

    return False


def update_readme(result: Result):
    badge_line = (
        "[![Evergreen Auto Checkin]"
        "(https://github.com/pintordev/evergreen_auto_checkin/actions/workflows/evergreen_checkin.yml/badge.svg)]"
        "(https://github.com/pintordev/evergreen_auto_checkin/actions/workflows/evergreen_checkin.yml)"
    )

    ts = now_kst_str()
    prefix = "✅ 출석 체크 성공" if result.ok else "❌ 출석 체크 실패"
    log_line = f"- {ts} | {prefix}"
    if not result.ok and result.message:
        # 너무 길면 README가 더러워져서 1줄로 압축
        msg = re.sub(r"\s+", " ", result.message).strip()
        msg = (msg[:180] + "…") if len(msg) > 180 else msg
        log_line += f" ({msg})"

    path = "README.md"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    else:
        lines = []

    # 1) 배지 첫 줄 강제
    if not lines:
        lines = [badge_line]
    else:
        # 첫 줄이 배지가 아니면 첫 줄을 배지로 교체/삽입
        if lines[0].strip() != badge_line:
            # 기존에 배지 라인이 어딘가 있으면 제거
            lines = [ln for ln in lines if ln.strip() != badge_line]
            lines.insert(0, badge_line)

    # 2) 두 번째 줄부터 로그가 시작해야 함 (최신이 위)
    # 기존 로그 라인이 있다면, 배지 다음 줄에 새 로그 삽입
    insert_at = 1
    # 빈 줄이 있으면 날려서 “그 다음 줄부터 기록” 형태 유지
    while insert_at < len(lines) and lines[insert_at].strip() == "":
        del lines[insert_at]

    lines.insert(insert_at, log_line)

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip() + "\n")


def main():
    user_id = os.getenv("EVERGREEN_ID", "").strip()
    password = os.getenv("EVERGREEN_PW", "").strip()

    if not user_id or not password:
        print("❌ 실패: 환경변수 EVERGREEN_ID / EVERGREEN_PW 가 비어있습니다.")
        sys.exit(1)

    driver = build_driver()
    result = Result(ok=False, message="")

    try:
        driver.get(ATTENDANCE_URL)
        time.sleep(1.2)

        do_login(driver, user_id, password)

        # 이미 출석했으면 성공 처리
        if already_checked(driver):
            result = Result(ok=True, message="이미 출석 상태로 보입니다.")
        else:
            ok = try_click_attendance(driver)
            if ok:
                result = Result(ok=True, message="출석 버튼 클릭 후 상태 변경 감지")
            else:
                # 마지막으로 새로고침 후 한번 더 상태 확인
                driver.refresh()
                time.sleep(2.0)
                if already_checked(driver):
                    result = Result(ok=True, message="새로고침 후 출석 상태 감지")
                else:
                    result = Result(ok=False, message="출석 버튼을 찾거나 상태 변경을 감지하지 못함")

    except TimeoutException as e:
        result = Result(ok=False, message=f"TimeoutException - {e.msg if hasattr(e, 'msg') else str(e)}")
    except Exception as e:
        result = Result(ok=False, message=f"{type(e).__name__} - {str(e)}")
    finally:
        # 실패 시 디버그 스크린샷 남기면 Actions에서 확인 가능
        try:
            if not result.ok:
                driver.save_screenshot("debug.png")
        except Exception:
            pass
        try:
            driver.quit()
        except Exception:
            pass

    # README 기록 업데이트 (항상 기록)
    update_readme(result)

    if result.ok:
        print(f"✅ 성공: {result.message}")
        sys.exit(0)
    else:
        print(f"❌ 실패: {result.message}")
        sys.exit(1)


if __name__ == "__main__":
    main()
