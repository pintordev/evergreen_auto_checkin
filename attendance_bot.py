# attendance_bot.py
# 사용법(로컬):
# export EVERGREEN_ID="polomolo"
# export EVERGREEN_PW="atmu7510"
# python attendance_bot.py
#
# (Windows PowerShell)
#   $env:EVERGREEN_ID="아이디"
#   $env:EVERGREEN_PW="비번"
#   python .\attendance_bot.py

import os
import sys
import time
import datetime
import logging
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException


ATTENDANCE_URL = "https://evergreenjb.me/attendance"


# ----------------------------
# logging / debug helpers
# ----------------------------
def setup_logger() -> logging.Logger:
    Path("logs").mkdir(exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = Path("logs") / f"run_{ts}.log"

    logger = logging.getLogger("evergreen")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)

    logger.addHandler(sh)
    logger.addHandler(fh)

    logger.info(f"[LOG] write to {log_path}")
    return logger


def save_debug(driver: webdriver.Chrome, logger: logging.Logger, reason: str) -> None:
    Path("debug").mkdir(exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    base = Path("debug") / f"{ts}_{reason}"

    try:
        png = f"{base}.png"
        html = f"{base}.html"
        driver.save_screenshot(png)
        Path(html).write_text(driver.page_source, encoding="utf-8")
        logger.error(f"[DEBUG] saved: {png}")
        logger.error(f"[DEBUG] saved: {html}")
    except Exception as e:
        logger.error(f"[DEBUG] save failed: {type(e).__name__}: {e}")


# ----------------------------
# core utils
# ----------------------------
def kst_today_label() -> str:
    return f"{datetime.datetime.now().day}일"


def build_driver(headless=True):
    opts = webdriver.ChromeOptions()

    # 1. 아까 추가한 우회 설정
    opts.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    opts.add_argument('--disable-blink-features=AutomationControlled')
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option('useAutomationExtension', False)

    # 2. 깃허브 액션 에러 해결을 위한 필수 설정 (추가할 부분)
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    if headless:
        opts.add_argument('--headless')

    driver = webdriver.Chrome(options=opts)

    # 3. 추가 우회 (선택 사항이지만 권장)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    return driver


def page_is_403(driver) -> bool:
    src = (driver.page_source or "").lower()
    title = (driver.title or "").lower()
    return ("403 forbidden" in src) or ("403 forbidden" in title)


def safe_get(driver, logger: logging.Logger, url: str) -> None:
    logger.info(f"[GET] {url}")
    driver.get(url)
    time.sleep(0.3)
    if page_is_403(driver):
        raise RuntimeError(f"403_forbidden ({url})")


# ----------------------------
# login detection / login flow
# ----------------------------
def find_login_button(driver):
    # 네가 준 버튼:
    # <a class="bt-login slbt slbt--rect" onclick="slPop('sl-login')">로그인</a>
    cands = driver.find_elements(By.CSS_SELECTOR, "a.bt-login")
    for a in cands:
        try:
            txt = (a.text or "").strip()
            oc = (a.get_attribute("onclick") or "")
            if "로그인" in txt or "slPop('sl-login')" in oc or "slPop(\"sl-login\")" in oc:
                return a
        except Exception:
            pass
    return None


def is_logged_in(driver) -> bool:
    """
    '로그인 상태'는 확실한 양성 근거가 있을 때만 True.
    (로그인 버튼이 보이면 무조건 False)
    """
    # 로그인 버튼이 있으면 비로그인
    if find_login_button(driver) is not None:
        return False

    src = driver.page_source or ""

    # 페이지 하단에 '로그인이 필요합니다' 뜨면 비로그인
    if "로그인이 필요합니다" in src:
        return False

    # 로그인 폼이 보이거나 존재하면 비로그인으로 간주
    if len(driver.find_elements(By.CSS_SELECTOR, "form[name='memberLogin']")) > 0:
        return False

    # 로그아웃/마이메뉴 등의 흔한 텍스트가 있으면 로그인으로 간주(사이트마다 다를 수 있음)
    if ("로그아웃" in src) or ("마이" in src and "내" in src and "메뉴" in src):
        return True

    # 애매하면 False (여기서 True로 두면 지금처럼 스킵하고 망함)
    return False


def open_login_modal(driver, wait: WebDriverWait, logger: logging.Logger) -> None:
    btn = find_login_button(driver)
    if btn is None:
        # 하단 "로그인" 링크가 따로 있을 수도 있으니 한번 더 시도
        links = driver.find_elements(By.XPATH, "//a[contains(normalize-space(.), '로그인')]")
        btn = links[0] if links else None

    if btn is None:
        raise RuntimeError("로그인 버튼을 찾지 못했습니다")

    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
    try:
        btn.click()
    except Exception:
        driver.execute_script("arguments[0].click();", btn)

    # 모달 form 존재 확인
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "form[name='memberLogin']")))
    logger.info("[LOGIN] modal opened")


