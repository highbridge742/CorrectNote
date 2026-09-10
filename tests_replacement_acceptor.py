# -*- coding: utf-8 -*-
import ast
from pathlib import Path
import unittest
from unittest.mock import Mock,patch
import corrector as C


class ReplacementAcceptorTests(unittest.TestCase):
    def setUp(self):
        for p in (patch.object(C,'absorb_stray_char',side_effect=lambda line,a,b,s:(a,b)),
                  patch.object(C,'_reading_spelled_in_bracket',return_value=False),
                  patch.object(C,'long_vowel_protected_span',return_value=None)):
            p.start();self.addCleanup(p.stop)

    def test_list_exemptions_work_with_tuple_defaults(self):
        self.assertEqual(C._check_replacement('abcdef',(0,6,'かな','その他'),None,None,
            halfwidth_taken=[(0,6)])[1],'accepted')
        self.assertEqual(C._check_replacement('あいうえお',(0,5,'字','その他'),None,None,
            lu_taken=[(0,5)])[1],'accepted')

    def test_shortening_and_katakana_conditions_are_explicit(self):
        accept=C._replacement_acceptor('あいうえお',0,5,None,None)
        self.assertFalse(accept('字','その他'))
        with patch.object(C,'_katakana_melt_ok',return_value=False):
            self.assertFalse(C._replacement_acceptor('カナ字',0,3,None,None,
                preserve_katakana=True)('文字','その他'))
            self.assertTrue(C._replacement_acceptor('カナ字',0,3,None,None)('文字','その他'))

    def test_actual_ascii_path_tries_next_candidate(self):
        tree=ast.parse(Path(C.__file__).read_text(encoding='utf-8'))
        call=next(n for n in ast.walk(tree) if isinstance(n,ast.Call)
            and isinstance(n.func,ast.Name) and n.func.id=='_resolve_reading_list'
            and len(n.args)>1 and isinstance(n.args[1],ast.Name) and n.args[1].id=='try_readings')
        store=Mock();store.lookup.return_value=[dict(surface='長すぎる候補',count=2),
                                                dict(surface='文字',count=2)]
        scope=dict(C.__dict__)
        scope.update(chunk='異字X',try_readings=['よみかた'],store=store,tokenize_fn=None,
            context_vec=None,surrounding=(),n_variant_readings=(),n_slip_readings=(),
            input_method='kana',line='異字X',a_start=0,a_end=3,dict_index=None,
            decisions=None,halfwidth_taken=[],lu_taken=[],conv_taken=[])
        with patch.object(C,'_chunk_is_intact',return_value=False):
            result=eval(compile(ast.Expression(call),'corrector.py','eval'),scope)
        self.assertEqual(result,('文字','その他'))

    def test_nominal_head_deletion_is_checked_for_all_replacements(self):
        tokens = [('炭酸', '名詞:一般', 'たんさん', 0, 2, True),
                  ('湯', '名詞:一般', 'ゆ', 2, 3, True)]
        with patch('oddness.is_odd_run', return_value=False):
            result, reason = C._check_replacement('炭酸湯', (0, 3, '炭酸', 'その他'),
                                                  None, lambda _: tokens)
        self.assertIsNone(result)
        self.assertEqual(reason, 'nominal_head_deletion')

    def test_nominal_head_check_does_not_replace_grammar_or_reading_evidence(self):
        tokens = [('炭酸', '名詞:一般', 'たんさん', 0, 2, True),
                  ('湯', '名詞:一般', 'ゆ', 2, 3, True)]
        with patch('oddness.is_odd_run', return_value=True):
            self.assertFalse(C._drops_nominal_head('炭酸湯', '炭酸', lambda _: tokens))
        with patch('oddness.is_odd_run', return_value=False):
            unknown = tokens[:-1] + [('湯', '名詞:一般', '', 2, 3, False)]
            self.assertFalse(C._drops_nominal_head('炭酸湯', '炭酸', lambda _: unknown))
            self.assertFalse(C._drops_nominal_head('素画像', '画像', lambda _: tokens))
            self.assertFalse(C._drops_nominal_head('炭酸湯', '温泉', lambda _: tokens))

    def test_user_block_uses_source_span(self):
        decision=Mock();decision.blocks.return_value=True
        accept=C._replacement_acceptor('前異字後',1,3,None,None,decisions=decision)
        self.assertFalse(accept('文字','その他'))
        decision.blocks.assert_called_once_with('異字','文字')


if __name__=='__main__':unittest.main()
