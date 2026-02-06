import time
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException


URL = "https://evergreenjb.me/attendance"


# -------------------------
# README 기록 함수
# -------------------------
def update_readme(message: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{now} | {message}\n"

    with open("README.md", "a", encoding="utf-8") as f:
        f.write(line)


# -------------------------
# 크롬 옵션
# -------------------------
def create_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")

    return webdriver.Chrome(options=options)


# -------------------------
# 메인 로직
# -------------------------
def main():
    driver = create_driver()
    wait = WebDriverWait(driver, 5)

    try:
        driver.get(URL)

        # ✅ 출석 버튼 기다렸다가 클릭
        btn = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "버튼셀렉터"))
        )

        btn.click()
        time.sleep(2)

        print("✅ 출석 체크 성공")
        update_readme("✅ 출석 체크 성공")

    # -------------------------
    # 이미 출석한 경우 (정상)
    # -------------------------
    except (TimeoutException, NoSuchElementException):
        print("ℹ️ 이미 출석 완료 → 스킵")
        # 🔥 README 기록 안 함

    # -------------------------
    # 진짜 에러만 기록
    # -------------------------
    except Exception as e:
        print("🚨 시스템 에러:", e)
        update_readme(f"🚨 시스템 에러: {e}")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
