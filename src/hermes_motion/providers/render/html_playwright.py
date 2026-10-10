"""Default renderer: headless Chromium (Playwright) stepping window.__seek(t) frame by frame."""
from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import unquote, urlparse

from ..base import ProviderUnavailable


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

    def available(self) -> tuple[bool, str]:
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
        ok, why = self.available()
        if not ok:
            raise ProviderUnavailable(why)
        frames_dir.mkdir(parents=True, exist_ok=True)
        n = int(round(total_seconds * fps))
        return asyncio.run(self._render(Path(scene_html), n, fps, size, frames_dir))

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
