"""Prefetch keeps completed rows and ignores internal layout notifications."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import unittest


def child():
    import tkinter as tk
    from types import SimpleNamespace
    from unittest.mock import Mock, patch
    import app, analysis_work_app as work, analysis_worker, tab_analysis
    from session import new_tab
    assert (Path.cwd() / '.ui-test-isolated').exists()
    assert Path(app.__file__).resolve().parent == Path.cwd().resolve()
    texts = ['寒ぃ日だ。', '資料を確認します。\nあしたの予定です。', '別のメモを読みます。']
    Path('session.json').write_text(json.dumps(dict(version=1, active=0,
        tabs=[new_tab(text=t) for t in texts]), ensure_ascii=False), encoding='utf-8')
    Path('settings.json').write_text(json.dumps(dict(layout='split', input_method='kana',
        input_method_auto=False)), encoding='utf-8')
    root = tk.Tk(); root.withdraw(); a = None; errors = []; calls = []; tasks = {}
    inject = [texts[1].split('\n')[1], 1]
    root.report_callback_exception = lambda *exc: errors.append(''.join(traceback.format_exception(*exc)))
    original_submit = analysis_worker.Worker.submit
    original_poll = analysis_worker.Worker.poll
    def submit(worker, task, state=None):
        identifier = original_submit(worker, task, state)
        calls.append((task['kind'], task.get('line'))); tasks[identifier] = task
        return identifier
    def poll(worker, identifier):
        value = original_poll(worker, identifier)
        task = tasks.get(identifier, {})
        if value is not None and inject[1] and task.get('kind') == 'line' and task.get('line') == inject[0]:
            # Exercise the UI contract for an unfinished worker reply without
            # changing the engine, its budget, or any personal vocabulary.
            value = dict(value, result=dict(value['result'], analysis_status='incomplete'))
            inject[1] -= 1
        return value
    def done():
        return (a._warmup is None and getattr(a, '_async_context_scope', None) is None
            and a._analyze_text == a.editor_source_text() and a._analyze_pos >= len(a._analyze_todo)
            and a._analyze_work == work.token(a) and a._analyze_dependencies == analysis_worker.state_key(a))
    def complete(index):
        return tab_analysis.completed(a, a.session.tabs[index]['text'],
            work.owner_for_tab(a, a.session.tabs[index])) is not None
    def until(predicate, seconds=35):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            root.update()
            if errors: raise AssertionError(errors)
            if predicate(): return
            time.sleep(.005)
        raise AssertionError(dict(status=a.status.cget('text'), foreground=a._foreground_analysis_pending(),
            interacting=a._interacting(), calls=calls, pending=getattr(a, '_async_request', None)))
    def line_calls(text):
        return calls.count(('line', text))
    internal_events = [True]
    def configure():
        if internal_events[0]:
            a.editor.event_generate('<Configure>')
            root.event_generate('<Configure>', x=root.winfo_x(), y=root.winfo_y(),
                width=root.winfo_width(), height=root.winfo_height())
            root.after(50, configure)
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()), \
         patch.object(app.CorrectNoteApp, '_learn_now', new=lambda *args: None), \
         patch.object(analysis_worker.Worker, 'submit', submit), \
         patch.object(analysis_worker.Worker, 'poll', poll):
        try:
            a = app.CorrectNoteApp(root); until(done)
            unit = next(u for u in a._editor_line_units(1) if u.get('detail'))
            a._open_editor_dropdown(SimpleNamespace(x_root=0, y_root=0), 1, unit)
            a._dropdown.withdraw(); configure()
            # A static candidate popup and repeated child layout events must
            # not stop the next tab or later tabs from being analyzed.
            until(lambda: complete(2))
            internal_events[0] = False
            assert a._dropdown is not None
            a._close_dropdown()
            owner = work.owner_for_tab(a, a.session.tabs[1])
            assert not complete(1)
            partial = a._bg_parked[owner]
            assert partial['results'][0] is not None and partial['results'][1] is None
            first, second = texts[1].split('\n')
            before = [line_calls(first), line_calls(second)]
            a._switch_tab(1); until(done)
            delta = [line_calls(first)-before[0], line_calls(second)-before[1]]
            assert delta == [0, 1], ('background partial was recomputed', delta)
            assert complete(1)
            print('BACKGROUND_PARTIAL_REUSED', delta, flush=True)
            # The same retention is needed when foreground processing reaches
            # its last row but one result remains incomplete.
            a._switch_tab(0); until(done)
            first, second = '新しい資料を確認します。', 'あさっての予定です。'
            a.session.tabs[1]['text'] = first + '\n' + second
            inject[:] = [second, 1]
            a._switch_tab(1); until(done)
            assert not complete(1) and a.line_results[1].get('analysis_status') == 'incomplete'
            before = [line_calls(first), line_calls(second)]
            a._switch_tab(0); until(done)
            until(lambda: complete(1))
            delta = [line_calls(first)-before[0], line_calls(second)-before[1]]
            assert delta == [0, 1], ('foreground partial was recomputed', delta)
            print('FOREGROUND_PARTIAL_REUSED', delta, flush=True)
            before = len(calls)
            a._switch_tab(1); until(done); a._switch_tab(0); until(done)
            assert len(calls) == before, ('completed tabs recomputed', calls[before:])
            print('PREFETCH_UI_OK', flush=True)
        finally:
            internal_events[0] = False
            if a is not None: a._on_close()
            else: root.destroy()


class PrefetchGuiTests(unittest.TestCase):
    def test_popup_layout_events_and_partial_rows(self):
        from bundle_manifest import NAMES
        source = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-prefetch-ui-') as folder:
            dest = Path(folder)
            for p in source.iterdir():
                if p.is_file() and (p.suffix == '.py' or p.name in NAMES):
                    shutil.copy2(p, dest / p.name)
            (dest / '.ui-test-isolated').touch()
            result = subprocess.run([sys.executable, '-X', 'utf8', str(dest / Path(__file__).name), '--child'],
                cwd=dest, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf-8', timeout=170)
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn('PREFETCH_UI_OK', result.stdout)
            print(result.stdout.strip())


if __name__ == '__main__':
    if '--child' in sys.argv: child()
    else: unittest.main()