# Contributing

Thanks for looking. Small, focused pull requests get merged fastest.

## Getting set up

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m pytest -q
```

Run the app without packaging: `.venv\Scripts\pythonw.exe -m voxkey`

You will need Windows. The keyboard hook, focus handling and key storage are
all Win32 — there is no meaningful way to develop this on another OS.

## Before opening a pull request

- `pytest -q` passes.
- New behaviour has a test. The suite deliberately needs no microphone and no
  network, so keep it that way: capture requests with a fake `requests.post`
  rather than calling a real endpoint.
- User-visible strings go in `src/voxkey/strings.py`, not inline.
- Read [AGENTS.md](AGENTS.md). It lists the handful of things that look like
  bugs but are load-bearing.

## Especially welcome

**Translations.** Copy `strings.py`, translate the values, and describe how
you would like language selection to work — there is no i18n mechanism yet and
the first translation gets to shape it.

**Providers.** If a service implements the OpenAI audio API, adding it is one
row in `providers.py` plus a test.

**A demo GIF.** The README has a slot for one at `docs/demo.gif`.

## Things that are out of scope

- **Other operating systems.** Not because they do not matter, but because a
  half-working macOS port is worse than none. A serious port is a fork or a
  long conversation, not a pull request.
- **Local/offline models.** Deliberate: the whole point of this project is
  being 30 MB with nothing to download. Excellent local-first alternatives
  already exist.
- **Telemetry or update checks.** Never.

## Reporting a bug

Turn logging on first — settings, or `"log": true` in
`%APPDATA%\Voxkey\config.json` — reproduce, then attach the relevant lines
from `%APPDATA%\Voxkey\voxkey.log`.

The log is designed to answer the common question directly. This line:

```
app: take 31.2s audio / 31.4s open, 975 KB, xruns=0
```

says how much audio actually arrived versus how long the recording was open.
If those numbers diverge, a `CAPTURE GAP` warning follows and the microphone
stream is at fault. If they match but the transcript is short, the model
truncated it.
