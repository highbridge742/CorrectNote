# -*- coding: utf-8 -*-
"""Explicit IME results survive real app timers, tabs and shutdown."""
from pathlib import Path
import json,shutil,subprocess,sys,tempfile,time,traceback,unittest

def child():
    import ctypes as C
    from ctypes import wintypes as W
    import tkinter as tk
    from unittest.mock import Mock,patch
    import app,ime_events,ime_watch
    from session import new_tab
    assert (Path.cwd()/'.ui-test-isolated').exists()
    Path('settings.json').write_text(json.dumps(dict(layout='split',input_method='kana',input_method_auto=False)),encoding='utf-8')
    Path('session.json').write_text(json.dumps(dict(version=1,active=0,tabs=[new_tab(text='最初のタブです。'),new_tab(text='別のタブです。')]),ensure_ascii=False),encoding='utf-8')
    root=tk.Tk();root.withdraw();a=None;errors=[]
    root.report_callback_exception=lambda *exc:errors.append(''.join(traceback.format_exception(*exc)))
    user=C.WinDLL('user32');user.SendMessageW.argtypes=[W.HWND,W.UINT,C.c_size_t,C.c_ssize_t]
    user.SendMessageW.restype=C.c_ssize_t
    def send(surface,reading,clauses=()):
        got=dict(result=surface,result_reading=reading)
        if clauses:got['result_clauses']=clauses
        with patch.object(ime_watch,'read_composition',return_value=got):
            user.SendMessageW(a.editor.winfo_id(),ime_events.WM_IME_COMPOSITION,0,0x1E00 if clauses else 0xA00)
    def until(predicate,seconds=90):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            root.update();assert not errors,errors
            if predicate():return
            time.sleep(.005)
        raise AssertionError(a.status.cget('text'))
    with patch.object(app,'GlobalHotkeys',return_value=Mock()),patch.object(app.CorrectNoteApp,'_learn_now',lambda *args:None):
        try:
            a=app.CorrectNoteApp(root)
            listener=a._ime_result_events;assert listener.hwnd==a.editor.winfo_id()
            a._start_ime_reading_watch();assert a._ime_result_events is listener
            send('行った','ｲｯﾀ');send('行った','ｵｺﾅｯﾀ')
            until(lambda:a.ime_readings.readings_for('行った')==['おこなった','いった'])
            assert a.editor_source_text().rstrip('\n')=='最初のタブです。',repr(a.editor_source_text())
            send('資料','ｼﾘｮｳ');a._switch_tab(1)
            until(lambda:a.ime_readings.readings_for('資料')==['しりょう'])
            assert a.editor_source_text().rstrip('\n')=='別のタブです。',repr(a.editor_source_text())
            assert not a._input_document.occurrences
            # Several native commits may arrive before one ordinary timer.
            user.SendMessageW(a.editor.winfo_id(),ime_events.WM_IME_STARTCOMPOSITION,0,0)
            send('行った','ｲｯﾀ');a.editor.insert('1.0','行った')
            a.editor.insert('1.3','行った');send('行った','ｵｺﾅｯﾀ')
            user.SendMessageW(a.editor.winfo_id(),ime_events.WM_IME_ENDCOMPOSITION,0,0)
            a.editor.mark_set('insert','end-1c')
            a._drain_ime_result_events()
            occurrences=a._input_document.occurrences
            assert [(o.start,o.end,o.surface,o.reading) for o in occurrences]==[
                (0,3,'行った','いった'),(3,6,'行った','おこなった')],occurrences
            user.SendMessageW(a.editor.winfo_id(),ime_events.WM_IME_STARTCOMPOSITION,0,0)
            a.editor.insert('1.0','資料')
            user.SendMessageW(a.editor.winfo_id(),ime_events.WM_IME_ENDCOMPOSITION,0,0)
            a._drain_ime_result_events()
            assert not any(o.surface=='資料' for o in a._input_document.occurrences)
            print('IME_ACTUAL_COMMIT_RANGES_OK',flush=True)
            revision=a.store.revision()
            user.SendMessageW(a.editor.winfo_id(),ime_events.WM_IME_STARTCOMPOSITION,0,0)
            send('海上読奥','ｶｲｼﾞｮｳﾖﾖｸ',(('海上','ｶｲｼﾞｮｳ'),('読奥','ﾖﾖｸ')))
            a.editor.insert('1.0','海上読奥')
            user.SendMessageW(a.editor.winfo_id(),ime_events.WM_IME_ENDCOMPOSITION,0,0)
            a._drain_ime_result_events()
            doc=a._input_document
            assert [(o.start,o.end,o.surface,o.reading) for o in doc.occurrences if o.end<=4]==[
                (0,2,'海上','かいじょう'),(2,4,'読奥','よよく')],doc.occurrences
            from analysis_work import current_input,occurrence_readings
            with current_input(doc.text,doc.occurrences):
                assert occurrence_readings(doc.text,0,4)==('かいじょうよよく',)
                assert occurrence_readings(doc.text,2,4)==('よよく',)
            assert a.ime_readings.readings_for('海上読奥')==['かいじょうよよく']
            assert not a.ime_readings.readings_for('海上')
            assert a.store.revision()==revision
            print('IME_RESULT_CLAUSES_APP_OK',flush=True)
            user.SendMessageW(a.editor.winfo_id(),ime_events.WM_IME_STARTCOMPOSITION,0,0)
            send('図表。','ｽﾞﾋｮｳ｡',(('図表。','ｽﾞﾋｮｳ｡'),))
            a.editor.insert('1.0','図表。')
            user.SendMessageW(a.editor.winfo_id(),ime_events.WM_IME_ENDCOMPOSITION,0,0)
            a._drain_ime_result_events()
            doc=a._input_document
            assert [(o.start,o.end,o.surface,o.reading) for o in doc.occurrences if o.end<=3]==[
                (0,2,'図表','ずひょう')],doc.occurrences
            with current_input(doc.text,doc.occurrences):
                assert occurrence_readings(doc.text,0,2)==('ずひょう',)
            assert not a.ime_readings.readings_for('図表。')
            assert not a.ime_readings.readings_for('図表')
            assert a.store.revision()==revision
            print('IME_LITERAL_RESULT_EDGES_APP_OK',flush=True)
            a.editor.insert('end-1c','確認')
            send('確認','ｶｸﾆﾝ');a._on_close();a=None
            assert listener.hwnd==0 and listener._uid not in ime_events._LIVE
            saved=json.loads(Path('ime_readings.json').read_text(encoding='utf-8'))
            assert '確認' in str(saved),saved
            assert not errors,errors
            print('IME_EVENTS_LIFECYCLE_OK',flush=True)
        finally:
            if a is not None:a._on_close()

class IMEResultEventsGuiTests(unittest.TestCase):
    def test_timer_tab_and_close_keep_explicit_pairs(self):
        from bundle_manifest import NAMES
        source=Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix='correctnote-ime-events-') as folder:
            dest=Path(folder)
            for p in source.iterdir():
                if p.is_file() and (p.suffix=='.py' or p.name in NAMES):shutil.copy2(p,dest/p.name)
            (dest/'.ui-test-isolated').touch()
            run=subprocess.run([sys.executable,'-X','utf8',str(dest/Path(__file__).name),'--child'],cwd=dest,
                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf-8',timeout=240)
            print(run.stdout,flush=True);self.assertEqual(run.returncode,0,run.stdout)

if __name__=='__main__':
    child() if '--child' in sys.argv else unittest.main()