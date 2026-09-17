# -*- coding: utf-8 -*-
"""48-ACO: real Tcl error forwarding and isolated application startup.

Copies only Python and bundle_manifest assets. No user stores are read/copied.
The child creates synthetic session/settings files and hidden real Tk widgets.
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


class TextObserverTkTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from analysis_work import observe_text
        self.tk = tk
        self.root = tk.Tk()
        self.root.withdraw()
        self.widget = tk.Text(self.root, undo=True)
        self.edits = []
        self.callbacks = []
        self.root.report_callback_exception = lambda *exc: self.callbacks.append(exc)
        observe_text(self.widget, lambda *edit: self.edits.append(edit))

    def tearDown(self):
        self.root.destroy()
        from tests_tk_keys import release_tk_fixture
        release_tk_fixture(self,'widget','root')

    def test_cursor_observer_shares_proxy_without_creating_edits(self):
        from analysis_work import observe_text
        cursors=[]
        observe_text(self.widget,on_cursor=lambda:cursors.append(self.widget.index('insert')))
        self.widget.insert('1.0','一行目\n二行目')
        self.edits.clear();cursors.clear()
        self.widget.mark_set('insert','1.0')
        self.widget.mark_set('insert','2.0')
        self.widget.mark_set('unrelated','1.0')
        self.widget.cget('background')
        self.assertEqual(cursors,['1.0','2.0'])
        self.assertEqual(self.edits,[])
        self.widget.insert('insert','追記')
        self.assertEqual(len(self.edits),1)
        self.assertEqual(cursors[-1],'2.2')

    def test_handled_native_errors_do_not_abort_next_mainloop(self):
        # Exactly the dark-mode failure: this caller catches an unsupported
        # option, then enters mainloop. The old Python proxy crashed here.
        with self.assertRaisesRegex(self.tk.TclError, 'unknown option'):
            self.widget.cget('selectcolor')
        self.root.after(0, self.root.quit)
        self.root.mainloop()
        self.assertEqual(self.callbacks, [])
        self.assertEqual(self.edits, [])

    def test_tcl_catch_preserves_native_error_and_valid_edits(self):
        w = self.widget
        original = w._w + '_correctnote_work'
        for args in (('cget', '-selectcolor'), ('delete', 'invalid-index'),
                     ('edit', 'undo')):
            outcomes = []
            for command in (original, w._w):
                code = w.tk.call('catch', (command,) + args,
                                 '::cn_test_error', '::cn_test_options')
                outcomes.append((code, w.tk.getvar('::cn_test_error'),
                    w.tk.call('dict', 'get', w.tk.getvar('::cn_test_options'),
                              '-errorcode')))
            self.assertEqual(outcomes[0], outcomes[1])
            self.assertEqual(outcomes[0][0], 1)
        self.assertEqual(self.edits, [])
        w.insert('1.0', '資料')
        w.edit_separator()
        w.insert('end-1c', 'と資料')
        self.assertEqual(self.edits[-1], ('資料と資料', False, (2, 2)))
        w.edit_undo()
        self.assertEqual(w.get('1.0', 'end-1c'), '資料')
        self.assertTrue(self.edits[-1][1])
        w.insert('1.0', '😀')
        w.insert('end-1c', 'と資料')
        self.assertEqual(self.edits[-1], ('😀資料と資料', False, (3, 3)))
        self.root.after(0, self.root.quit)
        self.root.mainloop()
        self.assertEqual(self.callbacks, [])


def _fixture_collection_child():
    import gc
    import threading
    import faulthandler
    faulthandler.enable(all_threads=True)
    # Force the formerly intermittent failure after the fixture is finished.
    gc.disable()
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(TextObserverTkTests)
    result=unittest.TextTestRunner().run(suite)
    if not result.wasSuccessful():raise AssertionError('observer fixture failed')
    del suite,result
    thread=threading.Thread(target=gc.collect)
    thread.start();thread.join()
    print('FIXTURE_COLLECTION_OK',flush=True)


@unittest.skipUnless(sys.platform=='win32','Windows Tk lifetime regression')
class FixtureCollectionTkTests(unittest.TestCase):
    def test_closed_tk_fixtures_can_be_collected_by_a_later_io_thread(self):
        path=Path(__file__).resolve()
        result=subprocess.run([sys.executable,'-X','utf8',str(path),'--fixture-collection-child'],
                              cwd=path.parent,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                              encoding='utf-8',errors='replace',timeout=30)
        self.assertEqual(result.returncode,0,result.stdout)
        self.assertIn('FIXTURE_COLLECTION_OK',result.stdout)


def _startup_child():
    import tkinter as tk
    import traceback
    import app
    from session import new_tab
    home = Path.cwd().resolve()
    assert Path(app.__file__).resolve().parent == home
    # Only the parent's newly-created isolated folder may be mutated.
    assert (home / '.startup-test-isolated').is_file()
    config = json.loads((home / 'startup_case.json').read_text(encoding='utf-8'))
    texts = ['よいでしょぅか。\n寒ぃ日だ。', 'これはテストです。']
    if config['restored']:
        (home / 'session.json').write_text(json.dumps(dict(version=1, active=0,
            tabs=[new_tab(text=text) for text in texts]), ensure_ascii=False),
            encoding='utf-8')
    (home / 'settings.json').write_text(json.dumps(dict(
        layout=config['layout'], dark_mode=config['dark'], input_method='kana',
        input_method_auto=False)), encoding='utf-8')
    root = tk.Tk()
    root.withdraw()
    callbacks = []
    def callback_error(*exc):
        callbacks.append(''.join(traceback.format_exception(*exc)))
        root.quit()
    root.report_callback_exception = callback_error
    instance = None
    try:
        instance = app.CorrectNoteApp(root)
        if config['restored']:
            assert len(instance.session.tabs) == 2
            assert instance.editor.get('1.0', 'end-1c').rstrip('\n') == texts[0]
        root.after(250, root.quit)
        root.mainloop()
        assert not callbacks, '\n'.join(callbacks)
        # Exercise valid mutations on the fully-constructed observed editor.
        epoch = getattr(instance, '_work_epoch', 0)
        instance.editor.insert('end-1c', '😀')
        assert instance._work_epoch > epoch
        assert instance.editor.get('1.0', 'end-1c').endswith('😀')
        root.after(50, root.quit)
        root.mainloop()
        assert not callbacks, '\n'.join(callbacks)
        print('STARTUP_OK ' + json.dumps(config), flush=True)
    finally:
        if instance is not None:
            instance._on_close()
        else:
            root.destroy()
    assert not callbacks, '\n'.join(callbacks)


def run_startup_smoke():
    from bundle_manifest import NAMES
    source = Path(__file__).resolve().parent
    cases = [dict(layout=layout, dark=dark, restored=dark)
             for layout in ('split', 'unified') for dark in (False, True)]
    for config in cases:
        with tempfile.TemporaryDirectory(prefix='correctnote-startup-') as folder:
            dest = Path(folder)
            for entry in source.iterdir():
                if entry.is_file() and (entry.suffix == '.py' or entry.name in NAMES):
                    shutil.copy2(entry, dest / entry.name)
            (dest / '.startup-test-isolated').touch()
            (dest / 'startup_case.json').write_text(json.dumps(config), encoding='utf-8')
            result = subprocess.run([sys.executable, '-X', 'utf8',
                str(dest / 'tests_gui_startup.py'), '--startup-child'], cwd=folder,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                encoding='utf-8', errors='replace', timeout=90)
            if result.returncode or 'STARTUP_OK ' not in result.stdout:
                raise AssertionError('Startup case %r failed:\n%s' % (config, result.stdout))
    return cases


class StartupTkTests(unittest.TestCase):
    def test_actual_startup_and_restore_in_both_layouts_and_themes(self):
        self.assertEqual(len(run_startup_smoke()), 4)


if __name__ == '__main__':
    if '--startup-child' in sys.argv:
        _startup_child()
    elif '--fixture-collection-child' in sys.argv:
        _fixture_collection_child()
    else:
        unittest.main()
