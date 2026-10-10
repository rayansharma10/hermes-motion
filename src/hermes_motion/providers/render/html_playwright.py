"""Default renderer: headless Chromium (Playwright) stepping window.__seek(t) frame by frame."""
from __future__ import annotations

import asyncio
import shutil
import threading
from pathlib import Path
from urllib.parse import unquote, urlparse

from ..base import ProviderUnavailable


def _run_in_thread(fn):
    """Run a blocking callable on a helper thread (which has no running event loop)."""
    box: dict = {}

    def target():
        try:
            box["value"] = fn()
        except BaseException as e:  # re-raised in the caller
            box["error"] = e

    t = threading.Thread(target=target)
    t.start()
    t.join()
    if "error" in box:
        raise box["error"]
    return box["value"]


def request_allowed(url: str, roots: list[Path]) -> bool:
    """True for data: URLs and for file: URLs inside one of ``roots``; everything else is blocked."""
    u = urlparse(url)
    if u.scheme in ("data", "about", "blob"):
        return True
    if u.scheme != "file":
        return False
    path = unquote(u.path)
    if len(path) > 2 and path[0] == "/" and path[2] == ":":  # file:///C:/x on Windows
        path = path[1:]
    try:
        p = Path(path).resolve()
    except (OSError, ValueError):
        return False
    return any(p == r or r in p.parents for r in roots)


class HtmlPlaywrightRenderer:
    name = "html-playwright"

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self._avail: tuple[bool, str] | None = None

    def available(self) -> tuple[bool, str]:
        if self._avail is not None:  # starting a Playwright driver is slow; ask once per instance
            return self._avail
        self._avail = self._check_available()
        return self._avail

    def _check_available(self) -> tuple[bool, str]:
        try:
            from playwright.sync_api import sync_playwright
        except Exception as e:
            return False, f"playwright not importable: {e}"
        try:
            with sync_playwright() as p:
                path = p.chromium.executable_path
            if not Path(path).exists():
                return False, "Chromium not installed: run `uv run playwright install chromium`"
        except Exception as e:
            return False, f"playwright error: {e}"
        return True, f"ok ({path})"

    def render(self, scene_html: Path, total_seconds: float, fps: int,
               size: tuple[int, int], frames_dir: Path) -> int:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return self._render_sync(scene_html, total_seconds, fps, size, frames_dir)
        # called from inside a running event loop (notebook, async bot): Playwright's sync API and
        # asyncio.run both refuse that, so do the whole render on a helper thread
        return _run_in_thread(lambda: self._render_sync(scene_html, total_seconds, fps, size, frames_dir))

    def _render_sync(self, scene_html: Path, total_seconds: float, fps: int,
                     size: tuple[int, int], frames_dir: Path) -> int:
        ok, why = self.available()
        if not ok:
            raise ProviderUnavailable(why)
        frames_dir.mkdir(parents=True, exist_ok=True)
        n = int(round(total_seconds * fps))
        self._check_disk(frames_dir, n)
        try:
            return asyncio.run(self._render(Path(scene_html), n, fps, size, frames_dir))
        except ProviderUnavailable:
            raise
        except Exception as e:
            raise ProviderUnavailable(f"rendering failed: {type(e).__name__}: {e}") from e

    def _check_disk(self, frames_dir: Path, n_frames: int) -> None:
        rcfg = self.cfg.get("renderer", {})
        per_frame = 1.5e6 if rcfg.get("frame_format", "jpeg") == "png" else 0.2e6  # conservative lower bounds
        need = n_frames * per_frame
        try:
            free = shutil.disk_usage(frames_dir).free
        except OSError:
            return
        if free < need:
            raise ProviderUnavailable(
                f"not enough free disk space for {n_frames} frames in {frames_dir.parent}: need about "
                f"{need / 1e9:.1f} GB, have {free / 1e9:.1f} GB; free some space or set pipeline.tmp_dir "
                f"to another drive")

    async def _render(self, page_path: Path, n_frames: int, fps: int, size, frames_dir: Path) -> int:
        from playwright.async_api import async_playwright
        rcfg = self.cfg.get("renderer", {})
        fmt = rcfg.get("frame_format", "jpeg")
        ext = "jpg" if fmt == "jpeg" else "png"
        workers = max(1, int(self.cfg.get("pipeline", {}).get("workers", 3)))
        workers = min(workers, n_frames) or 1
        url = page_path.resolve().as_uri()
        allowed_roots = [page_path.resolve().parent]
        if rcfg.get("fonts_dir"):
            allowed_roots.append(Path(rcfg["fonts_dir"]).expanduser().resolve())
        shot_opts = {"type": fmt}
        if fmt == "jpeg":
            shot_opts["quality"] = int(rcfg.get("jpeg_quality", 95))

        async with async_playwright() as p:
            browser = await p.chromium.launch(args=["--force-color-profile=srgb", "--disable-lcd-text"])

            async def worker(idx: int):
                ctx = await browser.new_context(viewport={"width": size[0], "height": size[1]},
                                                device_scale_factor=1)
                # Scenes may contain untrusted `custom` HTML: no network, no local files except
                # the page's own folder (and the configured fonts folder).
                await ctx.route("**/*", lambda route: route.continue_()
                                if request_allowed(route.request.url, allowed_roots) else route.abort())
                page = await ctx.new_page()
                await page.goto(url)
                await page.evaluate("window.__ready")
                for i in range(idx, n_frames, workers):
                    await page.evaluate("t => window.__seek(t)", i / fps)
                    await page.screenshot(path=str(frames_dir / f"{i:06d}.{ext}"), **shot_opts)
                await ctx.close()

            await asyncio.gather(*(worker(w) for w in range(workers)))
            await browser.close()
        return n_frames
