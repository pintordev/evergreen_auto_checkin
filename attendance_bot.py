import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


KST = ZoneInfo("Asia/Seoul")


@dataclass
class Result:
    result: str  # success | already | failed
    points: int | None = None
    message: str | None = None


def _now_kst() -> datetime:
    return datetime.now(tz=KST)


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _write_text(path: str, text: str) -> None:
    _ensure_dir(os.path.dirname(path) or ".")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _append_text(path: str, text: str) -> None:
    _ensure_dir(os.path.dirname(path) or ".")
    with open(path, "a", encoding="utf-8") as f:
        f.write(text)


def _update_readme_latest(line: str) -> None:
    readme_path = "README.md"
    if not os.path.exists(readme_path):
        return

    with open(readme_path, "r", encoding="utf-8") as f:
        content = f.read()

    start = "<!-- CHECKIN_STATUS_START -->"
    end = "<!-- CHECKIN_STATUS_END -->"
    if start not in content or end not in content:
        return

    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
    repl = f"{start}\n- {line}\n{end}"
    new_content = pattern.sub(repl, content, count=1)
    if new_content != content:
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(new_content)


def _setup_driver() -> webdriver.Chrome:
    options = Options()
    if os.getenv("HEADLESS", "1") == "1":
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1400,900")

    # If GitHub Actions provides CHROMEDRIVER_PATH, prefer it.
    chromedriver_path = os.getenv("CHROMEDRIVER_PATH")
    if chromedriver_path and os.path.exists(chromedriver_path):
        service = Service(executable_path=chromedriver_path)
    else:
        service = Service()  # Selenium Manager fallback

    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(int(os.getenv("PAGELOAD_TIMEOUT", "45")))
    return driver


def _dump_debug(driver: webdriver.Chrome, tag: str) -> None:
    out_dir = os.getenv("ARTIFACT_DIR", "artifacts")
    _ensure_dir(out_dir)

    # meta
    meta = {
        "tag": tag,
        "ts_kst": _now_kst().isoformat(),
        "url": getattr(driver, "current_url", None),
        "title": getattr(driver, "title", None),
    }
    _write_text(os.path.join(out_dir, f"meta_{tag}.json"), json.dumps(meta, ensure_ascii=False, indent=2))

    # page html
    try:
        _write_text(os.path.join(out_dir, f"page_{tag}.html"), driver.page_source)
    except Exception:
        pass

    # screenshot
    try:
        driver.save_screenshot(os.path.join(out_dir, f"shot_{tag}.png"))
    except Exception:
        pass

    # key nodes (best-effort)
    def outer_html(selector: tuple[str, str]) -> str | None:
        try:
            el = driver.find_element(*selector)
            return el.get_attribute("outerHTML")
        except Exception:
            return None

    snippets: dict[str, str] = {}
    candidates = {
        "login_button": (By.CSS_SELECTOR, "a.bt-login"),
        "login_form": (By.CSS_SELECTOR, "form[name='memberLogin']"),
        "id_input": (By.CSS_SELECTOR, "form[name='memberLogin'] input[name='user_id']"),
        "pw_input": (By.CSS_SELECTOR, "form[name='memberLogin'] input[name='password']"),
        "login_submit": (By.CSS_SELECTOR, "form[name='memberLogin'] button.bt-login.bt-submit"),
        "att_button": (By.CSS_SELECTOR, "button.bt-att"),
        "list_att": (By.CSS_SELECTOR, "#list-att"),
    }
    for k, sel in candidates.items():
        html = outer_html(sel)
        if html:
            snippets[k] = html
    if snippets:
        _write_text(
            os.path.join(out_dir, f"dom_{tag}.json"),
            json.dumps(snippets, ensure_ascii=False, indent=2),
        )


def _wait(driver: webdriver.Chrome, seconds: int | None = None) -> WebDriverWait:
    return WebDriverWait(driver, seconds or int(os.getenv("WAIT_TIMEOUT", "20")))


def login(driver: webdriver.Chrome, base_url: str) -> None:
    driver.get(base_url)
    _dump_debug(driver, "01_open")

    # Click header login button to make modal visible.
    try:
        btn = _wait(driver).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a.bt-login")))
        btn.click()
    except TimeoutException:
        # Modal exists in DOM, so proceed anyway.
        pass

    # Wait inputs visible
    id_input = _wait(driver).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, "form[name='memberLogin'] input[name='user_id']"))
    )
    pw_input = _wait(driver).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, "form[name='memberLogin'] input[name='password']"))
    )
    id_input.clear()
    id_input.send_keys(os.environ["EVERGREEN_ID"])
    pw_input.clear()
    pw_input.send_keys(os.environ["EVERGREEN_PW"])

    _dump_debug(driver, "02_filled")

    submit = _wait(driver).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "form[name='memberLogin'] button.bt-login.bt-submit"))
    )
    submit.click()

    # login success heuristic: header shows logout OR cookie-auth keeps the form hidden
    _wait(driver, int(os.getenv("LOGIN_POST_WAIT", "25"))).until(
        lambda d: "로그아웃" in d.page_source or "memberLogin" not in d.page_source
    )
    _dump_debug(driver, "03_logged_in")


