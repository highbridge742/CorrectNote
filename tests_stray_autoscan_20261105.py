# -*- coding: utf-8 -*-
"""Tk's repeat that scrolls while a drag is above the pane must not outlive the drag (2026-11-05 うにさん「補正欄だけが
スクロールし続け、上へ戻しても戻され、やがて1行目に着いた。メモ欄は30行目のまま」). Made-up text, Tk events only."""
import json, shutil, subprocess, sys, tempfile, time, unittest
from pathlib import Path


def child():
    import tkinter as tk
    from unittest.mock import Mock, patch
    import app
    from session import new_tab
    Path('session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[
        new_tab(text='\n'.join('一番目のタブの%d行目の文です。' % k for k in range(300))),
        new_tab(text='\n'.join('二番目のタブの%d行目の文です。' % k for k in range(300)))])), encoding='utf-8')
    import os
    root = tk.Tk(); root.withdraw()
    root.report_callback_exception = lambda *x: (__import__('traceback').print_exception(*x), sys.stdout.flush(), os._exit(3))
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), patch.object(app.CorrectNoteApp, '_learn_now', lambda *v: None):
        a = app.CorrectNoteApp(root)
        root.geometry('1000x600+0+0'); root.deiconify(); root.update()
        e, r = a.editor, a.result_view

        def pump(s):
            end = time.monotonic() + s
            while time.monotonic() < end:
                root.update(); time.sleep(.005)

        def running():
            return root.tk.eval('expr {[info exists ::tk::Priv(afterId)] && $::tk::Priv(afterId) ne ""}') == '1'

        def tops():
            return int(e.index('@0,0').split('.')[0]), int(r.index('@0,0').split('.')[0])

        def at_row_30():
            e.yview('30.0'); r.yview('30.0'); root.update()
            a._drop_pending_scroll()
            assert tops() == (30, 30), tops()

        def start_scan():
            """The drag has gone above the pane: Tk's own <B1-Leave> starts the repeat."""
            at_row_30()
            root.tk.call('set', '::tk::Priv(x)', 40)
            root.tk.call('set', '::tk::Priv(y)', -20)
            r.tk.call('::tk::TextAutoScan', r._w)
            assert running()

        import os, traceback
        pump(2)
        # 1) let go: every way out of the correction pane's release ends the repeat, the ones that stop the class binding too
        start_scan()
        with patch('mouse_words.take_chord', return_value=True):
            r.event_generate('<ButtonRelease-1>', x=40, y=-20); root.update()
        assert not running(), 'release with break'
        pump(1); top = tops(); pump(.3)
        assert tops() == top, ('still scrolling', top, tops())
        # 2) the release never came: the mouse moving with no button down ends it
        start_scan()
        r.event_generate('<Motion>', x=40, y=40, state=0); root.update()
        assert not running(), 'motion without a button'
        # over the memo as well
        start_scan()
        e.event_generate('<Motion>', x=40, y=40, state=0); root.update()
        assert not running(), 'motion over the memo'
        # the drag itself goes on with the button held
        start_scan()
        r.event_generate('<Motion>', x=40, y=-20, state=0x100); root.update()
        assert running(), 'a held drag keeps its repeat'
        root.tk.call('::tk::CancelRepeat')
        # 3) another tab
        start_scan()
        a._switch_tab(1); root.update()
        assert not running(), 'tab switch'
        a._switch_tab(0); pump(.3)
        # 4) the wheel with no button down
        start_scan()
        with patch.object(a, '_left_button_is_up', return_value=True):
            a._on_wheel_units(-120); root.update()
        assert not running(), 'wheel'
        print('STRAY_AUTOSCAN_OK', flush=True)
        os._exit(0)


class StrayAutoscan(unittest.TestCase):
    def test_the_repeat_does_not_outlive_the_drag(self):
        from bundle_manifest import NAMES
        source = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-stray-') as directory:
            dest = Path(directory)
            for p in source.iterdir():
                if p.is_file() and (p.suffix == '.py' or p.name in NAMES):
                    shutil.copy2(p, dest / p.name)
            (dest / '.ui-test-isolated').touch()
            run = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(dest / Path(__file__).name), '--child'], cwd=dest,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf-8', errors='replace', timeout=120)
            self.assertIn('STRAY_AUTOSCAN_OK', run.stdout, run.stdout[-900:])


if __name__ == '__main__':
    if '--child' in sys.argv:
        try:
            child()
        except BaseException:
            import os, traceback
            traceback.print_exc(); sys.stdout.flush(); sys.stderr.flush(); os._exit(2)
    else:
        unittest.main()
