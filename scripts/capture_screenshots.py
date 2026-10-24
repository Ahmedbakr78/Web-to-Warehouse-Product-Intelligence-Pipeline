#!/usr/bin/env python3
"""Capture high-resolution screenshots of the dashboard and Airflow UI for docs."""

from __future__ import annotations

import asyncio
import base64
import json
import subprocess
from pathlib import Path

import httpx
import websockets

ROOT = Path(__file__).resolve().parents[1]
SCREENSHOTS_DIR = ROOT / "docs" / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

CHROME_BIN = "/usr/bin/google-chrome"
CDP_PORT = 9222


async def get_token() -> str:
    async with httpx.AsyncClient() as client:
        res = await client.post(
            "http://localhost:8000/api/v1/auth/login",
            json={"email": "admin@example.com", "password": "Admin@12345"},
            timeout=10,
        )
        data = res.json()
        return data.get("access_token", "")


class CDPClient:
    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self.ws: websockets.WebSocketClientProtocol | None = None
        self._msg_id = 0

    async def connect(self):
        self.ws = await websockets.connect(self.ws_url, max_size=50 * 1024 * 1024)

    async def send(self, method: str, params: dict | None = None) -> dict:
        self._msg_id += 1
        msg = {"id": self._msg_id, "method": method, "params": params or {}}
        await self.ws.send(json.dumps(msg))
        while True:
            resp_raw = await self.ws.recv()
            resp = json.loads(resp_raw)
            if resp.get("id") == self._msg_id:
                return resp

    async def close(self):
        if self.ws:
            await self.ws.close()


async def capture_page(cdp: CDPClient, url: str, output_path: Path, wait_sec: float = 2.5):
    print(f"Navigating to {url}...")
    await cdp.send("Page.navigate", {"url": url})
    await asyncio.sleep(wait_sec)
    res = await cdp.send("Page.captureScreenshot", {"format": "png"})
    b64_data = res.get("result", {}).get("data", "")
    if b64_data:
        output_path.write_bytes(base64.b64decode(b64_data))
        print(f"Saved: {output_path} ({len(b64_data)} bytes base64)")
    else:
        print(f"Failed to capture screenshot for {url}: {res}")


async def main():
    token = await get_token()
    if not token:
        print("Error: Could not retrieve auth token from API")
        return 1

    chrome_cmd = [
        CHROME_BIN,
        "--headless=new",
        f"--remote-debugging-port={CDP_PORT}",
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--window-size=1440,900",
    ]
    proc = subprocess.Popen(chrome_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("Launched headless Chrome on port", CDP_PORT)
    await asyncio.sleep(1.5)

    try:
        async with httpx.AsyncClient() as client:
            pages = (await client.get(f"http://127.0.0.1:{CDP_PORT}/json", timeout=5)).json()
            ws_url = pages[0]["webSocketDebuggerUrl"]

        cdp = CDPClient(ws_url)
        await cdp.connect()

        # Set device metrics to 1440x900
        await cdp.send("Page.enable")
        await cdp.send(
            "Emulation.setDeviceMetricsOverride",
            {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False},
        )

        # Inject auth token and dark mode into localStorage
        await cdp.send("Page.navigate", {"url": "http://localhost:5173/login"})
        await asyncio.sleep(1.5)
        inject_script = (
            f"localStorage.setItem('pip.token', '{token}'); "
            "localStorage.setItem('pip.theme', 'dark'); "
            "document.documentElement.dataset.theme = 'dark'; "
            "document.documentElement.classList.add('dark');"
        )
        await cdp.send("Runtime.evaluate", {"expression": inject_script})

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
            await capture_page(cdp, url, path, wait_sec=2.5)

        # Now capture Airflow UI
        print("Logging into Airflow UI...")
        await cdp.send("Page.navigate", {"url": "http://localhost:8080/login/"})
        await asyncio.sleep(2.0)
        airflow_login_script = (
            "document.querySelector('input[name=username]').value = 'admin'; "
            "document.querySelector('input[name=password]').value = 'admin'; "
            "document.querySelector('form').submit();"
        )
        await cdp.send("Runtime.evaluate", {"expression": airflow_login_script})
        await asyncio.sleep(3.0)

        await capture_page(
            cdp,
            "http://localhost:8080/dags/product_intelligence_pipeline/graph",
            SCREENSHOTS_DIR / "airflow-graph.png",
            wait_sec=3.5,
        )
        await capture_page(
            cdp,
            "http://localhost:8080/dags/product_intelligence_pipeline/grid",
            SCREENSHOTS_DIR / "airflow-grid.png",
            wait_sec=3.5,
        )

        await cdp.close()
    finally:
        proc.terminate()
        proc.wait()

    print("Finished capturing all screenshots successfully!")
    return 0


if __name__ == "__main__":
    asyncio.run(main())
