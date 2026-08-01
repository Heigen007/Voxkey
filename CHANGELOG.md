# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.3] - 2026-08-01

### Fixed

- **The app could go deaf: hotkey pressed, nothing happens, nothing logged.**
  Tk stops rescheduling `after()` callbacks as soon as one raises, which
  killed the event loop for good — the keyboard hooks kept running and key
  presses kept landing in a queue that nobody read again. It left no trace
  because Tk writes callback errors to stderr, and a windowed build has none.
  The tick now reschedules from a `finally` and cannot die, and
  `report_callback_exception` goes to the log.
- **A locked clipboard crashed a dictation.** Any process can hold the
  Windows clipboard open for a moment; a write during that window raises, and
  the spoken text was lost with an unexplained error. Writes now retry with a
  short backoff, and a genuine failure is reported as such.
- Unexpected failures name the exception on the bar instead of pointing at a
  log file that is disabled by default.

## [0.1.2] - 2026-08-01

### Fixed

- **One key press could fire the hotkey twice**, starting a recording and
  stopping it in the same instant — the bar flashed "Too short" and nothing
  was transcribed. Introduced by the watchdog in 0.1.1: the two registrations
  it re-creates live in different registries inside the `keyboard` library
  and need different removal calls (`remove_hotkey` for the hotkey, `unhook`
  for the blocking hook). The wrong call raised `KeyError`, which was being
  swallowed, so every re-arm stacked another live hotkey on top of the last.

  Removal now uses the right call for each registration and logs a failure
  instead of hiding it. **Anyone on 0.1.1 should update.**

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

[Unreleased]: https://github.com/Heigen007/Voxkey/compare/v0.1.3...HEAD
[0.1.3]: https://github.com/Heigen007/Voxkey/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/Heigen007/Voxkey/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/Heigen007/Voxkey/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/Heigen007/Voxkey/releases/tag/v0.1.0
