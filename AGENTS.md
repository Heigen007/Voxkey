# Notes for coding agents

Read this before changing anything. It is the short version of the decisions
that are easy to undo by accident.

## What this is

A Windows tray app: a global hotkey records the microphone, a hosted
speech-to-text API transcribes it, and the text is pasted into whatever input
had focus. Python 3.10+, packaged into one executable with PyInstaller.

## Setup

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m pytest -q
```

Run without packaging: `.venv\Scripts\pythonw.exe -m voxkey`
Build: `powershell -ExecutionPolicy Bypass -File build.ps1`

## Never do these

- **Never commit an API key, and never put one in a file.** The user enters it
  in the settings window; it is stored encrypted under `%APPDATA%\Voxkey`. If
  you need a key for a manual test, use the `VOXKEY_API_KEY` environment
  variable. Do not ask the user to paste a key into the chat.
- **Never commit a built binary.** Releases are produced by CI from a tag so
  the artifact can be traced to a commit. A hand-uploaded executable destroys
  the only guarantee this project offers.
- **Never suppress Enter or Esc outside a recording.** `hotkey.py` swallows
  them only while `is_recording()` is true. Break that and you have a program
  that eats Enter system-wide.
- **Never paste without confirming focus.** `inserter.insert_text` returns
  `CLIPBOARD_ONLY` when the original window cannot be brought back. Do not
  "improve" it into pasting anyway.
- **Never put user-visible text outside `strings.py`.** Translations depend on
  it being one file.

## Things that look wrong but are deliberate

- **`overlay.py` scales every coordinate by hand.** The process is made
  DPI-aware on purpose; without the manual scaling Windows bitmap-stretches
  the bar and the text blurs on any display above 100%.
- **`WS_EX_NOACTIVATE` on the overlay.** This is the single most important
  line in the project. The bar must never take focus.
- **`whisper-1` is the OpenAI default, not `gpt-4o-transcribe`.** The latter
  is a language model and can end a transcript early at a long pause,
  silently losing the rest of a dictation.
- **`cleanup()` swallows every exception and returns the original text.**
  Losing a dictation to a clean-up failure is far worse than filler words.
- **PowerShell scripts are ASCII-only.** Windows PowerShell 5.1 reads a `.ps1`
  without a BOM as ANSI, and non-ASCII characters break the parser, not just
  the output.
- **`_tick` reschedules itself from a `finally`, and `report_callback_exception`
  is wired to the logger.** This is the most important reliability line in
  `app.py`. Tk stops calling `after()` the moment a callback raises, which
  kills the event loop permanently — hooks keep firing, the tray icon stays,
  key presses pile up in a queue nobody reads. It looks exactly like "the
  hotkey stopped working" and leaves no trace, because Tk reports callback
  errors to a stderr a windowed build does not have. Never move the
  reschedule out of `finally`.
- **The hotkey watchdog re-registers the hooks after 60 s of silence.** Not
  paranoia: Windows silently removes a low-level keyboard hook whose callback
  overruns `LowLevelHooksTimeout` (300 ms), and the app cannot detect that.
  Observed in practice under heavy CPU load — the process kept running and
  the hotkey simply stopped. Silence is the only signal available, and
  re-arming while nobody types is free. Do not "optimise" this away.

## Layout

| File | Responsibility |
|---|---|
| `app.py` | State machine (idle → recording → transcribing), event queue, threads |
| `hotkey.py` | Global keyboard hooks and conditional suppression |
| `recorder.py` | Microphone → 16 kHz mono WAV in memory, plus capture diagnostics |
| `transcriber.py` | The only network calls in the project |
| `providers.py` | Provider registry; add a service by adding a row |
| `inserter.py` | Focus restoration, clipboard, Ctrl+V |
| `overlay.py` | The recording bar: DPI, drawing, never taking focus |
| `settings_window.py` | First-run setup and settings, including the self-test |
| `config.py` | Settings in `%APPDATA%\Voxkey\config.json` |
| `keystore.py` | DPAPI encryption for the API key |
| `tray.py` | Tray icon and menu |
| `strings.py` | Every user-visible string |

Threads: the main thread owns all UI (Tk); keyboard hooks and the tray run on
their own; each dictation gets a worker for the network call and the paste.
They communicate through one queue, and only the main thread touches the UI.

## Adding a provider

Add a `ProviderInfo` row to `PROVIDERS` in `providers.py`. If the service
speaks the OpenAI audio API, that is the entire change — `transcriber.py`
needs nothing. Add a case to `tests/test_providers.py`.
