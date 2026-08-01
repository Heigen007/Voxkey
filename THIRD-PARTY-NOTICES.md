# Third-party licenses

Voxkey itself is MIT. A released executable bundles the following libraries.

| Library | License | Used for |
|---|---|---|
| [sounddevice](https://github.com/spatialaudio/python-sounddevice) | MIT | Microphone capture (bundles PortAudio, MIT) |
| [numpy](https://numpy.org/) | BSD-3-Clause | Audio buffers and level metering |
| [keyboard](https://github.com/boppreh/keyboard) | MIT | Global keyboard hooks |
| [requests](https://requests.readthedocs.io/) | Apache-2.0 | HTTP calls to the speech-to-text provider |
| [pyperclip](https://github.com/asweigart/pyperclip) | BSD-3-Clause | Clipboard access |
| [Pillow](https://python-pillow.org/) | MIT-CMU | Drawing the tray and application icons |
| [pystray](https://github.com/moses-palmer/pystray) | **LGPL-3.0** | System tray icon and menu |

## A note on pystray and the LGPL

pystray is the one dependency that is not permissively licensed. LGPL-3.0
allows use in a project under a different license, but requires that a
recipient be able to replace the LGPL component and relink the result.

This is satisfied here: the entire source of Voxkey is published under MIT,
the exact build steps are in [`build.ps1`](build.ps1) and run in public CI, and
pystray is an ordinary pip dependency declared in
[`pyproject.toml`](pyproject.toml). Anyone may modify or substitute pystray and
rebuild the executable with a single command.

If you distribute a modified binary, keep this notice with it.
