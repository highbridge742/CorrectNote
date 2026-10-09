# -*- coding: utf-8 -*-
"""The worker uses the shared correction entry without loading editor widgets."""
from pathlib import Path
import subprocess,sys,unittest


class HeadlessEntryTests(unittest.TestCase):
    def test_application_exports_the_same_entry(self):
        import app,correction_entry,text_positions
        self.assertIs(app.correct_line,correction_entry.correct_line)
        self.assertIs(app.map_column,text_positions.map_column)
        self.assertIs(app.selection_correction_pair,text_positions.selection_correction_pair)

    def test_candidate_selection_projection_does_not_import_editor(self):
        code=r'''
import sys
from candidates import contextual_choice_candidates
original='旧文です';shown='新しい文です'
result=dict(original=original,corrected=shown,contextual_choices=dict(version=1,source=original,
    candidates=[dict(start=0,end=2,base='旧文',surface='新文',reading='しんぶん')]))
values=contextual_choice_candidates(result,shown,0,4)
assert len(values)==1 and values[0]['choice_span']==(0,4),values
assert values[0]['original_span']==(0,2) and values[0]['base']=='旧文',values
assert not contextual_choice_candidates(result,shown,4,6)
assert not {'app','tkinter','hotkeys','session','search'} & set(sys.modules)
'''
        run=subprocess.run([sys.executable,'-B','-u','-X','utf8','-c',code],cwd=Path(__file__).resolve().parent,
            encoding='utf8',stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90)
        self.assertEqual(run.returncode,0,run.stdout)

    def test_worker_line_does_not_import_window_or_hotkey_modules(self):
        code=r'''
import sys
from types import SimpleNamespace
from unittest.mock import patch
from analysis_worker import Runtime
import corrector,units
runtime=Runtime()
runtime.store=SimpleNamespace(_tokenize_fn=lambda text:[])
runtime.decisions=runtime.context_vec=runtime.index=runtime.choices=None
runtime.tokenize=lambda text:[]
def correct(line,*args,**kwargs):
    assert kwargs['nearby_words']==('nearby',)
    assert kwargs['recent_words']==('recent',)
    return dict(original=line,corrected=line,changed=False,odd_spans=[])
with patch.object(corrector,'correct_line',side_effect=correct),patch('ime_colloquial.source_tokenizer',side_effect=lambda text,fn:fn),patch.object(units,'build_line_units',return_value=('sample',[])),patch.object(units,'build_suspect_units',return_value=('sample',[])):
    result=runtime.execute(dict(kind='line',line='sample',context={},input_method='kana',nearby=('nearby',),recent=('recent',)))
assert result['result']['original']==result['result']['corrected']=='sample'
assert runtime._ime_queries is None
assert not {'app','tkinter','hotkeys','session','search'} & set(sys.modules), sorted({'app','tkinter','hotkeys','session','search'} & set(sys.modules))
'''
        run=subprocess.run([sys.executable,'-B','-u','-X','utf8','-c',code],cwd=Path(__file__).resolve().parent,
            encoding='utf8',stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90)
        self.assertEqual(run.returncode,0,run.stdout)


if __name__=='__main__':unittest.main()
