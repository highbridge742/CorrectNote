# -*- coding: utf-8 -*-
"""Original grammatical context survives the selectable-range UI entry."""
import ast,copy,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import morphology as M,units,explain


class SelectionContextTests(unittest.TestCase):
    def tokens(self):
        return [M.Token('よい','形容詞','よい','よい',0,2,True,'自立','基本形'),
                M.Token('でしょ','助動詞','です','でしょ',2,5,True,'','未然形'),
                M.Token('う','助動詞','う','う',5,6,True,'','基本形'),
                M.Token('か','助詞','か','か',6,7,True,'副助詞／並立助詞／終助詞'),
                M.Token('。','記号','。','。',7,8,True,'句点')]

    def test_finite_question_keeps_surface_and_source_offsets(self):
        before=self.tokens();after=M._contextualize_terminal_questions(before)
        self.assertEqual(after[3].pos_sub,'終助詞')
        for a,b in zip(before,after):
            for key in ('surface','reading','base_form','start','end','has_reading','infl_form'):
                self.assertEqual(getattr(a,key),getattr(b,key))
        self.assertEqual(before[3].pos_sub,'副助詞／並立助詞／終助詞')

    def test_indefinite_alternative_unknown_and_unfinished_are_not_reclassified(self):
        for variant in ('noun','unfinished','unknown','gap','following_word','comma'):
            parts=self.tokens()
            if variant=='noun':parts[2]=M.Token('物','名詞','物','もの',5,6,True,'一般')
            if variant=='unfinished':parts[2]=M.Token('う','助動詞','う','う',5,6,True,'','未然形')
            if variant=='unknown':parts[2]=M.Token('う','助動詞','う','う',5,6,False,'','基本形')
            if variant=='gap':parts[3]=M.Token('か','助詞','か','か',7,8,True,'副助詞／並立助詞／終助詞')
            if variant=='following_word':parts[4]=M.Token('帰る','動詞','帰る','かえる',7,9,True,'自立','基本形')
            if variant=='comma':parts[4]=M.Token('、','記号','、','、',7,8,True,'読点')
            self.assertEqual(M._contextualize_terminal_questions(parts)[3].pos_sub,'副助詞／並立助詞／終助詞',variant)

    def test_range_carries_complete_native_functional_span(self):
        parts=M._contextualize_terminal_questions(self.tokens())
        with patch.object(M,'tokenize',return_value=parts):
            unit=units.make_range_unit('よいでしょうか。',[],2,6)
            self.assertTrue(unit['functional'])
            self.assertEqual(unit['analysis_context'],('よいでしょうか。',2,6))
            self.assertFalse(units.make_range_unit('よいでしょうか。',[],3,6)['functional'])
            self.assertFalse(units.make_range_unit('よいでしょうか。',[],0,2)['functional'])

    def test_selected_question_uses_original_context_in_pos_display(self):
        parts=M._contextualize_terminal_questions(self.tokens())
        with patch.object(M,'tokenize',return_value=parts):
            self.assertEqual(explain.pos_lines('か',source_context=('よいでしょうか。',6,7)),['助詞（終助詞）'])

    def test_partial_original_token_is_not_reparsed_as_an_unrelated_verb(self):
        with patch.object(M,'tokenize',return_value=self.tokens()),patch.object(M,'HAS_JANOME',True):
            lines=explain.pos_lines('しょう',source_context=('よいでしょうか。',3,6))
            self.assertIn('原文の語の区切り',lines[0])
            self.assertNotIn('原形 する',str(lines))

    def test_ambiguous_native_label_does_not_assert_its_first_sense(self):
        label=explain.pos_name('助詞:副助詞／並立助詞／終助詞','か')
        self.assertIn('終助詞',label)
        self.assertIn('文脈による',label)

    def test_all_three_real_dropdown_branches_prioritize_functional_range(self):
        source=Path(__file__).with_name('app.py').read_text(encoding='utf8')
        tree=ast.parse(source)
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='CorrectNoteApp')
        names=('_open_quick_dropdown','_editor_dropdown_items','_open_dropdown')
        for name in names:
            method=copy.deepcopy(next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name==name))
            # Run the actual candidate-dispatch body, without constructing Tk.
            edge=next(i for i,n in enumerate(method.body) if isinstance(n,ast.If)
                      and 'build_range_candidates' in ast.unparse(n) and 'build_candidates' in ast.unparse(n))
            method.body=method.body[:edge+1]+[ast.Return(value=ast.Name(id='cands',ctx=ast.Load()))]
            calls=[]
            ns={'build_candidates':lambda *a,**k:calls.append('word') or ['word'],
                'build_range_candidates':lambda *a,**k:calls.append('range') or ['range'],
                'find_known_readings_flex':None}
            exec(compile(ast.fix_missing_locations(ast.Module(body=[method],type_ignores=[])),'app.py','exec'),ns)
            obj=SimpleNamespace(dict_index=SimpleNamespace(ready=True),line_units=[[]],_quick_units=[[]],store=None,context_vec=None,
                _unit_surroundings=lambda *a:[],_functional_kanji_cands=lambda *a:calls.append('functional') or ['functional'])
            unit=dict(kind='range',segments=[('でしょう','でしょう')],functional=True,base='でしょう',reading='でしょう')
            args=(obj,1,unit,[]) if name=='_editor_dropdown_items' else (obj,None,1,unit)
            self.assertEqual(ns[name](*args),['functional'],name)
            self.assertEqual(calls,['functional'],name)
            calls.clear();unit['functional']=False
            self.assertEqual(ns[name](*args),['range'],name)
            self.assertEqual(calls,['range'],name)

if __name__=='__main__':unittest.main()
