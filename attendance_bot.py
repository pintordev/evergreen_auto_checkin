import os
import sys
import time
import shutil
import datetime
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


BASE_URL = "https://evergreenjb.me"
ATTENDANCE_URL = f"{BASE_URL}/attendance"

ART_DIR = Path("artifacts")
ART_DIR.mkdir(parents=True, exist_ok=True)


def kst_now() -> datetime.datetime:
    # Asia/Seoul = UTC+9 (DST 없음)
    return datetime.datetime.utcnow() + datetime.timedelta(hours=9)


def today_kst_day_str() -> str:
    # 예: "7일"
    return f"{kst_now().day}일"


def chrome_binary_guess() -> str | None:
    # setup-chrome action이 PATH에 넣는 경우도 있지만, 혹시 몰라서 후보들을 다 찾아봄
    candidates = [
        os.environ.get("CHROME_BIN"),
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        shutil.which("chrome"),
        "/opt/hostedtoolcache/setup-chrome/chromium/*/x64/chrome",
    ]
    for c in candidates:
        if not c:
            continue
        if "*" in c:
            # 글롭 패턴 처리
            from glob import glob
            hits = glob(c)
            if hits:
                return hits[0]
            continue
        if Path(c).exists():
            return c
    return None


def make_driver() -> webdriver.Chrome:
    opts = Options()
    # GitHub Actions: headless + sandbox 옵션 권장
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1280,720")
    opts.add_argument("--disable-gpu")

    bin_path = chrome_binary_guess()
    if bin_path:
        opts.binary_location = bin_path

    # Selenium 4.6+ : Selenium Manager가 드라이버를 자동 처리 (webdriver-manager 필요 없음)
    return webdriver.Chrome(options=opts)


def save_debug(driver: webdriver.Chrome, prefix: str) -> None:
    try:
        (ART_DIR / f"{prefix}.html").write_text(driver.page_source, encoding="utf-8", errors="ignore")
    except Exception:
        pass
    try:
        driver.save_screenshot(str(ART_DIR / f"{prefix}.png"))
    except Exception:
        pass


def visible(driver, by, value, timeout=15):
    return WebDriverWait(driver, timeout).until(EC.visibility_of_element_located((by, value)))


def clickable(driver, by, value, timeout=15):
    return WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((by, value)))


def login(driver: webdriver.Chrome, user_id: str, password: str) -> None:
    driver.get(BASE_URL)

    # 상단 로그인 버튼: <a class="bt-login ... onclick="slPop('sl-login')">로그인</a>
    login_btn = clickable(driver, By.CSS_SELECTOR, "a.bt-login.bt-login, a.bt-login.slbt")
    login_btn.click()

    # 모달은 DOM에 이미 존재하지만, 클릭 후 input이 "보이는 상태"가 되는 걸 기다림
    id_input = visible(driver, By.CSS_SELECTOR, "form[name='memberLogin'] input[name='user_id']")
    pw_input = visible(driver, By.CSS_SELECTOR, "form[name='memberLogin'] input[name='password']")

    id_input.clear()
    id_input.send_keys(user_id)
    pw_input.clear()
    pw_input.send_keys(password)

    # submit 버튼: <button type="submit" class="bt-login bt-submit">로그인</button>
    submit = clickable(driver, By.CSS_SELECTOR, "form[name='memberLogin'] button.bt-submit")
    submit.click()

    # 로그인 성공 여부는 헤더/페이지 변화로 판단 (사이트 상태에 따라 문구가 다를 수 있어 “로그인 버튼 사라짐” 기준도 같이 둠)
    WebDriverWait(driver, 15).until(
        lambda d: ("로그아웃" in d.page_source) or (len(d.find_elements(By.CSS_SELECTOR, "a.bt-login.slbt")) == 0)
    )


def already_attended_today(driver: webdriver.Chrome) -> bool:
    driver.get(ATTENDANCE_URL)

    # 출석 목록 영역이 뜨는지 확인
    visible(driver, By.CSS_SELECTOR, "#list-att", timeout=15)

    day_text = today_kst_day_str()

    # 이번달 내 출석 리스트에서 오늘 날짜가 있는지 검사
    items = driver.find_elements(By.CSS_SELECTOR, "#list-att .la-my li.lau .lau-my_date")
    for el in items:
        if day_text in (el.text or "").strip():
            return True
    return False


def click_attend(driver: webdriver.Chrome) -> None:
    driver.get(ATTENDANCE_URL)

    # 출석 버튼:
    # <button type="submit" class="slbt slbt--rect bt-att bt-submit" onclick="beCheckWrite(this)">출석</button>
    btn = clickable(driver, By.CSS_SELECTOR, "button.bt-att.bt-submit", timeout=15)
    btn.click()

    # 클릭 후 오늘 날짜가 리스트에 생길 때까지 대기
    day_text = today_kst_day_str()
    WebDriverWait(driver, 15).until(
        lambda d: any(day_text in (x.text or "") for x in d.find_elements(By.CSS_SELECTOR, "#list-att .lau-my_date"))
    )


def main() -> int:
    user_id = os.environ.get("EVERGREEN_ID")
    user_pw = os.environ.get("EVERGREEN_PW")

    if not user_id or not user_pw:
        print("❌ 환경변수 EVERGREEN_ID / EVERGREEN_PW 가 비어있음")
        print("RESULT=fail")
        return 2

    driver = make_driver()
    try:
        login(driver, user_id, user_pw)
        print("✅ 로그인 성공")

        if already_attended_today(driver):
            print("✅ 오늘 출석 기록이 이미 존재함(중복 클릭 안 함)")
            print("RESULT=already")
            return 0

        click_attend(driver)
        print("✅ 출석 완료")
        print("RESULT=success")
        return 0

    except Exception as e:
        print(f"❌ 실패: {type(e).__name__} - {e}")
        save_debug(driver, "debug")
        print("RESULT=fail")
        return 1

    finally:
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
