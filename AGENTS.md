# AGENTS.md — hard rules for anyone (human or bot) working on hermes-motion

1. Read SPEC.md first. It is the source of truth. Ask via a kanban comment if something blocks you; don't silently change decisions.
2. PUBLIC repo: never commit secrets, tokens, personal paths, personal data, or downloaded model weights/fonts/media. Cache models outside the repo.
3. Free and local by default. No paid APIs, no keys required to render a video.
4. Modular: every stage sits behind a provider interface and is selectable via motion.config.yaml. No hard-coded provider.
5. Python via `uv` only (no global pip). Windows is the primary dev machine; keep Linux/macOS working where cheap (no Windows-only code outside clearly marked fallbacks).
6. Deterministic rendering: scenes are seeked by time, never recorded in real time.
7. Don't touch Hermes config, other repos, or other bots' profiles.
8. Report with real tool output (ffprobe, volumedetect, test runs). Never claim success you didn't observe.
9. Keep commits small and meaningful; keep README and docs updated with the code.
