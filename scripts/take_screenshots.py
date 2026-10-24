#!/usr/bin/env python3
"""Capture automated 1440x900 screenshots of the dashboard and Airflow via Chrome DevTools Protocol."""

import asyncio
import base64
import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path
import websockets

ROOT = Path(__file__).resolve().parent.parent
SCREENSHOTS_DIR = ROOT / "docs" / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

CHROME_PORT = 9222

PAGES = [
    ("dashboard", "http://localhost:5173/"),
    ("analytics", "http://localhost:5173/analytics"),
    ("changes", "http://localhost:5173/changes"),
    ("products", "http://localhost:5173/products"),
    ("pipeline", "http://localhost:5173/pipeline"),
    ("quality", "http://localhost:5173/quality"),
    ("sources", "http://localhost:5173/sources"),
]

def get_token() -> str:
    url = "http://localhost:8000/api/v1/auth/login"
    data = json.dumps({"email": "admin@example.com", "password": "Admin@12345"}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())["access_token"]

async def send_cmd(ws, method, params=None, msg_id=1):
    payload = {"id": msg_id, "method": method, "params": params or {}}
    await ws.send(json.dumps(payload))
    while True:
        resp = json.loads(await ws.recv())
        if resp.get("id") == msg_id:
            return resp.get("result", {})

async def capture_all():
    token = get_token()
    print("Obtained admin token.")

    # Start Chrome headless
    chrome_proc = subprocess.Popen([
        "/usr/bin/google-chrome",
        "--headless=new",
        "--no-sandbox",
        "--disable-gpu",
        f"--remote-debugging-port={CHROME_PORT}",
        "--window-size=1440,900",
        "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    time.sleep(2)

    try:
        # Get target websocket URL
        tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{CHROME_PORT}/json").read())
        ws_url = tabs[0]["webSocketDebuggerUrl"]

        async with websockets.connect(ws_url, max_size=20_000_000) as ws:
            # Enable Page and Runtime
            await send_cmd(ws, "Page.enable", msg_id=1)
            await send_cmd(ws, "Runtime.enable", msg_id=2)
            await send_cmd(ws, "Emulation.setDeviceMetricsOverride", {
                "width": 1440,
                "height": 900,
                "deviceScaleFactor": 1,
                "mobile": False,
            }, msg_id=3)

            # Navigate to base domain to set localStorage
            await send_cmd(ws, "Page.navigate", {"url": "http://localhost:5173/"}, msg_id=4)
            await asyncio.sleep(1.5)

            # Inject token and dark theme
            setup_script = f"""
            localStorage.setItem('pip.token', {json.dumps(token)});
            localStorage.setItem('pip.theme', 'dark');
            document.documentElement.classList.add('dark');
            """
            await send_cmd(ws, "Runtime.evaluate", {"expression": setup_script}, msg_id=5)
            await asyncio.sleep(0.5)

            # Capture dashboard pages
            req_id = 10
            for name, url in PAGES:
                print(f"Capturing {name} -> {url}...")
                req_id += 1
                await send_cmd(ws, "Page.navigate", {"url": url}, msg_id=req_id)
                # Wait for API fetch and chart rendering
                await asyncio.sleep(3.0)

                req_id += 1
                res = await send_cmd(ws, "Page.captureScreenshot", {"format": "png"}, msg_id=req_id)
                img_data = base64.b64decode(res["data"])
                out_path = SCREENSHOTS_DIR / f"{name}-dark.png"
                out_path.write_bytes(img_data)
                print(f"Saved {out_path.name} ({len(img_data) // 1024} KB)")

            # Now capture Airflow
            # Login to Airflow or visit directly
            print("Capturing Airflow Graph...")
            req_id += 1
            airflow_graph_url = "http://admin:admin@localhost:8080/dags/product_intelligence_pipeline/graph"
            await send_cmd(ws, "Page.navigate", {"url": airflow_graph_url}, msg_id=req_id)
            await asyncio.sleep(4.0)
            req_id += 1
            res = await send_cmd(ws, "Page.captureScreenshot", {"format": "png"}, msg_id=req_id)
            img_data = base64.b64decode(res["data"])
            out_path = SCREENSHOTS_DIR / "airflow-graph.png"
            out_path.write_bytes(img_data)
            print(f"Saved {out_path.name} ({len(img_data) // 1024} KB)")

            print("Capturing Airflow Grid...")
            req_id += 1
            airflow_grid_url = "http://admin:admin@localhost:8080/dags/product_intelligence_pipeline/grid"
            await send_cmd(ws, "Page.navigate", {"url": airflow_grid_url}, msg_id=req_id)
            await asyncio.sleep(4.0)
            req_id += 1
            res = await send_cmd(ws, "Page.captureScreenshot", {"format": "png"}, msg_id=req_id)
            img_data = base64.b64decode(res["data"])
            out_path = SCREENSHOTS_DIR / "airflow-grid.png"
            out_path.write_bytes(img_data)
            print(f"Saved {out_path.name} ({len(img_data) // 1024} KB)")

    finally:
        chrome_proc.terminate()
        chrome_proc.wait()

if __name__ == "__main__":
    asyncio.run(capture_all())