def _today_kst_day() -> int:
    return _now_kst().day


def _extract_points_from_today_block(list_att_html: str, day: int) -> int | None:
    # Try to locate "{day}일" block then extract +NN.
    # This is best-effort and tolerant to markup changes.
    m = re.search(rf">\s*{day}\s*일\s*<.*?class=\"lau-point.*?\".*?\+(\d+)", list_att_html, re.DOTALL)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def checkin(driver: webdriver.Chrome, attendance_url: str) -> Result:
    driver.get(attendance_url)
    _dump_debug(driver, "10_attendance_open")

    day = _today_kst_day()

    # Wait list area present (it exists even if empty)
    list_att = _wait(driver).until(EC.presence_of_element_located((By.CSS_SELECTOR, "#list-att")))
    list_html = list_att.get_attribute("outerHTML") or ""
    if f"{day}일" in list_html:
        pts = _extract_points_from_today_block(list_html, day)
        return Result(result="already", points=pts, message="오늘 출석 기록이 이미 존재")

    # Click attendance button
    btn = _wait(driver).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.bt-att")))
    btn.click()
    _dump_debug(driver, "11_clicked")

    # Wait until today's record appears
    def appeared(d: webdriver.Chrome) -> bool:
        try:
            el = d.find_element(By.CSS_SELECTOR, "#list-att")
            return f"{day}일" in (el.get_attribute("outerHTML") or "")
        except Exception:
            return False

    _wait(driver, int(os.getenv("CHECKIN_POST_WAIT", "25"))).until(appeared)
    _dump_debug(driver, "12_checked")

    list_html2 = driver.find_element(By.CSS_SELECTOR, "#list-att").get_attribute("outerHTML") or ""
    pts = _extract_points_from_today_block(list_html2, day)
    return Result(result="success", points=pts, message="출석 완료")


def persist(result: Result) -> None:
    ts = _now_kst()
    payload = {
        "ts_kst": ts.isoformat(),
        "result": result.result,
        "points": result.points,
        "message": result.message,
    }

    out_dir = os.getenv("ARTIFACT_DIR", "artifacts")
    _ensure_dir(out_dir)
    _write_text(os.path.join(out_dir, "result.json"), json.dumps(payload, ensure_ascii=False, indent=2))

    line = f"{ts.strftime('%Y-%m-%d %H:%M:%S')} KST | {result.result}"
    if result.points is not None:
        line += f" | +{result.points}"
    if result.message:
        line += f" | {result.message}"
    line += "\n"
    _write_text(os.path.join(out_dir, "summary.txt"), line)

    if os.getenv("WRITE_LOG", "1") == "1":
        _append_text("checkin_log.md", f"- {line}")
        _update_readme_latest(line.strip())


def main() -> int:
    base_url = os.getenv("EVERGREEN_BASE_URL", "https://evergreenarts.co.kr")
    attendance_url = os.getenv("EVERGREEN_ATTENDANCE_URL", base_url.rstrip("/") + "/attendance")

    driver = None
    try:
        driver = _setup_driver()
        login(driver, base_url)
        print("✅ 로그인 성공")
        res = checkin(driver, attendance_url)
        if res.result == "already":
            print("✅ 오늘 출석 기록이 이미 존재함(중복 클릭 안 함)")
        elif res.result == "success":
            print("✅ 출석 완료")
        else:
            print("❌ 출석 실패")
        persist(res)
        print(f"RESULT={res.result}")
        return 0
    except TimeoutException as e:
        if driver:
            _dump_debug(driver, "99_timeout")
        persist(Result(result="failed", message=f"TimeoutException: {e}"))
        print(f"❌ 실패: TimeoutException - {e}")
        return 1
    except Exception as e:
        if driver:
            _dump_debug(driver, "99_error")
        persist(Result(result="failed", message=f"{type(e).__name__}: {e}"))
        print(f"❌ 실패: {type(e).__name__} - {e}")
        return 1
    finally:
        try:
            if driver:
                driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
