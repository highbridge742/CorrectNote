# -*- coding: utf-8 -*-
"""Rows read back from the saved file have no record of what they used. A word that moves must not mark them all as
not analysed: they keep their answers and are read again when the hands stop (2026-11-05)."""
import json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path


def child():
    import tkinter as tk
    from unittest.mock import Mock, patch
    import analysis_cache, app, tab_analysis
    root = tk.Tk(); root.withdraw()
    with patch.object(app, 'GlobalHotkeys', return_value=Mock()):
        a = app.CorrectNoteApp(root)
        root.geometry('900x600+40+40'); root.deiconify(); root.update()
        e = a.editor
        def pump(s):
            end = time.monotonic() + s
            while time.monotonic() < end:
                root.update(); time.sleep(.01)
        t0 = time.monotonic()
        while time.monotonic() - t0 < 120 and (a._foreground_analysis_pending() or not a.line_results):
            pump(.2)
        pump(.5)
        lines = e.get('1.0', 'end-1c').split(chr(10))
        filled = [i for i, r in enumerate(a.line_results) if r.get('original')]
        assert len(filled) >= 8 and all(tab_analysis.reusable_result(a.line_results[i]) for i in filled)
        # read back from the saved form
        a.line_results = [analysis_cache._read_back(analysis_cache._pack(r)) if r.get('original') else r for r in a.line_results]
        assert all(tab_analysis.restored_without_proof(a.line_results[i]) for i in filled)
        answers = {a.line_results[i]['original']: a.line_results[i]['corrected'] for i in filled}
        a.store.add('ずばらしごう', '図原氏号')
        row = next(i + 1 for i, l in enumerate(lines) if not l.strip() and i > 2)
        e.focus_force(); e.mark_set('insert', '%d.0' % row); root.update()
        e.event_generate('<KeyPress-BackSpace>'); e.event_generate('<KeyRelease-BackSpace>'); root.update()
        pump(.3)
        lines = e.get('1.0', 'end-1c').split(chr(10))
        rows = [i + 1 for i, l in enumerate(lines) if l.strip()]
        far = [k for k in rows if abs(k - row) > 3]
        marks = [k for k in far if a._line_analysis_display_state(k) == 'pending']
        assert not marks, ('marked', len(marks), len(far))
        for k in far:
            assert a.line_results[k - 1]['corrected'] == answers[lines[k - 1]], k
        kept = sum(1 for k in far if a.line_results[k - 1].get('deferred_stages'))
        assert kept == len(far), (kept, len(far))
        # Read again when the hands stop, without a mark on the way
        t0 = time.monotonic(); seen = 0
        while time.monotonic() - t0 < 120 and any(r.get('deferred_stages') for r in a.line_results):
            pump(.1)
            seen += sum(1 for k in far if a._line_analysis_display_state(k) == 'pending')
        assert not any(r.get('deferred_stages') for r in a.line_results), 'never read again'
        assert seen == 0, seen
        assert all(isinstance(a.line_results[k - 1].get('used_keys'), dict) for k in far), 'no record after reading again'
        # The next move touches only what used it
        a.store.add('ずばらしごうに', '図原氏号二'); a._analyze(); root.update(); pump(.3)
        assert not [k for k in far if a._line_analysis_display_state(k) == 'pending']
        # A tab read back from the saved file, opened after a word has moved
        import analysis_async, analysis_work_app as W
        other = a.session.tabs[1]; owner = W.owner_for_tab(a, other); key = other['text'].rstrip(chr(10))
        reg = tab_analysis._registry(a)
        t0 = time.monotonic()
        while time.monotonic() - t0 < 120 and owner not in reg:
            pump(.2)
        assert owner in reg, 'the other tab was not read'
        rows = reg.pop(owner)['results']
        getattr(a, '_bg_parked', {}).pop(owner, None)
        a._analysis_cache[key] = [analysis_cache._read_back(analysis_cache._pack(r)) if r.get('original') else r for r in rows]
        a._analysis_cache_dependencies[key] = analysis_async.state_key(a)
        a.store.add('ずばらしごうさん', '図原氏号三')
        assert analysis_async.state_key(a) != a._analysis_cache_dependencies[key]
        a._switch_tab(1); root.update(); pump(.3)
        lines = e.get('1.0', 'end-1c').split(chr(10))
        rows2 = [i + 1 for i, l in enumerate(lines) if l.strip()]
        marks = [k for k in rows2 if a._line_analysis_display_state(k) == 'pending']
        assert not marks, ('marked after the switch', len(marks), len(rows2))
        t0 = time.monotonic()
        while time.monotonic() - t0 < 120 and any(r.get('deferred_stages') for r in a.line_results):
            pump(.1)
        assert not any(r.get('deferred_stages') for r in a.line_results), 'the switch: never read again'
        assert all(isinstance(a.line_results[k - 1].get('used_keys'), dict) for k in rows2)
        print('RESTORED_MARKS_OK', flush=True)
        os._exit(0)


def main():
    source = Path(__file__).resolve().parent
    sys.path.insert(0, str(source)); sys.path.insert(0, str(source / 'tools_local' / 'heavy_20261027'))
    from probe_heavy import make_copy
    with tempfile.TemporaryDirectory(prefix='correctnote-restored-') as folder:
        dest = make_copy(folder, 'as_is', False)
        for n in ('reading_lattice_compact.pickle.gz', 'reading_lattice_table.pickle.gz', 'janome_entries.pickle.gz', 'wlsp_synonyms_compact.pickle.gz'):
            if (source / n).exists(): shutil.copy2(source / n, dest / n)
        sys.path.insert(0, str(dest))
        from session import new_tab
        text = chr(10).join('今日は天気がよいので%d番目の公園へ歩いて行きました。' % k if k % 3 else '' for k in range(1, 25))
        (dest / 'session.json').write_text(json.dumps(dict(version=1, active=0, tabs=[new_tab(text=text), new_tab(text=text.replace('公園', '図書館'))]), ensure_ascii=False), encoding='utf-8')
        (dest / '.ui-test-isolated').touch()
        shutil.copy2(__file__, dest / 'probe_restored_marks.py')
        r = subprocess.run([sys.executable, '-X', 'utf8', str(dest / 'probe_restored_marks.py'), '--child'], cwd=dest, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf-8', errors='replace', timeout=280)
        ok = 'RESTORED_MARKS_OK' in r.stdout
        print('OK' if ok else r.stdout[-1500:].encode('ascii', 'replace').decode())
        sys.exit(0 if ok else 1)


if __name__ == '__main__':
    child() if '--child' in sys.argv else main()
