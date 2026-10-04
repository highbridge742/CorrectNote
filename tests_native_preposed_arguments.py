# -*- coding: utf-8 -*-
"""Unchanged preposed arguments and their original object share one action."""
from tests_spelling_reference import assert_reviewed_source_spelling
from tests_spelling_reference import assert_repaired_spelling
import unittest
import morphology as M
import reading_segments as R

@unittest.skipUnless(M.dictionary_inflections('先生'),'requires native dictionary')
class NativePreposedArgumentTests(unittest.TestCase):

    def test_short_written_arguments_keep_the_same_native_case_boundary(self):
        import contextual_repair as Q
        for text,written in (('鍋に水をいれる',False),('皿に肉を置く',True),
                             ('子に本を読む',True),('箱に本を置く',True)):
            with self.subTest(text=text):
                parts=R.native_preposed_object_parts(text,written)
                self.assertTrue(parts,text)
                self.assertTrue(any(cut==text.index('を')+1
                                    for edge,case,receiver,cut,objects in parts),text)
        for text in ('鍋に水を','鍋にをいれる','ぷねらに本を読む'):
            self.assertFalse(R.native_preposed_object_parts(text,True),text)
        for line,face in (('なべに水をいれます','鍋'),('さらに水をいれます','皿')):
            self.assertTrue(Q._changed_object_slot_allowed(line,0,2,face),(line,face))

    def test_source_ranges_include_written_and_kana_arguments(self):
        for text in ('せんせいにしりょうをおきります','先生に資料をおきります',
                     'ともだちにてがみをおきります','友達に手紙をおきります'):
            frames=R.native_object_predicate_frames(text)
            self.assertTrue(frames,text)
            self.assertTrue(any(cut==text.index('を')+1 for cut,faces in frames),text)
            for cut,faces in frames:
                self.assertFalse(R.native_object_predicate_proof(text,cut,faces),text)
                normal=text.replace('おきります','おくります')
                self.assertTrue(R.native_object_predicate_proof(normal,cut,faces),normal)
                self.assertTrue(R.native_object_predicate_proof(normal+'。',cut,faces),normal)

    def test_every_argument_keeps_its_written_meaning(self):
        for text in ('精度に資料をおくります','制度に資料をおくります','水に資料をおくります',
                     '先生に精度をおくります','先生に制度をよみます','先生に飼料をよみます'):
            frames=R.native_object_predicate_frames(text)
            self.assertTrue(frames,text)
            self.assertFalse(any(R.native_object_predicate_proof(text,cut,faces)
                                 for cut,faces in frames),text)

    def test_classified_whole_readings_keep_family_and_human_arguments(self):
        import semantic_roles as S
        for reading,face in (('かぞく','家族'),('わたし','私'),('おきゃくさま','お客様'),
                             ('とまと','トマト'),('しりょう','史料')):
            self.assertIn(face,R.native_nominal_phrase_faces(reading),reading)
        for text in ('かぞくにしりょうをおくります','わたしにほんをよんでくれます',
                     'おきゃくさまにおちゃをだします'):
            frames=R.native_object_predicate_contexts(text)
            self.assertTrue(frames,text)
            self.assertTrue(any(R.native_object_predicate_proof(text[begin:],cut-begin,faces)
                                for begin,cut,faces in frames),text)
        for noun in ('私','僕','彼女','お客様','父','母'):
            self.assertIn('person',S.nominal_roles(noun),noun)
        for noun in ('これ','それ','あれ','水','精度'):
            self.assertNotIn('person',S.nominal_roles(noun),noun)
        # 48-AMP: classified one-kana nouns retain exact native evidence.
        self.assertIn('子',R._classified_nominal_readings().get('こ',()))
        self.assertIn('目',R._classified_nominal_readings().get('め',()))
        # Lexical evidence is independent of a positive semantic-role inventory.
        self.assertTrue(R.native_common_noun_reading('木','き'))
        self.assertNotIn('木',R._classified_nominal_readings().get('き',()))
        self.assertFalse(R.completed_native_reading_clause('こをのみます',require_object_fit=True))

    def test_nominal_reading_with_adverbial_ni_keeps_positive_case_proof(self):
        for text in ('あににおちゃをだします','兄にお茶をだします',
                     'あににしりょうをおくります'):
            frames=R.native_object_predicate_contexts(text)
            self.assertTrue(frames,text)
            self.assertTrue(any(R.native_object_predicate_proof(text[begin:],cut-begin,faces)
                                for begin,cut,faces in frames),text)
        source='あににおちゃをだします'
        boundary=R.native_nominal_case_boundary(source,M.tokenize(source),2,'に',('兄',),
                                                allow_known_noun=True)
        self.assertEqual(boundary,('兄',True))
        for text in ('あににおちゃをのみます','あににせいどをだします',
                     'あににおちゃをだしますです','さらにおちゃをだします'):
            self.assertFalse(R.completed_native_reading_clause(text,require_object_fit=True),text)

    def test_written_receiver_shares_whole_original_intactness(self):
        import app
        from tests_analysis_async import initial
        from janome_import import import_from_janome
        a=initial();import_from_janome(a.store)
        for text in ('兄におちゃをだします。','姉におちゃをだします。',
                     '弟におちゃをだします。','妹におちゃをだします。',
                     '彼におちゃをだします。','彼女におちゃをだします。'):
            self.assertIn((0,len(text)-1),R.native_context_ranges(text),text)
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=a.context_vec,decisions=a.decisions)
            assert_reviewed_source_spelling(self, result['corrected'], text)
            self.assertEqual(result.get('odd_spans'),[])
        for text in ('兄におちゃをのみます','水におちゃをだします',
                     '兄におちゃをだしますです','兄にぷねらをだします'):
            self.assertNotIn((0,len(text)),R.native_context_ranges(text),text)

    def test_written_predicate_cannot_borrow_a_fitting_homophone_to_hide_a_source_conflict(self):
        for text in ('意見を繁栄します','騒動を収集します','人質を開放します',
                     '画面を長生します','ひらがなを漢字に返還します'):
            frames=R.native_object_predicate_contexts(text,allow_written_predicate=True)
            self.assertTrue(frames,text)
            for begin,cut,faces in frames:
                self.assertFalse(R.native_object_predicate_proof(text[begin:],cut-begin,faces),text)
            self.assertNotIn((0,len(text)),R.native_context_ranges(text),text)
        for text in ('意見を反映します','資料を収集します','人質を解放します',
                     '画面を調整します','ひらがなを漢字に変換します'):
            self.assertIn((0,len(text)),R.native_context_ranges(text),text)

    def test_written_predicate_shares_positive_source_proof_without_expanding_targets(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('ほんをにさつ読みます。','本をにさつ読みます。',
                     '資料をにさつ読みます。','しりょうをにさつ読みます。',
                     'おきゃくさまにしりょうを送ります。'):
            self.assertIn((0,len(text)-1),R.native_context_ranges(text),text)
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_reviewed_source_spelling(self, result['corrected'], text)
            self.assertEqual(result.get('odd_spans'),[])
        for text in ('ほんをにさつ飲みます','本をにさつ読みますです',
                     'おきゃくさまにしりょうを起きります'):
            self.assertNotIn((0,len(text)),R.native_context_ranges(text),text)
        self.assertFalse(R.native_object_predicate_contexts('ほんをにさつ読みます'))
        self.assertTrue(R.native_object_predicate_contexts('ほんをにさつ読みます',allow_written_predicate=True))

    def test_provision_uses_the_same_object_and_recipient_roles(self):
        import semantic_roles as S
        for noun in ('茶','水','料理','資料','手紙','お金'):
            self.assertTrue(S.support(noun,'出す'),noun)
        for person in ('客','お客様','先生','友人'):
            self.assertTrue(S.case_action_support(person,'に','出す'),person)
        self.assertFalse(S.case_action_support('水','に','出す'))
        self.assertFalse(S.case_action_support('精度','に','出す'))
        self.assertFalse(S.support('飼料','読む'))

    def test_marked_object_reuses_its_original_adverb_boundary(self):
        import app
        import contextual_repair as X
        import corrector as C
        from tests_analysis_async import initial
        a=initial();tokenize=C.make_tokenizer(a.store)
        for prefix in ('あしたまでに','しめきりまでに','じぶんで'):
            source=prefix+'しゃしまをならべます。'
            targets=X.targets_for_line(source,tokenize,a.store,a.dict_index)
            self.assertTrue(any(t.start==len(prefix) and t.text=='しゃしま'
                                and t.boundary_kind=='nominal_object' for t in targets),source)
            result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_repaired_spelling(self, result, (prefix+'しゃしんをならべます。',prefix+'写真をならべます。'))
            self.assertFalse(result.get('odd_spans'),source)
            normal=prefix+'しゃしんをならべます。'
            result=app.correct_line(normal,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_reviewed_source_spelling(self, result['corrected'], normal)
            self.assertFalse(result.get('odd_spans'),normal)
        source='ぷねらまでにしゃしまをならべます。'
        targets=X.targets_for_line(source,tokenize,a.store,a.dict_index)
        self.assertFalse(any(t.start==len('ぷねらまでに') and t.text=='しゃしま' for t in targets))
        for source in ('あしたまでにしゃしま','「あしたまでにしゃしま」と入力しました。'):
            result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],source)

    def test_temporal_prefix_keeps_its_separate_adverb_boundary(self):
        text='あさにつくったしりょうをせんせいにおきります'
        self.assertFalse(R.native_preposed_object_parts(text))
        self.assertTrue(R.native_object_predicate_contexts(text))

    def test_original_receiver_cannot_be_replaced_by_a_wider_predicate_proposal(self):
        import contextual_repair as C
        text='先生に資料をおきります'
        self.assertTrue(C.object_predicate_candidate_allowed(text,6,len(text),'おくります'))
        self.assertFalse(C.object_predicate_candidate_allowed(text,0,len(text),'水に資料をおくります'))
        self.assertFalse(C.object_predicate_candidate_allowed(text,0,len(text),'生徒に資料をおくります'))

    def test_wide_final_proposals_keep_the_same_source_arguments_and_action(self):
        import corrector as C
        from tests_analysis_async import initial
        a=initial();tokenize=C.make_tokenizer(a.store)
        for text in ('先生に資料をおきります','先生に資料をおきります。',
                     'せんせいにしりょうをおきります。'):
            good=text.replace('おき','おく')
            value,reason=C._check_replacement(text,(0,len(text),good,'かな入力'),
                a.store,tokenize,a.dict_index,a.decisions)
            self.assertIsNotNone(value,reason)
            for bad in (good.replace('先生','水').replace('せんせい','みず'),
                        good.replace('先生','生徒').replace('せんせい','せいと'),
                        text.replace('おき','のみ')):
                value,reason=C._check_replacement(text,(0,len(text),bad,'かな入力'),
                    a.store,tokenize,a.dict_index,a.decisions)
                self.assertIsNone(value,bad)

    def test_independent_clause_can_change_without_repairing_old_bad_predicate(self):
        import contextual_repair as C
        text='今日は休みです。先生に資料をおきります。'
        changed=text.replace('今日','明日')
        self.assertTrue(C.object_predicate_candidate_allowed(text,0,len(text),changed))
        changed=text.replace('今日は休みです。','明日です。').replace('おき','おく')
        self.assertTrue(C.object_predicate_candidate_allowed(text,0,len(text),changed))
        self.assertFalse(C.object_predicate_candidate_allowed(text,0,len(text),
            changed.replace('先生','水')))

    def test_completed_clause_and_action_note_keep_their_source_scope(self):
        import contextual_repair as C
        import app
        from tests_analysis_async import initial
        source='せつめいをきいてからじぶんてためしてみます。'
        self.assertTrue(C.object_predicate_candidate_allowed(source,13,14,'で'))
        self.assertTrue(C.object_predicate_candidate_allowed(source,0,len(source),source.replace('じぶんて','じぶんで')))
        note='ないようをせんこうしてほぞん'
        self.assertTrue(C.object_predicate_candidate_allowed(note,0,9,'ないようをへんこう'))
        self.assertTrue(C.object_predicate_candidate_allowed(note,0,len(note),note.replace('せんこう','へんこう')))
        self.assertFalse(C.object_predicate_candidate_allowed(note,0,len(note),'ねこをへんこうしてほぞん'))
        self.assertFalse(C.object_predicate_candidate_allowed(note,0,len(note),'ないようをこうこうしてほぞん'))
        a=initial()
        for text,expected in (('せつめいをきいてからじぶん゛てためしてみます。',source.replace('じぶんて','じぶんで')),
                ('こどもにえほんをよんであうげます。','こどもにえほんを読んであげます。'),
                (note,note.replace('せんこう','へんこう'))):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_repaired_spelling(self, result, expected)
            self.assertEqual(result.get('odd_spans'),[])

    def test_actual_repairs_and_normal_second_pass(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('せんせいにしりょうをおきります。','先生に資料をおきります。',
                     'ともだちにてがみをおきります。','友達に手紙をおきります。'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            expected=text.replace('おきります','送ります')
            assert_reviewed_source_spelling(self, result['corrected'], expected, text)
            normal=app.correct_line(expected,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_reviewed_source_spelling(self, normal['corrected'], expected)
            self.assertEqual(normal.get('odd_spans'),[],expected)

    def test_unknown_quoted_and_unmatched_receiver_remain_literal(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('精度に資料をおきります。','みずにしりょうをおきります。',
                     '「せんせいにしりょうをおきります」という例です。'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            expected='水にしりょうをおきります。' if text=='みずにしりょうをおきります。' else text
            self.assertEqual(result['corrected'],expected)

    def test_unknown_receiver_keeps_its_name_without_freezing_known_object(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        result=app.correct_line('ぷねらに資料をおきります。',a.store,input_method='kana',
            dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        self.assertEqual(result['corrected'],'ぷねらに資料を送ります。')
        unchanged=app.correct_line('ぷねらに資料を送ります。',a.store,input_method='kana',
            dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        self.assertEqual(result['odd_spans'],unchanged['odd_spans'])

    def test_nominal_slot_keeps_existing_source_mark_without_broad_request(self):
        import app,corrector as C,contextual_repair as X
        from tests_analysis_async import initial
        a=initial();tokenize=C.make_tokenizer(a.store)
        for prefix in ('さぎょうまえに','さぎょうごに'):
            source=prefix+'しゃしまをならべます。'
            targets=X.targets_for_line(source,tokenize,a.store,a.dict_index)
            self.assertFalse(any(t.boundary_kind=='kana_request' for t in targets))
            narrow=[t for t in targets if t.boundary_kind=='nominal_object'
                    and t.start==len(prefix) and t.text=='しゃしま']
            self.assertEqual(len(narrow),1)
            self.assertTrue(narrow[0].anomalies)
            result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_repaired_spelling(self, result, (prefix+'しゃしんをならべます。',prefix+'写真をならべます。'))
            self.assertFalse(result.get('odd_spans'))
            normal=prefix+'しゃしんをならべます。'
            self.assertFalse(X.targets_for_line(normal,tokenize,a.store,a.dict_index))
            result=app.correct_line(normal,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_reviewed_source_spelling(self, result['corrected'], normal)
            self.assertFalse(result.get('odd_spans'))
        for source in ('さぎょうまえにぷねらをならべます。','さぎょうまえにしゃしまをたべます。',
                       '「さぎょうまえにしゃしまをならべます」という入力例です。'):
            result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],source)

if __name__=='__main__':unittest.main()
