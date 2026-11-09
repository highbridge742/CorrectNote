# -*- coding: utf-8 -*-
"""A cursor key that changes neither the text nor the view costs little (2026-11-05 うにさん「左右キーでのカーソル移動が重い」).
Made-up text, Tk events only."""
import json, os, shutil, subprocess, sys, tempfile, time, traceback, unittest
from pathlib import Path


def child():
    import tkinter as tk
    from unittest.mock import Mock, patch
    import app
    from session import new_tab
    Path('session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[
        new_tab(text='\n'.join('一番目のタブの%d行目の文です。' % k for k in range(200))),
        new_tab(text='\n'.join('二番目のタブの%d行目の文です。' % k for k in range(200)))])), encoding='utf-8')
    root = tk.Tk(); root.withdraw()
    root.report_callback_exception = lambda *x: (traceback.print_exception(*x), sys.stdout.flush(), os._exit(3))
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), patch.object(app.CorrectNoteApp, '_learn_now', lambda *v: None):
        a = app.CorrectNoteApp(root)
        root.geometry('1000x600+0+0'); root.deiconify(); root.update()
        e, r = a.editor, a.result_view

        def pump(s):
            end = time.monotonic() + s
            while time.monotonic() < end:
                root.update(); time.sleep(.005)
        pump(1)
        e.focus_force(); root.update()
        counts = dict(ws=0, gutter=0, follow=0, configure=0)
        real_ws, real_follow = a._schedule_whitespace_paint, a._sync_partner_to_line

        def ws(*x, **k):
            counts['ws'] += 1
            return real_ws(*x, **k)

        def follow(*x, **k):
            counts['follow'] += 1
            return real_follow(*x, **k)
        a._schedule_whitespace_paint = ws
        a._sync_partner_to_line = follow
        e.mark_set('insert', '5.0'); e.see('5.0'); root.update()
        e.event_generate('<KeyRelease-Right>'); root.update(); pump(.4)     # the first release has nothing to compare with
        counts.update(ws=0, follow=0)
        for i in range(5):
            e.event_generate('<KeyPress-Right>'); e.event_generate('<KeyRelease-Right>'); root.update()
        assert e.index('insert') == '5.5', e.index('insert')
        assert counts['ws'] == 0, ('whitespace paint on a cursor key', counts)
        assert counts['follow'] == 0, ('the correction pane aligned on a cursor key', counts)
        # the cursor still flashes, and comes back
        guides = a._editor_guides
        assert guides._flash is not None
        pump(.4)
        assert guides._flash is None
        # typing still paints
        e.insert('insert', '字'); e.event_generate('<KeyRelease-Right>'); root.update()
        assert counts['ws'] >= 1, counts
        # a real move still follows
        counts.update(follow=0)
        e.yview('100.0'); root.update(); pump(.2)
        assert counts['follow'] >= 1, counts
        assert r.index('@0,0').split('.')[0] == '100', r.index('@0,0')
        # another tab at the same fractions: the correction pane follows it
        a._switch_tab(1); pump(.5)
        a._switch_tab(0); pump(.5)
        e.yview('50.0'); root.update(); pump(.2)
        seen = e.yview()
        a._switch_tab(1); pump(.3); e.yview_moveto(seen[0]); root.update(); pump(.2)
        assert e.index('@0,0').split('.')[0] == r.index('@0,0').split('.')[0], (e.index('@0,0'), r.index('@0,0'))
        print('KEYS_LIGHT_OK', flush=True)
        os._exit(0)


class KeysLight(unittest.TestCase):
    def test_a_cursor_key_in_the_whole_app(self):
        from bundle_manifest import NAMES
        source = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-keys-') as directory:
            dest = Path(directory)
            for p in source.iterdir():
                if p.is_file() and (p.suffix == '.py' or p.name in NAMES):
                    shutil.copy2(p, dest / p.name)
            (dest / '.ui-test-isolated').touch()
            run = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(dest / Path(__file__).name), '--child'], cwd=dest,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf-8', errors='replace', timeout=120)
            self.assertIn('KEYS_LIGHT_OK', run.stdout, run.stdout[-900:])

    def test_the_flash_configures_the_pane_once(self):
        import tkinter as tk
        from unittest.mock import Mock
        from editor_guides import EditorGuides
        g = EditorGuides.__new__(EditorGuides)
        g.root = Mock(); g.root.after = Mock(return_value='job')
        g._flash = None; g._restore_job = None; g._key_job = None; g._draw_job = None
        pane = Mock(); pane.cget = Mock(return_value='x')
        g._begin_flash(pane); g._begin_flash(pane); g._begin_flash(pane)
        self.assertEqual(pane.configure.call_count, 1)


if __name__ == '__main__':
    if '--child' in sys.argv:
        try:
            child()
        except BaseException:
            traceback.print_exc(); sys.stdout.flush(); sys.stderr.flush(); os._exit(2)
    else:
        unittest.main()
