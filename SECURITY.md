# Security

## Reporting a vulnerability

Open a [private security advisory](https://github.com/heigen007/voxkey/security/advisories/new).
Please do not open a public issue for anything exploitable.

## What this app can do, stated plainly

Voxkey installs a **global keyboard hook**, records your **microphone**, and
sends audio over the **network**. Any honest security review starts there,
because that is also the capability set of spyware.

What it does with those capabilities:

- The keyboard hook watches for exactly three keys: your hotkey, Enter and
  Escape. Enter and Escape are only intercepted while a recording is running.
  Keystrokes are never stored, buffered or transmitted. See
  [`hotkey.py`](src/voxkey/hotkey.py) — it is under 100 lines.
- The microphone is opened when you press the hotkey and closed when you stop.
  Audio lives in memory and is never written to disk.
- Exactly one module makes network requests:
  [`transcriber.py`](src/voxkey/transcriber.py). It posts to the endpoint in
  your settings. There is no other outbound traffic — no telemetry, no
  analytics, no update check.

## Your API key

- Stored in `%APPDATA%\Voxkey\config.json`, encrypted with Windows DPAPI and
  tied to your Windows account. Another user on the same machine, or the file
  copied elsewhere, cannot decrypt it.
- Never compiled into the binary. Released executables contain no credentials
  of any kind.
- Never logged. Logging is off by default; even when enabled the key is not
  written.
- If DPAPI is somehow unavailable, the key is stored in plain text **and
  labelled `"scheme": "plain"`** in the config, so the situation is visible
  rather than silently insecure.

## Verifying a release binary

Releases are built by GitHub Actions from a tagged commit, in public logs, and
signed with a build provenance attestation:

```
gh attestation verify Voxkey.exe --repo heigen007/voxkey
```

That ties the file to a specific commit and workflow run. No executable is
ever committed to the repository or uploaded by hand.

The binary is **not code-signed** with a commercial certificate, so Windows
SmartScreen will warn about it. That is a cost decision on a free project, not
a claim about safety — if it matters to you, build from source.
