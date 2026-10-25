import json
import socket
import threading
import time
from pathlib import Path

from PIL import Image, ImageStat

ROOT = Path(__file__).resolve().parent.parent
import os
import urllib.request

PORT = int(os.environ.get("BACKFLOW_PORT", 8765))
BASE = f"http://127.0.0.1:{PORT}"


def _port_open(port):
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _is_ours(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/index.html", timeout=1) as r:
            return b"Backflow harness" in r.read()
    except Exception:
        return False


def _ensure_server():
    """Reuse our server if running; otherwise start one (next free port if 8765 belongs to another app)."""
    global PORT, BASE
    port = PORT
    while _port_open(port) and not _is_ours(port):
        port += 1
    if port != PORT:
        print(f"port {PORT} is used by another app, using {port}")
    PORT, BASE = port, f"http://127.0.0.1:{port}"
    if _port_open(port):
        return
    import uvicorn
    from backend.server import app

    cfg = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(cfg)
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if _port_open(port):
            return
        time.sleep(0.05)
    raise RuntimeError("could not start server on port %d" % port)


def _check_frame(path):
    im = Image.open(path).convert("L")
    st = ImageStat.Stat(im)
    if st.mean[0] < 3 or st.stddev[0] < 2:
        raise RuntimeError(f"blank or black frame: {path} (mean={st.mean[0]:.1f}, std={st.stddev[0]:.1f})")


class Renderer:
    def __init__(self, width=854, height=480):
        self.site = {}
        self.patch = {}
        self.w, self.h = width, height
        self.pw = self.browser = self.page = None
        self.scene_url = None
        self.depths_key = None
        self.gl_mode = None

    def _launch(self, args):
        self.browser = self.pw.chromium.launch(headless=True, args=args)
        self.page = self.browser.new_page(viewport={"width": self.w, "height": self.h})
        self.page.on("pageerror", lambda e: print("page error:", e))
        self._goto_harness()

    def _goto_harness(self, attempts=3):
        """Load the harness page, retrying with backoff; the page and Three.js are served locally."""
        last = None
        for i in range(attempts):
            try:
                self.page.goto(BASE + "/index.html", wait_until="load", timeout=20000)
                self.page.wait_for_function("typeof window.loadScene === 'function'", timeout=30000)
                return
            except Exception as e:
                last = e
                print(f"harness load failed (attempt {i + 1}/{attempts}): {type(e).__name__}: {str(e)[:200]}")
                if i < attempts - 1:
                    time.sleep(2 * 2 ** i)
        raise RuntimeError(
            f"could not load the harness at {BASE}/index.html after {attempts} attempts. "
            f"Check that the server is running and web/vendor/three/build/three.module.js exists. Last error: {last}")

    def start(self):
        from playwright.sync_api import sync_playwright

        _ensure_server()
        self.pw = sync_playwright().start()
        self.gl_mode = "metal"
        self._launch(["--use-angle=metal", "--ignore-gpu-blocklist"])
        return self

    def _fallback_swiftshader(self):
        self.browser.close()
        self.gl_mode = "swiftshader"
        self._launch(["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
        self.scene_url = None
        self.depths_key = None

    def _load(self, scene_url, depths):
        if scene_url != self.scene_url:
            url = scene_url if scene_url.startswith(("http", "/")) else "/" + scene_url
            self.page.evaluate("async ([u, s]) => { await window.loadScene(u, s); }", [url, self.site])
            self.page.wait_for_function("window.ready === true", timeout=30000)
            self.scene_url = scene_url
        if isinstance(depths, (str, Path)):
            depths = json.loads(Path(depths).read_text())
        key = json.dumps(depths, sort_keys=True)
        if key != self.depths_key:
            self.page.evaluate("d => window.loadDepths(d)", depths)
            self.depths_key = key

    def render(self, scene_url, depths_path_or_dict, cam, times_s, out_dir):
        if self.page is None:
            self.start()
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        for attempt in range(2):
            try:
                self._load(scene_url, depths_path_or_dict)
                self.page.evaluate("p => window.applyPatch(p)", self.patch)
                self.page.evaluate("c => window.setCamera(c)", cam)
                paths = []
                for t in times_s:
                    self.page.evaluate("t => { window.setStep(t); window.renderNow(); }", t)
                    p = out_dir / f"{cam}_t{int(round(t)):05d}.png"
                    self.page.locator("canvas").screenshot(path=str(p))
                    _check_frame(p)
                    paths.append(str(p))
                return paths
            except RuntimeError as e:
                if attempt == 0 and self.gl_mode == "metal" and "blank" in str(e):
                    self._fallback_swiftshader()
                    continue
                raise

    def close(self):
        if self.browser:
            self.browser.close()
        if self.pw:
            self.pw.stop()
        self.page = self.browser = self.pw = None


    def describe(self, scene_url):
        if self.page is None:
            self.start()
        self._load(scene_url, {"t": [0], "depth_m": {}})
        return self.page.evaluate("() => window.describeScene()")
