# Third-party notices

hermes-motion itself is licensed under the MIT License (see `LICENSE`). It depends on the
components below. Licences are those of the upstream projects; verify against the versions you
actually install.

No model weights, fonts, or media assets are committed to this repository. Models and (optional)
voices are downloaded into a user cache directory at install/first-use time; nothing here
redistributes them.

## Runtime dependencies

| Component | Used for | Licence |
|-----------|----------|---------|
| Playwright | Drives headless Chromium | Apache-2.0 |
| Chromium (downloaded by Playwright) | Renders scenes | BSD-style and other open-source licences (see Chromium's `LICENSE`) |
| kokoro-onnx | Kokoro TTS wrapper | MIT |
| Kokoro-82M model weights | Default TTS model | Apache-2.0 |
| onnxruntime | Runs the Kokoro ONNX model | MIT |
| numpy | Audio maths, palette k-means | BSD-3-Clause |
| soundfile | Read/write WAV | BSD-3-Clause |
| PyYAML | Parse config / storyboards | MIT |
| jsonschema | Storyboard validation | MIT |
| ffmpeg / ffprobe | Encoding, probing, reference analysis | Invoked as an **external program**, not bundled. ffmpeg builds are LGPL-2.1+ or GPL-2.0+ depending on how they were compiled (e.g. `libx264` builds are GPL). Install and license it separately. |

## Optional extra: Piper TTS

| Component | Licence | Notes |
|-----------|---------|-------|
| piper-tts | MIT | Install with `uv sync --extra piper`. |
| espeak-ng data used by piper-tts 1.x | GPL-3.0 | piper-tts 1.x bundles/uses espeak-ng phoneme data. This is an **optional extra**, downloaded at the user's install time and **not redistributed** by this repository. Installing it is the user's choice; if the GPL-3.0 terms matter to you, skip the Piper extra. |

## Piper voice models

Piper voices (for example `en_GB-alan-medium`, from the `rhasspy/piper-voices` collection on
Hugging Face) are downloaded on first use. Each voice has its own licence, stated in that voice's
model card; licences vary between voices and voices are added/changed by their authors. Check the
model card for the specific voice you use before redistributing anything derived from it. This
repository does not bundle or relicense any voice, and makes no blanket licence claim for them.

## Windows SAPI

The `sapi` TTS provider uses speech voices already installed on the user's Windows machine via
`System.Speech`. Those voices come with the OS and/or were installed by the user; they are
governed by their own terms and are not bundled here.

## Fonts

No fonts are bundled. Every preset uses a system font stack (Segoe UI on Windows, with generic
`serif`/`monospace`/`sans-serif` fallbacks), so rendering depends only on fonts already present
on the host.

The optional `renderer.fonts_dir` config loads `.ttf/.otf/.woff/.woff2` files from a folder the
user supplies, via `@font-face`. Those fonts are the user's responsibility to license; open
fonts under the SIL Open Font License (OFL) are a good fit.

## Reference analysis

`motion analyze-ref` extracts only abstract aggregate traits (palette, pacing, loudness) from
user-supplied clips; it stores no footage, frames, or text from them. Respect the copyright of
any clip you analyse.
