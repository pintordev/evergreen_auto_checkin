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

    # 1. 봇 감지 우회 설정
    opts.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    opts.add_argument('--disable-blink-features=AutomationControlled')
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option('useAutomationExtension', False)

    # 2. 리눅스/GitHub Actions 환경 필수 설정
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    if headless:
        opts.add_argument('--headless')

    driver = webdriver.Chrome(options=opts)

    # 3. 추가 우회 (navigator.webdriver 속성 제거)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    return driver

def page_is_403(driver) -> bool:
    src = (driver.page_source or "").lower()
    title = (driver.title or "").lower()
    return ("403 forbidden" in src) or ("403 forbidden" in title)

def safe_get(driver, logger: logging.Logger, url: str) -> None:
    logger.info(f"[GET] {url}")
    driver.get(url)
    time.sleep(1) # 페이지 안정화를 위해 대기 시간 소폭 증가
    if page_is_403(driver):
        raise RuntimeError(f"403_forbidden ({url})")

# ----------------------------
# login detection / login flow
# ----------------------------
def find_login_button(driver):
    cands = driver.find_elements(By.CSS_SELECTOR, "a.bt-login")
    for a in cands:
        try:
            txt = (a.text or "").strip()
            oc = (a.get_attribute("onclick") or "")
            if "로그인" in txt or "slPop('sl-login')" in oc:
                return a
        except Exception:
            pass
    return None

def is_logged_in(driver) -> bool:
    if find_login_button(driver) is not None:
        return False
    src = driver.page_source or ""
    if "로그인이 필요합니다" in src:
        return False
    # 보안 로그인 페이지인 경우(user_id 필드 존재)도 비로그인으로 간주
    if len(driver.find_elements(By.ID, "user_id")) > 0:
        return False
    if ("로그아웃" in src) or ("마이" in src and "메뉴" in src):
        return True
    return False

def open_login_modal(driver, wait: WebDriverWait, logger: logging.Logger) -> None:
    btn = find_login_button(driver)
    if btn is None:
        links = driver.find_elements(By.XPATH, "//a[contains(normalize-space(.), '로그인')]")
        btn = links[0] if links else None

    if btn is None:
        raise RuntimeError("로그인 버튼을 찾지 못했습니다")

    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
    try:
        btn.click()
    except Exception:
        driver.execute_script("arguments[0].click();", btn)

    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "form[name='memberLogin']")))
    logger.info("[LOGIN] modal opened")

def ensure_login(driver, wait: WebDriverWait, logger: logging.Logger, user_id: str, password: str) -> None:
    if is_logged_in(driver):
        logger.info("ℹ️ 이미 로그인 상태(확인됨)")
        return

    logger.info("[LOGIN] need login")
    
    # [수정] 보안 로그인 페이지(전체 화면 로그인)인지 확인
    direct_id_input = driver.find_elements(By.ID, "user_id")
    
    if direct_id_input:
        logger.info("[LOGIN] 보안 로그인 페이지 감지 - 직접 입력 시도")
        id_field = direct_id_input[0]
        pw_field = driver.find_element(By.ID, "password")
        submit_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        
        id_field.clear()
        id_field.send_keys(user_id)
        pw_field.clear()
        pw_field.send_keys(password)
        submit_btn.click()
    else:
        # 기존 모달 방식
        open_login_modal(driver, wait, logger)
        form = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "form[name='memberLogin']")))
        id_input = form.find_element(By.CSS_SELECTOR, "input[name='user_id']")
        pw_input = form.find_element(By.CSS_SELECTOR, "input[name='password']")
        submit_btn = form.find_element(By.CSS_SELECTOR, "button.bt-login.bt-submit[type='submit']")
        
        id_input.clear()
        id_input.send_keys(user_id)
        pw_input.clear()
        pw_input.send_keys(password)
        submit_btn.click()

    # 로그인 성공 여부 확인 대기
    time.sleep(2)
    safe_get(driver, logger, ATTENDANCE_URL)
    wait.until(lambda d: "출석부" in (d.page_source or "") or "로그아웃" in (d.page_source or ""))
    logger.info("✅ 로그인 프로세스 완료")

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
    selectors = [
        "button.bt-att.bt-submit",
        "button.bt-att",
        "button[onclick*='beCheckWrite']",
    ]
    for sel in selectors:
        els = driver.find_elements(By.CSS_SELECTOR, sel)
        if els:
            return els[0]
    els = driver.find_elements(By.XPATH, "//button[contains(normalize-space(.), '출석')]")
    return els[0] if els else None

def click_attendance_and_verify(driver, wait: WebDriverWait, logger: logging.Logger) -> str:
    if is_today_in_att_list(driver):
        logger.info("✅ 오늘 출석 기록이 이미 존재함")
        return "already"

    wait.until(lambda d: "출석부" in (d.page_source or ""))
    btn = find_attendance_button(driver)
    
    if btn is None:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(0.5)
        btn = find_attendance_button(driver)

    if btn is None:
        raise RuntimeError("출석 버튼을 찾지 못했습니다")

    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
    try:
        btn.click()
    except Exception:
        driver.execute_script("arguments[0].click();", btn)

    logger.info("✅ 출석 버튼 클릭 완료")
    wait_today_in_att_list(driver, timeout=25)
    return "done"

# ----------------------------
# main
# ----------------------------
def main():
    logger = setup_logger()
    user_id = os.environ.get("EVERGREEN_ID", "").strip()
    user_pw = os.environ.get("EVERGREEN_PW", "").strip()
    
    if not user_id or not user_pw:
        logger.error("❌ 환경변수(EVERGREEN_ID/PW) 설정 확인 필요")
        return 1

    headless = os.environ.get("HEADLESS", "1").strip().lower() in ("1", "true", "yes")
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

        logger.info(f"FINAL_RESULT={result}")
        print(f"RESULT={result}")
        return 0

    except Exception as e:
        logger.error(f"❌ 오류 단계: {step} - {e}")
        if driver:
            save_debug(driver, logger, reason=f"fail_{step}")
        print("RESULT=failed")
        return 1
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    sys.exit(main())