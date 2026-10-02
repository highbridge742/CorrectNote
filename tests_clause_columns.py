# -*- coding: utf-8 -*-
import unittest
import app,reading_segments as R,morphology as M
from tests_analysis_async import initial

@unittest.skipUnless(M.HAS_JANOME,'requires native Janome dictionary')
class ClauseColumnTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.a=initial()
    def test_native_proof_ends_at_the_column_without_losing_numeric_punctuation(self):
        text='ゆうせんしてほせい ⇒ ぷねらをよみます'
        ranges=R.native_context_ranges(text)
        self.assertIn((0,9),ranges)
        self.assertFalse(any(lo<=12 and len(text)<=hi for lo,hi in ranges))
        text='本を2.5冊  次の項目'
        self.assertEqual(list(R._native_source_clauses(text)),[(0,'本を2.5冊'),(text.index('次'),'次の項目')])
    def test_native_inflection_and_offsets_do_not_borrow_another_column(self):
        source='😀的買い\tまとがい ⇒ まちがい\t間違い'
        start=source.index('まとがい')
        tokens=[t for t in M.tokenize(source) if start<=t.start and t.end<=start+4]
        self.assertEqual([(t.surface,t.pos,t.infl_form,t.start,t.end) for t in tokens],
                         [('まと','動詞','未然ウ接続',start,start+2),
                          ('がい','名詞','',start+2,start+4)])
        self.assertTrue(all(source[t.start:t.end]==t.surface for t in M.tokenize(source)))

    def test_named_inflection_uses_the_column_as_a_word_boundary(self):
        import literal_examples as L
        for left,right in (('',''),('項目\t','\t次'),('資料    ','    次'),('前 ⇒ ',' ⇒ 次')):
            text=left+'小さかろという言葉があります。'+right
            with self.subTest(text=text):
                self.assertIn((len(left),len(left)+4),L._unquoted_form_ranges(text,()))
                r=app.correct_line(text,self.a.store,input_method='kana',dict_index=self.a.dict_index,
                                   context_vec=None,decisions=self.a.decisions)
                self.assertEqual(r['corrected'],text);self.assertEqual(r.get('odd_spans'),[])
        self.assertEqual(L._unquoted_form_ranges('ぷねら小さかろという言葉があります。',()),[])

    def test_initial_stages_keep_column_spacing_and_apply_the_same_phrase_judgment(self):
        from janome_import import import_from_janome
        a=self.a
        for phase in ('seed','fresh'):
            if phase=='fresh':import_from_janome(a.store)
            rows=[]
            for separator in ('\t','    '):
                closed=separator=='\t'
                rows += [(separator.join(('用船して補正','ようせんしてほせい ⇒ ゆうせんしてほせい','優先して補正')),
                          separator.join(('用船して補正',
                                          '用船して補正 ⇒ 優先して補正','優先して補正'))),
                         ('ゆうせんしてほせい'+separator+'次',
                          ('優先して補正' if closed else 'ゆうせんしてほせい')+separator+'次')]
            rows += [('の日っています\tのひっています ⇒ のこっています\t残っています',
                      '残っています\t残っています ⇒ 残っています\t残っています'),
                     ('的買い\tまとがい ⇒ まちがい\t間違い',
                      '間違い\t間違い ⇒ 間違い\t間違い')]
            rows += [(' ようせんしてほせい → ゆうせんしてほせい ',
                      ' ようせんしてほせい → ゆうせんしてほせい '),
                     ('「ようせんしてほせい」と入力します。','「ようせんしてほせい」と入力します。')]
            for source,expected in rows:
                with self.subTest(phase=phase,source=source):
                    r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                        context_vec=a.context_vec if phase=='fresh' else None,decisions=a.decisions)
                    self.assertEqual(r['corrected'],expected);self.assertEqual(r.get('odd_spans'),[])

    def test_open_native_continuations_keep_their_written_source(self):
        for source in ('用船して補正', '予約しまして、',
                       '履歴を買いますが', '透明度が高く'):
            with self.subTest(source=source):
                result=app.correct_line(source,self.a.store,input_method='kana',
                    dict_index=self.a.dict_index,decisions=self.a.decisions,
                    context_vec=None)
                self.assertEqual(result['corrected'],source)
                self.assertEqual(result.get('odd_spans'),[])

    def test_explicit_spelling_labels_protect_columns_inside_the_quote_only(self):
        from janome_import import import_from_janome
        a=initial()
        for phase in ('seed','fresh'):
            if phase=='fresh':import_from_janome(a.store)
            for label in ('文字列','表記','綴り'):
                for separator in (' ⇒ ',' → ','\t','    '):
                    for word in ('モーシろょん','まとがい'):
                        source=label+'「'+word+separator+'注」を確認します。'
                        with self.subTest(phase=phase,source=source):
                            r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                                context_vec=a.context_vec if phase=='fresh' else None,decisions=a.decisions)
                            self.assertEqual(r['corrected'],source)
                            self.assertEqual(r.get('odd_spans'),[])
            source='文字列「モーシろょん ⇒ 注」を確認します。モーシろょんを作ります。'
            r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=a.context_vec if phase=='fresh' else None,decisions=a.decisions)
            self.assertEqual(r['corrected'],'文字列「モーシろょん ⇒ 注」を確認します。モーションを作ります。')
            self.assertEqual(r.get('odd_spans'),[])

if __name__=='__main__':unittest.main()
