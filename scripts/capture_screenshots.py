#!/usr/bin/env python3
"""Capture high-resolution dark mode screenshots of dashboard screens and Airflow UI."""

from __future__ import annotations

import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

ROOT = Path(__file__).resolve().parents[1]
SCREENSHOTS_DIR = ROOT / "docs" / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)


def main():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1440,900")

    driver = webdriver.Chrome(options=options)
    driver.set_window_size(1440, 900)

    try:
        print("Navigating to login page...")
        driver.get("http://localhost:5173/login")
        time.sleep(2)

        # Login to Dashboard
        email_input = driver.find_element(By.CSS_SELECTOR, "input[type='email']")
        password_input = driver.find_element(By.CSS_SELECTOR, "input[type='password']")
        email_input.clear()
        email_input.send_keys("admin@example.com")
        password_input.clear()
        password_input.send_keys("Admin@12345")

        submit_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        submit_btn.click()
        print("Logged in, waiting for dashboard...")
        time.sleep(3)

        # Ensure dark theme is applied
        driver.execute_script(
            "localStorage.setItem('pip.theme', 'dark'); "
            "document.documentElement.dataset.theme = 'dark'; "
            "document.documentElement.classList.add('dark');"
        )
        time.sleep(1)

        screens = [
            ("http://localhost:5173/", SCREENSHOTS_DIR / "dashboard-dark.png"),
            ("http://localhost:5173/analytics", SCREENSHOTS_DIR / "analytics-dark.png"),
            ("http://localhost:5173/changes", SCREENSHOTS_DIR / "changes-dark.png"),
            ("http://localhost:5173/products", SCREENSHOTS_DIR / "products-dark.png"),
            ("http://localhost:5173/pipeline", SCREENSHOTS_DIR / "pipeline-dark.png"),
            ("http://localhost:5173/quality", SCREENSHOTS_DIR / "quality-dark.png"),
            ("http://localhost:5173/sources", SCREENSHOTS_DIR / "sources-dark.png"),
        ]

        for url, path in screens:
            print(f"Capturing {url} -> {path.name}...")
            driver.get(url)
            driver.execute_script(
                "document.documentElement.dataset.theme = 'dark'; "
                "document.documentElement.classList.add('dark');"
            )
            time.sleep(3)
            driver.save_screenshot(str(path))
            print(f"Saved: {path.name} ({path.stat().st_size} bytes)")

        # Log into Airflow UI
        print("Navigating to Airflow UI...")
        driver.get("http://localhost:8080/login/")
        time.sleep(2)

        try:
            af_user = driver.find_element(By.CSS_SELECTOR, "input[name='username']")
            af_pass = driver.find_element(By.CSS_SELECTOR, "input[name='password']")
            af_user.clear()
            af_user.send_keys("admin")
            af_pass.clear()
            af_pass.send_keys("admin")
            driver.find_element(By.CSS_SELECTOR, "form").submit()
            time.sleep(3)
        except Exception as e:
            print(f"Airflow login form not found or already logged in: {e}")

        # Graph view
        print("Capturing Airflow Graph view...")
        driver.get("http://localhost:8080/dags/product_intelligence_pipeline/graph")
        time.sleep(4)
        graph_path = SCREENSHOTS_DIR / "airflow-graph.png"
        driver.save_screenshot(str(graph_path))
        print(f"Saved: {graph_path.name} ({graph_path.stat().st_size} bytes)")

        # Grid view
        print("Capturing Airflow Grid view...")
        driver.get("http://localhost:8080/dags/product_intelligence_pipeline/grid")
        time.sleep(4)
        grid_path = SCREENSHOTS_DIR / "airflow-grid.png"
        driver.save_screenshot(str(grid_path))
        print(f"Saved: {grid_path.name} ({grid_path.stat().st_size} bytes)")

    finally:
        driver.quit()

    print("All screenshots captured successfully!")


if __name__ == "__main__":
    main()
