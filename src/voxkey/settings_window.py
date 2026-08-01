"""The settings window, and the whole of first-run setup.

Design goal: someone who has never seen a terminal can go from a downloaded
executable to working dictation without reading documentation. That is what
the Test button is for - it records three seconds and shows what came back,
so setup verifies itself instead of failing silently later.
"""

from __future__ import annotations

import dataclasses
import logging
import threading
import tkinter as tk
import webbrowser
from collections.abc import Callable
from tkinter import ttk

from . import autostart, config, providers, strings, transcriber
from .recorder import Recorder, RecorderError

logger = logging.getLogger(__name__)

TEST_SECONDS = 3.0
PAD = 8


class SettingsWindow:
    """A Toplevel bound to the app's Tk root. Only one may exist at a time."""

    _open: SettingsWindow | None = None

    def __init__(
        self,
        root: tk.Tk,
        settings: config.Settings,
        on_saved: Callable[[config.Settings], None],
    ) -> None:
        self._settings = settings
        self._on_saved = on_saved
        self._testing = False

        self.window = tk.Toplevel(root)
        self.window.title(strings.SETTINGS_TITLE.format(app=strings.APP_NAME))
        self.window.resizable(False, False)
        self.window.protocol('WM_DELETE_WINDOW', self.close)

        self._provider = tk.StringVar(value=providers.get(settings.provider).label)
        self._api_key = tk.StringVar(value=settings.api_key)
        self._base_url = tk.StringVar(value=settings.base_url)
        self._model = tk.StringVar(value=settings.model)
        self._language = tk.StringVar(value=settings.language)
        self._vocabulary = tk.StringVar(value=settings.vocabulary)
        self._hotkey = tk.StringVar(value=settings.hotkey)
        self._cleanup = tk.BooleanVar(value=settings.cleanup)
        self._autostart = tk.BooleanVar(value=autostart.is_enabled())
        self._show_key = tk.BooleanVar(value=False)
        self._status = tk.StringVar(value='')

        self._build()
        self._on_provider_change()
        SettingsWindow._open = self

    # -- public ----------------------------------------------------------

    @classmethod
    def show(
        cls,
        root: tk.Tk,
        settings: config.Settings,
        on_saved: Callable[[config.Settings], None],
    ) -> SettingsWindow:
        """Open the window, or raise the one already open."""
        existing = cls._open
        if existing is not None and existing.window.winfo_exists():
            existing.window.deiconify()
            existing.window.lift()
            existing.window.focus_force()
            return existing
        return cls(root, settings, on_saved)

    def close(self) -> None:
        SettingsWindow._open = None
        self.window.destroy()

    # -- layout ----------------------------------------------------------

    def _build(self) -> None:
        frame = ttk.Frame(self.window, padding=16)
        frame.grid(sticky='nsew')
        frame.columnconfigure(1, weight=1)
        row = _Rows()

        ttk.Label(frame, text=strings.SETTINGS_WELCOME, wraplength=460, foreground='#555').grid(
            row=row.next(), column=0, columnspan=3, sticky='w', pady=(0, PAD * 2)
        )

        # provider
        current = row.next()
        ttk.Label(frame, text=strings.SETTINGS_PROVIDER).grid(row=current, column=0, sticky='w')
        combo = ttk.Combobox(
            frame, textvariable=self._provider, values=providers.labels(), state='readonly', width=32
        )
        combo.grid(row=current, column=1, sticky='ew', pady=2)
        combo.bind('<<ComboboxSelected>>', lambda _event: self._on_provider_change())
        self._key_button = ttk.Button(frame, text=strings.SETTINGS_GET_KEY, command=self._open_signup)
        self._key_button.grid(row=current, column=2, sticky='w', padx=(PAD, 0))

        self._notes = ttk.Label(frame, text='', wraplength=460, foreground='#777')
        self._notes.grid(row=row.next(), column=1, columnspan=2, sticky='w', pady=(0, PAD))

        # api key
        current = row.next()
        ttk.Label(frame, text=strings.SETTINGS_API_KEY).grid(row=current, column=0, sticky='w')
        self._key_entry = ttk.Entry(frame, textvariable=self._api_key, show='*', width=34)
        self._key_entry.grid(row=current, column=1, sticky='ew', pady=2)
        ttk.Checkbutton(
            frame, text=strings.SETTINGS_SHOW_KEY, variable=self._show_key, command=self._toggle_key
        ).grid(row=current, column=2, sticky='w', padx=(PAD, 0))

        # custom endpoint - shown only for providers that allow one
        self._url_row = row.next()
        self._url_label = ttk.Label(frame, text=strings.SETTINGS_BASE_URL)
        self._url_entry = ttk.Entry(frame, textvariable=self._base_url)

        current = row.next()
        ttk.Label(frame, text=strings.SETTINGS_MODEL).grid(row=current, column=0, sticky='w')
        self._model_combo = ttk.Combobox(frame, textvariable=self._model, width=32)
        self._model_combo.grid(row=current, column=1, sticky='ew', pady=2)

        self._field(frame, row, strings.SETTINGS_LANGUAGE, self._language, strings.SETTINGS_LANGUAGE_HELP)
        self._field(frame, row, strings.SETTINGS_VOCABULARY, self._vocabulary, strings.SETTINGS_VOCABULARY_HELP)
        self._field(frame, row, strings.SETTINGS_HOTKEY, self._hotkey, strings.SETTINGS_HOTKEY_HELP)

        ttk.Checkbutton(frame, text=strings.SETTINGS_CLEANUP, variable=self._cleanup).grid(
            row=row.next(), column=0, columnspan=3, sticky='w', pady=(PAD, 0)
        )
        ttk.Checkbutton(frame, text=strings.SETTINGS_AUTOSTART, variable=self._autostart).grid(
            row=row.next(), column=0, columnspan=3, sticky='w'
        )

        ttk.Separator(frame).grid(row=row.next(), column=0, columnspan=3, sticky='ew', pady=PAD * 2)

        current = row.next()
        self._test_button = ttk.Button(frame, text=strings.SETTINGS_TEST, command=self._run_test)
        self._test_button.grid(row=current, column=0, sticky='w')
        ttk.Label(frame, textvariable=self._status, wraplength=380).grid(
            row=current, column=1, columnspan=2, sticky='w'
        )

        buttons = ttk.Frame(frame)
        buttons.grid(row=row.next(), column=0, columnspan=3, sticky='e', pady=(PAD * 2, 0))
        ttk.Button(buttons, text=strings.SETTINGS_CANCEL, command=self.close).grid(row=0, column=0)
        ttk.Button(buttons, text=strings.SETTINGS_SAVE, command=self._save).grid(
            row=0, column=1, padx=(PAD, 0)
        )

    def _field(self, frame: ttk.Frame, row: _Rows, label: str, var: tk.StringVar, help_text: str) -> None:
        current = row.next()
        ttk.Label(frame, text=label).grid(row=current, column=0, sticky='w')
        ttk.Entry(frame, textvariable=var).grid(row=current, column=1, sticky='ew', pady=2)
        ttk.Label(frame, text=help_text, foreground='#777', font=('Segoe UI', 8)).grid(
            row=row.next(), column=1, columnspan=2, sticky='w', pady=(0, 4)
        )

    # -- behaviour -------------------------------------------------------

    def _toggle_key(self) -> None:
        self._key_entry.configure(show='' if self._show_key.get() else '*')

    def _provider_key(self) -> str:
        return providers.key_for_label(self._provider.get())

    def _open_signup(self) -> None:
        url = providers.get(self._provider_key()).signup_url
        if url:
            webbrowser.open(url)

    def _on_provider_change(self) -> None:
        info = providers.get(self._provider_key())
        self._notes.configure(text=info.notes)
        self._key_button.configure(state='normal' if info.signup_url else 'disabled')
        self._model_combo.configure(values=list(info.models))
        if self._model.get() not in info.models and not info.editable_base_url:
            self._model.set(info.default_model)

        if info.editable_base_url:
            self._url_label.grid(row=self._url_row, column=0, sticky='w')
            self._url_entry.grid(row=self._url_row, column=1, columnspan=2, sticky='ew', pady=2)
        else:
            self._url_label.grid_remove()
            self._url_entry.grid_remove()

    def _collect(self) -> config.Settings:
        return dataclasses.replace(
            self._settings,
            provider=self._provider_key(),
            api_key=self._api_key.get().strip(),
            base_url=self._base_url.get().strip(),
            model=self._model.get().strip(),
            language=self._language.get().strip(),
            vocabulary=self._vocabulary.get().strip(),
            hotkey=self._hotkey.get().strip().lower() or config.DEFAULT_HOTKEY,
            cleanup=self._cleanup.get(),
            autostart=self._autostart.get(),
        )

    def _save(self) -> None:
        settings = self._collect()
        config.save(settings)
        autostart.apply(settings.autostart)
        self._status.set(strings.SETTINGS_SAVED)
        self._on_saved(settings)
        self.close()

    # -- the self-check --------------------------------------------------

    def _run_test(self) -> None:
        if self._testing:
            return
        settings = self._collect()
        if not settings.is_configured:
            self._status.set(strings.SETTINGS_TEST_NEEDS_KEY)
            return

        self._testing = True
        self._test_button.configure(state='disabled')
        self._status.set(strings.SETTINGS_TESTING)
        threading.Thread(target=self._test_worker, args=(settings,), daemon=True).start()

    def _test_worker(self, settings: config.Settings) -> None:
        """Record a few seconds and run them through the real pipeline."""
        try:
            recorder = Recorder(config.SAMPLE_RATE, settings.max_seconds)
            recorder.start()
            threading.Event().wait(TEST_SECONDS)
            wav = recorder.stop()

            label = providers.get(settings.provider).label
            self._post(strings.SETTINGS_TEST_SENDING.format(provider=label))
            text = transcriber.transcribe(wav, settings)
            self._post(strings.SETTINGS_TEST_OK.format(text=text[:80]))
        except transcriber.TranscriptionError as error:
            if str(error) == strings.ERROR_NO_SPEECH:
                self._post(strings.SETTINGS_TEST_EMPTY)
            else:
                self._post(strings.SETTINGS_TEST_FAILED.format(reason=error))
        except RecorderError as error:
            self._post(strings.SETTINGS_TEST_FAILED.format(reason=error))
        except Exception as error:  # noqa: BLE001 - a failed test must not kill the window
            logger.exception('settings: test failed')
            self._post(strings.SETTINGS_TEST_FAILED.format(reason=error))
        finally:
            self._post_done()

    def _post(self, message: str) -> None:
        if self.window.winfo_exists():
            self.window.after(0, lambda: self._status.set(message))

    def _post_done(self) -> None:
        def finish() -> None:
            self._testing = False
            if self.window.winfo_exists():
                self._test_button.configure(state='normal')

        if self.window.winfo_exists():
            self.window.after(0, finish)


class _Rows:
    """Hands out consecutive grid row numbers so layout edits stay painless."""

    def __init__(self) -> None:
        self._current = -1

    def next(self) -> int:
        self._current += 1
        return self._current