def do_login(driver, wait: WebDriverWait, logger: logging.Logger, user_id: str, password: str) -> None:
    form = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "form[name='memberLogin']")))

    id_input = form.find_element(By.CSS_SELECTOR, "input[name='user_id']")
    pw_input = form.find_element(By.CSS_SELECTOR, "input[name='password']")
    submit_btn = form.find_element(By.CSS_SELECTOR, "button.bt-login.bt-submit[type='submit']")

    id_input.clear()
    id_input.send_keys(user_id)
    pw_input.clear()
    pw_input.send_keys(password)

    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", submit_btn)
    try:
        submit_btn.click()
    except Exception:
        driver.execute_script("arguments[0].click();", submit_btn)

    # 로그인 완료 대기:
    # - 로그인 버튼이 없어지거나(헤더에서)
    # - 또는 "로그인이 필요합니다" 문구가 사라지거나
    # - 또는 출석 버튼이 나타나거나
    def _logged_in_condition(d):
        if find_login_button(d) is not None:
            return False
        src = d.page_source or ""
        if "로그인이 필요합니다" in src:
            return False
        # 출석 버튼 후보가 하나라도 생기면 OK
        if len(d.find_elements(By.CSS_SELECTOR, "button.bt-att")) > 0:
            return True
        if "로그아웃" in src:
            return True
        return True  # 위 두 조건(로그인 버튼/필요문구)만 통과하면 일단 로그인 성공으로 처리

    wait.until(_logged_in_condition)
    logger.info("✅ 로그인 성공")


def ensure_login(driver, wait: WebDriverWait, logger: logging.Logger, user_id: str, password: str) -> None:
    if is_logged_in(driver):
        logger.info("ℹ️ 이미 로그인 상태(확인됨)")
        return

    logger.info("[LOGIN] need login")
    open_login_modal(driver, wait, logger)
    do_login(driver, wait, logger, user_id, password)

    # 로그인 후 출석 페이지로 다시 정착(리다이렉트/모달 닫힘 등 변수가 있음)
    safe_get(driver, logger, ATTENDANCE_URL)
    wait.until(lambda d: "출석부" in (d.page_source or ""))


# ----------------------------
# attendance flow
# ----------------------------
def is_today_in_att_list(driver) -> bool:
    today = kst_today_label()
    els = driver.find_elements(By.CSS_SELECTOR, "#list-att .lau .lau-my_date")
    return any(e.text.strip() == today for e in els)


def wait_today_in_att_list(driver, timeout: int = 20) -> None:
    today = kst_today_label()
    wait = WebDriverWait(driver, timeout)
    wait.until(
        lambda d: any(
            (el.text or "").strip() == today
            for el in d.find_elements(By.CSS_SELECTOR, "#list-att .lau .lau-my_date")
        )
    )


def find_attendance_button(driver):
    # 네가 준 버튼:
    # <button type="submit" class="slbt slbt--rect bt-att bt-submit" onclick="beCheckWrite(this)">출석</button>
    # 여러 후보로 잡음
    selectors = [
        "button.bt-att.bt-submit",
        "button.bt-att",
        "button[onclick*='beCheckWrite']",
        "button[onclick*=\"beCheckWrite\"]",
    ]
    for sel in selectors:
        els = driver.find_elements(By.CSS_SELECTOR, sel)
        if els:
            return els[0]

    # 텍스트로도 시도
    els = driver.find_elements(By.XPATH, "//button[contains(normalize-space(.), '출석')]")
    if els:
        return els[0]

    return None


def click_attendance_and_verify(driver, wait: WebDriverWait, logger: logging.Logger) -> str:
    # 이미 출석이면 커밋/클릭 다 하지 말아야 하니까 여기서 종료
    if is_today_in_att_list(driver):
        logger.info("✅ 오늘 출석 기록이 이미 존재함(중복 클릭 안 함)")
        return "already"

    # 출석 버튼 찾기
    # 페이지 로딩 안정화(동적 렌더 대비)
    wait.until(lambda d: "출석부" in (d.page_source or ""))

    btn = find_attendance_button(driver)
    if btn is None:
        # 혹시 어떤 탭/영역 클릭 후 버튼이 생기는 경우 대비: 화면 한번 스크롤
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(0.3)
        btn = find_attendance_button(driver)

    if btn is None:
        raise RuntimeError("출석 버튼을 찾지 못했습니다")

    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
    try:
        btn.click()
    except Exception:
        driver.execute_script("arguments[0].click();", btn)

    logger.info("✅ 출석 버튼 클릭")

    # 성공 판정: #list-att에 오늘 날짜 추가
    wait_today_in_att_list(driver, timeout=25)
    logger.info("✅ 출석 성공: 목록(#list-att)에 오늘 날짜가 추가됨")
    return "done"


# ----------------------------
# main
# ----------------------------
def main():
    logger = setup_logger()

    user_id = os.environ.get("EVERGREEN_ID", "").strip()
    user_pw = os.environ.get("EVERGREEN_PW", "").strip()
    if not user_id or not user_pw:
        logger.error("❌ EVERGREEN_ID / EVERGREEN_PW 환경변수가 비어있음")
        sys.exit(1)

    headless = os.environ.get("HEADLESS", "0").strip().lower() in ("1", "true", "yes")

    driver = None
    step = "INIT"

    try:
        driver = build_driver(headless=headless)
        wait = WebDriverWait(driver, 25)

        step = "OPEN_ATTENDANCE"
        safe_get(driver, logger, ATTENDANCE_URL)

        step = "ENSURE_LOGIN"
        ensure_login(driver, wait, logger, user_id, user_pw)

        step = "DO_ATTENDANCE"
        result = click_attendance_and_verify(driver, wait, logger)

        logger.info(f"RESULT={result}")
        # CI에서 쓰기 좋게 stdout에도 한 줄 고정 출력
        print(f"RESULT={result}")
        return 0

    except Exception as e:
        logger.error(f"❌ Exception at step={step} - {type(e).__name__}: {e}", exc_info=True)
        if driver:
            save_debug(driver, logger, reason=f"fail_{step}")
        print("RESULT=failed")
        return 1

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
