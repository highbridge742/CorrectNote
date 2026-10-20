# -*- coding: utf-8 -*-
"""The word book hotkey really registers and toggles the word book (2026-10-20 うにさん「単語帳が
ショートカットキーで呼び出せなくなった」 — the cause was the View menu's 「単語帳のオン・オフ」, which
switches the hotkey itself, saved as off; the registration path was unchanged). RegisterHotKey is
done for real: with a spare combination of keys, a WM_HOTKEY posted to the hotkey thread reaches
the app, and the app's queue toggles the word book. The real combinations are registered too when
nothing else holds them (then released at once)."""
import queue
import sys
import time
import unittest
from unittest.mock import Mock, patch

import hotkeys
import settings


@unittest.skipUnless(sys.platform == 'win32', 'RegisterHotKey')
class WordBookHotkeyTests(unittest.TestCase):
    def wait(self, predicate, seconds=3):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if predicate():
                return True
            time.sleep(0.01)
        return False

    def test_label_and_setting(self):
        self.assertEqual(hotkeys.HOTKEY_LABELS['wordbook'], 'Ctrl+Alt+Insert / Ctrl+Alt+Shift+-')
        self.assertTrue(settings.DEFAULTS['hotkey_wordbook_enabled'])
        s = settings.Settings()
        self.assertIn(('wordbook', 'Ctrl+Alt+Insert / Ctrl+Alt+Shift+-'), settings.active_hotkeys(s))
        s.set('hotkey_wordbook_enabled', False)
        self.assertNotIn('wordbook', [name for name, _ in settings.active_hotkeys(s)])
        # The View menu items switch the hotkeys: 「…ホットキー有効化」 with the keys on the right
        # (2026-10-20: 「単語帳のオン・オフ（…）」 read as a command to open the word book)
        from pathlib import Path
        import app
        source = Path(app.__file__).read_text(encoding='utf-8')
        self.assertIn("label='単語帳ホットキー有効化', accelerator='Ctrl+Alt+Insert / Ctrl+Alt+Shift+-'", source)
        self.assertIn("label='簡易入力ホットキー有効化', accelerator='Ctrl+Insert'", source)
        self.assertIn("label='簡易入力ホットキー有効化', accelerator='Ctrl+Shift+-'", source)
        self.assertIn("m_edit.add_command(label='単語帳を開く／閉じる',", source)
        self.assertNotIn("label='単語帳のオン・オフ", source)

    def test_a_registered_hotkey_reaches_the_app(self):
        # Spare keys (Ctrl+Alt+Shift+F13 / F14), the same path as the real ones
        mods = hotkeys.MOD_CONTROL | hotkeys.MOD_ALT | hotkeys.MOD_SHIFT | hotkeys.MOD_NOREPEAT
        got = []
        with patch.dict(hotkeys.HOTKEY_DEFS, {'wordbook': [(mods, 0x7C), (mods, 0x7D)]}):
            gh = hotkeys.GlobalHotkeys(on_triggered=got.append)
            gh.start()
            try:
                gh.set_enabled('wordbook', True)
                self.assertTrue(self.wait(lambda: 'wordbook' in gh.status()['registered']), gh.status())
                self.assertIsNone(gh.status()['errors']['wordbook'])
                import ctypes
                user32 = ctypes.WinDLL('user32')
                hk_id = hotkeys._HOTKEY_IDS['wordbook'][0]
                self.assertTrue(user32.PostThreadMessageW(gh._thread_id, hotkeys.WM_HOTKEY, hk_id, 0))
                self.assertTrue(self.wait(lambda: got == ['wordbook']), got)
                gh.set_enabled('wordbook', False)
                self.assertTrue(self.wait(lambda: 'wordbook' not in gh.status()['registered']))
            finally:
                gh.stop()

    def test_enabling_right_after_start_is_never_lost(self):
        # The thread published its id before it had a message queue: a wake-up posted in between
        # was dropped and nothing registered (16 of 30 tries before the fix)
        mods = hotkeys.MOD_CONTROL | hotkeys.MOD_ALT | hotkeys.MOD_SHIFT | hotkeys.MOD_NOREPEAT
        with patch.dict(hotkeys.HOTKEY_DEFS, {'wordbook': [(mods, 0x7C), (mods, 0x7D)]}):
            lost = 0
            for _ in range(20):
                gh = hotkeys.GlobalHotkeys(on_triggered=lambda name: None)
                gh.start()
                gh.set_enabled('wordbook', True)
                try:
                    lost += not self.wait(lambda: 'wordbook' in gh.status()['registered'])
                finally:
                    gh.stop()
            self.assertEqual(lost, 0)

    def test_the_real_combinations_register_when_free(self):
        gh = hotkeys.GlobalHotkeys(on_triggered=lambda name: None)
        gh.start()
        try:
            gh.set_enabled('wordbook', True)
            self.wait(lambda: 'wordbook' in gh.status()['registered']
                      or gh.status()['errors'].get('wordbook'))
            errors = gh.status()['errors'].get('wordbook')
            if errors and all(e == 1409 for e in errors):
                self.skipTest('another program (CorrectNote itself) holds the word book hotkeys')
            self.assertIn('wordbook', gh.status()['registered'], errors)
        finally:
            gh.stop()                                   # released at once

    def test_the_app_queue_toggles_the_word_book(self):
        import app
        a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a._hotkey_queue = queue.Queue()
        a.root = Mock()
        a._toggle_word_book_from_hotkey = Mock()
        a._open_quick_capture = Mock()
        a._on_hotkey_triggered('wordbook')
        a._poll_hotkey_queue()
        a._toggle_word_book_from_hotkey.assert_called_once_with()
        a._open_quick_capture.assert_not_called()


if __name__ == '__main__':
    unittest.main()
