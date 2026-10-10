# Third-party notices

hermes-motion itself is licensed under the MIT License (see `LICENSE`). It depends on the
components below. Licences are those stated by the upstream projects or read from the installed
package metadata; verify against the versions you actually install. Anything not checked is
marked **UNVERIFIED**.

No model weights, fonts, or media assets are committed to this repository. Models and voices are
downloaded into a user cache directory at install/first-use time; nothing here redistributes them.

## Important: the default install pulls in GPL components

`kokoro-onnx` (the default TTS) requires `phonemizer` and `espeakng-loader`. Both are installed by
a plain `uv sync`, no extras. They are loaded at runtime when Kokoro runs. This repository contains
none of their code and does not redistribute them, but a default environment does contain GPL
software. See "Licence implications" in the README.

## Runtime dependencies (installed by default)

Versions are the ones in `uv.lock` / the checked environment at the time of writing.

| Component | Used for | Licence | How verified |
|-----------|----------|---------|--------------|
| Playwright (1.63.0) | Drives headless Chromium | Apache-2.0 | package metadata |
| Chromium (downloaded by Playwright) | Renders scenes | BSD-style and other open-source licences (see Chromium's `LICENSE`) | UNVERIFIED (not re-read) |
| kokoro-onnx (0.6.1) | Kokoro TTS wrapper | MIT | `LICENSE` file in the wheel |
| **phonemizer (3.4.0)** | Text to phonemes, required by kokoro-onnx | **GPL-3.0-or-later** | package metadata (classifier GPLv3+) |
| **espeakng-loader (0.2.4)** | Loads a bundled eSpeak NG library, required by kokoro-onnx | package metadata has **no licence field**; the wheel ships `espeak-ng.dll` and `espeak-ng-data`, and eSpeak NG is **GPL-3.0** upstream | wheel contents checked; the licence is from the upstream espeak-ng project, UNVERIFIED in the wheel itself |
| Kokoro-82M model weights | Default TTS voice | Apache-2.0 (Hugging Face model card for `hexgrad/Kokoro-82M` lists `apache-2.0`) | HF model metadata |
| onnxruntime (1.31.0) | Runs the ONNX models | MIT | package metadata |
| numpy (2.5.3) | Audio maths, palette k-means | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | package metadata |
| soundfile (0.14.0) | Read/write WAV | BSD-3-Clause | package metadata |
| PyYAML (6.0.3) | Parse config | MIT | package metadata |
| jsonschema (4.26.0) | Storyboard validation | MIT | package metadata |
| ffmpeg / ffprobe | Encoding, probing, reference analysis | Invoked as an **external program**, not bundled. Builds are LGPL-2.1+ or GPL-2.0+ depending on how they were compiled (e.g. `libx264` builds are GPL). Install and license it separately. | general knowledge, UNVERIFIED for your build |

### Where the Kokoro files come from

The two Kokoro files (`kokoro-v1.0.onnx`, `voices-v1.0.bin`) are downloaded from the
**thewh1teagle/kokoro-onnx GitHub release `model-files-v1.0`**, a third-party conversion of the
original weights, not from hexgrad's own repository. Both are verified by SHA-256 after download.
The Apache-2.0 statement above is from the upstream `hexgrad/Kokoro-82M` model card; whether the
ONNX conversion carries any additional terms is **UNVERIFIED**.

## Optional extra: Piper TTS (`uv sync --extra piper`)

| Component | Licence | Notes |
|-----------|---------|-------|
| **piper-tts (1.8.0)** | **GPL-3.0-or-later** | Package metadata says `License: GPL-3.0-or-later` (an earlier version of this file said MIT; that was wrong). Installed only if you ask for the extra. |

The Piper extra adds nothing new in kind: the default install already contains GPL components
(see above). Skipping the Piper extra does **not** remove GPL software from the environment.

## Piper voice models (downloaded on first use)

Voices come from the `rhasspy/piper-voices` Hugging Face repository, fetched at the pinned commit
`c10ece1aade47bb51c153c893d14e5bf8e5b7117` and verified by SHA-256. The collection's top-level
metadata says `license: mit`, but each voice's model card points at the licence of the dataset it
was trained on, and those differ. What the cards (read at that commit) actually say:

| Voice (used in the registry) | Card says | Dataset licence |
|------------------------------|-----------|-----------------|
| `en_US-ryan-medium` | License: **CC BY-NC-SA 4.0** (dataset: RyanSpeech on Kaggle) | **Non-commercial, share-alike, attribution.** Do not use for commercial output. |
| `en_GB-jenny_dioco-medium` | "License: See URL" (dataset: `dioco-group/jenny-tts-dataset`) | That README says: attribution required in software that generates audio with this dataset (call the voice "Jenny" / "Jenny (Dioco)"), commercial use permitted, no further restrictions. Read from the README, not from the model card. |
| `en_GB-alan-medium` | "License: See URL" (dataset: `MycroftAI/mimic3-voices`, `en_UK/apope_low`) | The `mimic3-voices` repository shows a CC-BY-SA-4.0 licence file. The page for this specific voice could not be fetched, so the per-voice dataset licence is **UNVERIFIED**. |
| `en_US-amy-medium` | "License: See URL" (dataset: `MycroftAI/mimic3-voices`) | Same repository-level CC-BY-SA-4.0; the per-voice dataset licence is **UNVERIFIED**. |

Treat any voice you did not read the card for as unknown. This repository does not bundle or
relicense any voice and makes no blanket licence claim for them.

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
