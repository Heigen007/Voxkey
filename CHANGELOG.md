# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.1] - 2026-08-01

### Fixed

- **The hotkey could silently stop working.** Windows removes a low-level
  keyboard hook whose callback overruns `LowLevelHooksTimeout` (300 ms) and
  tells nobody: the process keeps running, the tray icon stays put, and key
  presses simply stop arriving. A Python callback on a machine under heavy
  load can overrun that, and it was reproduced doing exactly that. A watchdog
  now re-registers the hooks after 60 seconds without a single key event —
  by definition nobody is typing at that moment, so there is no gap during
  real work and no synthetic keystrokes are needed.

## [0.1.0] - 2026-08-01

First public release.

### Added

- Hotkey dictation into any Windows input: record, transcribe, paste at the
  cursor.
- A recording bar that never takes focus (`WS_EX_NOACTIVATE`) and is DPI-aware
  on high-resolution displays.
- Stop with `Enter` or the hotkey, cancel with `Esc`. Both keys are suppressed
  only while recording, so they behave normally the rest of the time.
- Providers: Groq, OpenAI, and any OpenAI-compatible endpoint including
  keyless self-hosted servers.
- A settings window with a **Test** button that records three seconds and
  shows the transcription, so setup verifies itself.
- API key encrypted per Windows account with DPAPI; settings in
  `%APPDATA%\Voxkey`.
- Optional LLM clean-up pass that removes filler words and fixes punctuation.
- Start with Windows, toggled from the tray — a Startup shortcut, no registry
  and no admin rights.
- Refuses to paste into the wrong window: if focus cannot be restored the
  transcript is left on the clipboard instead.
- Optional diagnostics that distinguish a lost microphone stream from a
  truncated transcription.
- Releases built by CI from a tag, with build provenance attestation and
  SHA256. No binary is committed to the repository.

[Unreleased]: https://github.com/Heigen007/Voxkey/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/Heigen007/Voxkey/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/Heigen007/Voxkey/releases/tag/v0.1.0
