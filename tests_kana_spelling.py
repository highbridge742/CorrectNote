# -*- coding: utf-8 -*-
"""Kana spelling preserves meaning, explicit choices, fields and original coordinates."""
from tests_spelling_reference import assert_reviewed_source_spelling
import unittest
from unittest.mock import patch
import morphology as M
import reading_segments as R
import familiar_spelling as F

class KanaSpellingCoordinateTests(unittest.TestCase):
    def test_mixed_ime_reading_maps_back_to_original_positions(self):
        from types import SimpleNamespace as T
        from unittest.mock import Mock
        from ime_spelling import source_first_words
        tokens=[T(surface='資料',start=0,end=2,reading='しりょう',has_reading=True),
                T(surface='を',start=2,end=3,reading='を',has_reading=True),
                T(surface='よむ',start=3,end=5,reading='よむ',has_reading=True)]
        ime=Mock();ime.convert_words.return_value=('資料を読む',(
            (0,2,0,4,100,0),(2,3,4,5,0,0),(3,5,5,7,200,0)))
        with patch('morphology.tokenize',return_value=tokens),patch('morphology.native_spelling_only',return_value=True):
            first,words,reading,offsets=source_first_words('資料をよむ',ime)
        ime.convert_words.assert_called_once_with('しりょうをよむ')
        self.assertEqual(words,((0,2,0,2,100,0),(2,3,2,3,0,0),(3,5,3,5,200,0)))
        self.assertNotIn(1,offsets);self.assertNotIn(2,offsets)
        self.assertEqual(offsets[5],3)
        tokens[0].has_reading=False;ime.reset_mock()
        with patch('morphology.tokenize',return_value=tokens):
            self.assertIsNone(source_first_words('資料をよむ',ime))
        ime.convert_words.assert_not_called()

    def test_source_coordinates_survive_shortened_repairs_and_emoji(self):
        import corrector as E
        from kana_spelling import _compose_result
        source='😀しゅうありょうが\tのひっています'
        old=dict(corrected='😀しゅうりょうが\tのこっています',
                 original_spans=[(4,5),(11,12)],spans=[(4,4),(10,11)])
        result=_compose_result(source,old,[(1,7,'終了'),(9,12,'残っ')],E)
        self.assertEqual(result['corrected'],'😀終了が\t残っています')
        self.assertEqual(result['original_spans'],[(1,8),(10,13)])
        self.assertEqual(result['spans'],[(1,3),(5,7)])
        self.assertEqual([source[a:b] for a,b in result['original_spans']],['しゅうありょう','のひっ'])

    def test_adjacent_edits_and_repeated_words_keep_separate_source_ranges(self):
        import corrector as E
        from kana_spelling import _compose_result
        source='ゆうせんほせい\tゆうせん'
        r=_compose_result(source,dict(corrected=source),[(0,4,'優先'),(4,7,'補正'),(8,12,'優先')],E)
        self.assertEqual(r['corrected'],'優先補正\t優先')
        self.assertEqual(r['original_spans'],[(0,4),(4,7),(8,12)])
        self.assertEqual(r['spans'],[(0,2),(2,4),(5,7)])

    def test_spelling_touching_a_deleted_key_keeps_the_deletion(self):
        import corrector as E
        from kana_spelling import _compose_result
        left=dict(corrected='つたえたことで',original_spans=[(3,4)],spans=[(3,3)])
        result=_compose_result('つたえふたことで',left,[(0,3,'伝え')],E)
        self.assertEqual(result['corrected'],'伝えたことで')
        self.assertEqual(result['original_spans'],[(0,4)])
        self.assertEqual(result['spans'],[(0,2)])
        right=dict(corrected='ゆうせん',original_spans=[(0,1)],spans=[(0,0)])
        result=_compose_result('ふゆうせん',right,[(0,4,'優先')],E)
        self.assertEqual(result['corrected'],'優先')
        self.assertEqual(result['original_spans'],[(0,5)])

    def test_invalid_prior_mapping_is_not_guessed(self):
        import corrector as E
        from kana_spelling import _compose_result
        original='のひっています'
        old=dict(corrected='全く別の文章',original_spans=[(1,2)],spans=[(1,2)])
        self.assertIs(_compose_result(original,old,[(0,2,'残る')],E),old)

@unittest.skipUnless(M.HAS_JANOME,'requires native Janome dictionary')
class KanaSpellingNativeTests(unittest.TestCase):
    def test_preposed_whole_object_shares_the_native_negative_boundary(self):
        import ime_spelling as I
        source='学生達がないようをかきます'
        self.assertTrue(R.native_independent_object_reading(source,4,8))
        self.assertFalse(I._crosses_negative_attachment(source,4,8))
        self.assertFalse(I._reinterprets_function_attachment(source,4,8,'内容'))
        for text in ('教師が書かないようにします','内容を読まないようにします',
                     '教師がないようをぷねらします','ぷねらがないようをかきます',
                     '機械がないようをかきます','教師をないようをかきます',
                     '教師がないようにかきます','教師がないようをかきま'):
            start=text.index('ないよう')
            with self.subTest(text=text):
                self.assertFalse(R.native_independent_object_reading(text,start,start+4))
                self.assertTrue(I._crosses_negative_attachment(text,start,start+4))

    def test_preposed_whole_object_requires_both_arguments_and_exact_case(self):
        import semantic_roles as S,ime_spelling as I
        source='学生達がないようをかきます'
        for module,name,value in ((R,'native_preposed_object_parts',()),
                                  (R,'native_object_predicate_proof',False),
                                  (S,'proved_action_case_support',False)):
            R.native_independent_object_reading.cache_clear()
            with self.subTest(name=name),patch.object(module,name,return_value=value):
                self.assertFalse(R.native_independent_object_reading(source,4,8))
                self.assertTrue(I._crosses_negative_attachment(source,4,8))
            R.native_independent_object_reading.cache_clear()
        for start,end in ((3,8),(5,8),(4,7),(4,9)):
            self.assertFalse(R.native_independent_object_reading(source,start,end))
        actual=M.dictionary_inflections
        # The missing-dictionary fixture must invalidate the earlier true
        # case-entry cache, and must not leave its false result afterwards.
        R.native_nominal_case_reading.cache_clear()
        try:
            with patch.object(M,'dictionary_inflections',side_effect=lambda face:() if face=='を' else actual(face)):
                self.assertFalse(R.native_independent_object_reading(source,4,8))
        finally:
            R.native_nominal_case_reading.cache_clear()
            R.native_independent_object_reading.cache_clear()

    def test_preposed_whole_object_body_reaches_common_gate(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        source='学生達がないようをかきます。';seen=[];check=C._check_replacement
        def observed(line,replacement,*args,**kwargs):
            result=check(line,replacement,*args,**kwargs);seen.append((replacement[2],result[0] is not None));return result
        def analyze(text):
            a=initial();return app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        try:
            with patch.object(C,'_check_replacement',side_effect=observed):result=analyze(source)
            self.assertEqual(result['corrected'],'学生達が内容を書きます。')
            self.assertEqual(result['odd_spans'],[]);self.assertEqual(result['analysis_status'],'complete')
            self.assertIn(('内容',True),seen);self.assertIn(('書き',True),seen)
            with patch.object(C,'_check_replacement',return_value=(None,'test_common_gate')):
                self.assertEqual(analyze(source)['corrected'],source)
            quote='入力は「'+source+'」です。'
            self.assertEqual(analyze(quote)['corrected'],quote)
        finally:set_active(None)

    def test_native_te_auxiliary_seam_reaches_common_candidate_gate(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        source='私達がもじをかいています。';seen=[];check=C._check_replacement
        def observed(line,replacement,*args,**kwargs):
            result=check(line,replacement,*args,**kwargs);seen.append((replacement[2],result[0] is not None));return result
        def analyze(text):
            a=initial();return app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        try:
            with patch.object(C,'_check_replacement',side_effect=observed):result=analyze(source)
            self.assertEqual(result['corrected'],'私達が文字を書いています。')
            self.assertEqual(result['odd_spans'],[]);self.assertEqual(result['analysis_status'],'complete')
            self.assertIn(('文字',True),seen);self.assertIn(('書い',True),seen)
            self.assertEqual(result['original_spans'],[(3,5),(6,8)])
            with patch.object(C,'_check_replacement',return_value=(None,'test_common_gate')):
                self.assertEqual(analyze(source)['corrected'],source)
            quote='入力は「'+source+'」です。'
            self.assertEqual(analyze(quote)['corrected'],quote)
        finally:set_active(None)

    def test_native_te_auxiliary_seam_requires_the_original_chain(self):
        import copy,kana_spelling as K,contextual_repair as Q
        from tests_analysis_async import initial
        from last_choice import set_active
        source='私達が文字をかいています。';tokenize=M.tokenize;native=Q._native_te_auxiliary_tail
        def project():
            a=initial();return K.project(source,a.store,a.dict_index,a.decisions)
        try:
            # Losing the existing full native proof retains the older seam.
            with patch.object(Q,'_native_te_auxiliary_tail',side_effect=lambda forms,tail,reading,surface:
                    False if surface=='かい' else native(forms,tail,reading,surface)):
                self.assertIsNone(project())
            for field,value in (('has_reading',False),('pos_sub','自立'),('start',8)):
                parts=[copy.copy(t) for t in tokenize(source)]
                setattr(next(t for t in parts if t.start==9),field,value)
                with self.subTest(field=field),patch.object(M,'tokenize',side_effect=lambda text:
                        parts if text==source else tokenize(text)):
                    self.assertIsNone(project())
        finally:set_active(None)

    def test_plural_subject_keeps_the_entire_original_nominal(self):
        for noun in ('学生','教師','先生'):
            for suffix in ('たち','達'):
                subject=noun+suffix;head=subject+'がよくかいた'
                with self.subTest(subject=subject):
                    self.assertEqual(R._native_plural_subject_heads(head,len(subject),M.tokenize(head)),(noun,))
        for subject in ('機械達','ぷねら達','学生 達','学生\t達','達','学生達達','学生達の'):
            head=subject+'がよくかいた'
            with self.subTest(subject=subject):
                self.assertFalse(R._native_plural_subject_heads(head,len(subject),M.tokenize(head)))

    def test_plural_subject_requires_each_actual_token_and_native_proof(self):
        import copy
        head='学生達がよくかいた';parts=M.tokenize(head);dictionary=M.dictionary_inflections
        for index in range(2):
            for field,value in (('surface','別'),('reading','べつ'),('has_reading',False),('pos','副詞'),
                    ('pos_sub','一般別'),('base_form','別'),('infl_form','基本形'),('start',99),('end',99)):
                changed=[copy.copy(t) for t in parts];setattr(changed[index],field,value)
                with self.subTest(index=index,field=field):
                    self.assertFalse(R._native_plural_subject_heads(head,3,changed))
            removed=parts[index].surface
            with patch.object(M,'dictionary_inflections',side_effect=lambda word:
                    () if word==removed else dictionary(word)):
                self.assertFalse(R._native_plural_subject_heads(head,3,parts))
        for fake in ((),('機械',),('学生','先生')):
            with patch.object(R,'native_plural_nominal_heads',return_value=fake):
                self.assertFalse(R._native_plural_subject_heads(head,3,parts))
        self.assertFalse(R._native_plural_subject_heads(head,2,parts))

    def test_plural_subject_keeps_its_own_same_lexeme_meaning(self):
        import semantic_roles as S
        head='学生達がよくかいた';relative=('かいた',('が',));nouns=('内容',)
        self.assertTrue(R._native_subject_kana_verb_nominal(head,relative,nouns))
        self.assertTrue(R._native_subject_kana_verb_nominal('学生たちがよくかいた',relative,nouns))
        self.assertFalse(R._native_subject_kana_verb_nominal(head,relative,('内容','ぷねら')))
        self.assertFalse(R._native_subject_kana_verb_nominal(head,relative,nouns,candidate_face='描い'))
        subject=S.subject_candidate_evidence
        with patch.object(S,'subject_candidate_evidence',side_effect=lambda noun,*a,**kw:
                None if noun=='学生' else subject(noun,*a,**kw)):
            self.assertFalse(R._native_subject_kana_verb_nominal(head,relative,nouns))
        written='学生達がよく書いた'
        self.assertTrue(R._native_subject_kana_verb_nominal(written,('書いた',('が',)),nouns,allow_written=True))
        self.assertFalse(R._native_subject_kana_verb_nominal(written,('書いた',('が',)),nouns))

    def test_plural_subject_body_keeps_the_common_final_gate(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        source='学生達がよくかいたないようを保存します。';check=C._check_replacement;seen=[]
        def observed(line,replacement,*args,**kwargs):
            result=check(line,replacement,*args,**kwargs)
            seen.append((replacement[:3],result[0] is not None));return result
        def analyze(text):
            a=initial();return app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        try:
            with patch.object(C,'_check_replacement',side_effect=observed):result=analyze(source)
            self.assertEqual(result['corrected'],'学生達がよく書いた内容を保存します。')
            self.assertEqual(result['odd_spans'],[]);self.assertEqual(result['analysis_status'],'complete')
            self.assertEqual(result['original_spans'],[(6,8),(9,13)])
            self.assertTrue(any(face=='書い' and ok for (a,b,face),ok in seen))
            self.assertTrue(any(face=='内容' and ok for (a,b,face),ok in seen))
            with patch.object(C,'_check_replacement',return_value=(None,'test_forced_reject')):
                rejected=analyze(source)
            self.assertEqual(rejected['corrected'],source);self.assertEqual(rejected['analysis_status'],'complete')
            literal='入力は「'+source+'」です。'
            self.assertEqual(analyze(literal)['corrected'],literal)
        finally:set_active(None)

    def test_coordinated_subject_owns_all_original_members(self):
        for head,end,expected in (('教師と講師がゆっくりかいた',5,('教師','講師')),
                ('先生と学生がよくよんだ',5,('先生','学生')),
                ('教師と講師と学生がすぐかく',8,('教師','講師','学生'))):
            with self.subTest(head=head):
                self.assertEqual(R._native_coordinated_subject_heads(head,end,M.tokenize(head)),expected)
        for subject in ('教師とぷねら','ぷねらと講師','教師や講師','教師 と講師','教師\tと講師','教師⇒と講師','教師との講師'):
            head=subject+'がよくかいた'
            with self.subTest(subject=subject):
                self.assertFalse(R._native_coordinated_subject_heads(head,len(subject),M.tokenize(head)))

    def test_coordinated_subject_requires_every_original_token_and_dictionary(self):
        import copy
        head='教師と講師がゆっくりかいた';parts=M.tokenize(head);dictionary=M.dictionary_inflections
        for index in range(3):
            for field,value in (('surface','別'),('reading','べつ'),('has_reading',False),('pos','副詞'),
                    ('pos_sub','一般別'),('base_form','別'),('infl_form','基本形'),('start',99),('end',99)):
                changed=[copy.copy(t) for t in parts];setattr(changed[index],field,value)
                with self.subTest(index=index,field=field):
                    self.assertFalse(R._native_coordinated_subject_heads(head,5,changed))
            removed=parts[index].surface
            with patch.object(M,'dictionary_inflections',side_effect=lambda word:
                    () if word==removed else dictionary(word)):
                self.assertFalse(R._native_coordinated_subject_heads(head,5,parts))
        with patch.object(R,'native_coordinated_nominal_parts',return_value=('講師',)):
            self.assertFalse(R._native_coordinated_subject_heads(head,5,parts))
        self.assertFalse(R._native_coordinated_subject_heads(head,4,parts))

    def test_coordinated_subject_requires_each_own_same_lexeme_meaning(self):
        import semantic_roles as S
        head='教師と講師がゆっくりかいた';relative=('かいた',('が',));nouns=('文章',)
        self.assertTrue(R._native_subject_kana_verb_nominal(head,relative,nouns))
        self.assertFalse(R._native_subject_kana_verb_nominal(head,relative,('文章','ぷねら')))
        self.assertFalse(R._native_subject_kana_verb_nominal(head,relative,nouns,candidate_face='描い'))
        subject=S.subject_candidate_evidence
        for omitted in ('教師','講師'):
            with patch.object(S,'subject_candidate_evidence',side_effect=lambda noun,*a,**kw:
                    None if noun==omitted else subject(noun,*a,**kw)):
                self.assertFalse(R._native_subject_kana_verb_nominal(head,relative,nouns))
        written='教師と講師がゆっくり書いた'
        self.assertTrue(R._native_subject_kana_verb_nominal(written,('書いた',('が',)),nouns,allow_written=True))
        self.assertFalse(R._native_subject_kana_verb_nominal(written,('書いた',('が',)),nouns))

    def test_coordinated_subject_body_preserves_common_gate(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        source='教師と講師がゆっくりかいたぶんしょうを保存します。'
        check=C._check_replacement;seen=[]
        def observed(line,replacement,*args,**kwargs):
            result=check(line,replacement,*args,**kwargs)
            seen.append((replacement[:3],result[0] is not None));return result
        def analyze(text):
            a=initial();return app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        try:
            with patch.object(C,'_check_replacement',side_effect=observed):result=analyze(source)
            self.assertEqual(result['corrected'],'教師と講師がゆっくり書いた文章を保存します。')
            self.assertEqual(result['odd_spans'],[]);self.assertEqual(result['analysis_status'],'complete')
            self.assertEqual(result['original_spans'],[(10,12),(13,18)])
            self.assertTrue(any(face=='書い' and ok for (a,b,face),ok in seen))
            self.assertTrue(any(face=='文章' and ok for (a,b,face),ok in seen))
            with patch.object(C,'_check_replacement',return_value=(None,'test_forced_reject')):
                rejected=analyze(source)
            self.assertEqual(rejected['corrected'],source);self.assertEqual(rejected['analysis_status'],'complete')
            literal='入力は「'+source+'」です。'
            self.assertEqual(analyze(literal)['corrected'],literal)
        finally:set_active(None)

    def test_quantity_country_ambiguity_preserves_unresolved_source(self):
        import app
        from tests_analysis_async import initial
        from last_choice import set_active
        try:
            for source,completed in (('にほんの文化','日本の文化'),('にほんの会社','日本の会社'),
                    ('にほんの鉄道について説明する','日本の鉄道について説明する')):
                a=initial();r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
                # This safety contract does not weaken the older complete
                # spelling expectation. A future proved country may finish it.
                with self.subTest(source=source):
                    self.assertIn(r['corrected'],(source,completed));self.assertEqual(r['analysis_status'],'complete')
                    self.assertNotIn('二本',r['corrected'])
        finally:set_active(None)

    def test_quantity_country_ambiguity_retains_positive_source_relation(self):
        import context_meaning as X,kana_spelling as K
        from tests_analysis_async import initial
        from last_choice import set_active
        a=initial()
        try:
            source='にほんの線'
            proof=X.nominal_spelling_context_evidence(source,0,3,'二本')
            self.assertTrue(proof);self.assertEqual(proof['expected_role'],'linear_quantity')
            self.assertIsNone(X.nominal_spelling_context_evidence(source,1,3,'二本'))
            self.assertIsNone(X.nominal_spelling_context_evidence('にほんの文化',0,3,'二本'))
            self.assertIsNone(X.nominal_spelling_context_evidence('にほんの線と韓国の線',0,3,'二本'))
            result=K.project(source,a.store,a.dict_index,a.decisions)
            self.assertIsNotNone(result);self.assertEqual(result[0],'二本の線')
            with patch.object(X,'contexts',return_value=()):
                result=K.project(source,a.store,a.dict_index,a.decisions)
                self.assertTrue(result is None or result[0]!= '二本の線')
        finally:set_active(None)

    def test_quantity_country_ambiguity_keeps_dictionary_and_explicit_choice(self):
        import context_meaning as X,kana_spelling as K
        from tests_analysis_async import initial
        from last_choice import set_active
        a=initial();source='にほんの文化'
        try:
            countries=X._native_country_readings()['にほん'];self.assertIn('日本',countries)
            self.assertTrue(M.native_spelling_only('にほん','日本'))
            with patch.object(X,'_native_country_readings',return_value={}):
                result=K.project(source,a.store,a.dict_index,a.decisions)
                self.assertIsNotNone(result);self.assertEqual(result[0],'二本の文化')
            with patch('last_choice.surface_for_reading',side_effect=lambda rd:'二本' if rd=='にほん' else None):
                result=K.project(source,a.store,a.dict_index,a.decisions)
                self.assertIsNotNone(result);self.assertEqual(result[0],'二本の文化')
        finally:set_active(None)

    def test_quantity_country_ambiguity_preserves_common_gate_and_literals(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        check=C._check_replacement;seen=[]
        def observed(line,replacement,*args,**kwargs):
            result=check(line,replacement,*args,**kwargs);seen.append((replacement[2],result[0] is not None));return result
        def analyze(text):
            a=initial();return app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        try:
            with patch.object(C,'_check_replacement',side_effect=observed):result=analyze('にほんの線')
            self.assertEqual(result['corrected'],'二本の線');self.assertIn(('二本',True),seen)
            with patch.object(C,'_check_replacement',return_value=(None,'test_forced_reject')):
                self.assertEqual(analyze('にほんの線')['corrected'],'にほんの線')
            for source in ('日本の文化','二本の文化','「にほんの文化」という文字列'):
                with self.subTest(source=source):self.assertEqual(analyze(source)['corrected'],source)
        finally:set_active(None)

    def test_genitive_subject_owns_whole_original_phrase(self):
        for head,end in (('二人の先生がゆっくりかかなかった',5),('私の先生がよくかく',4)):
            with self.subTest(head=head):
                self.assertEqual(R._native_genitive_subject_heads(head,end,M.tokenize(head)),('先生',))
        for subject in ('ぷねらの先生','私のぷねら','私を先生','私 の先生','私\tの先生','私のの先生'):
            head=subject+'がよんだ'
            with self.subTest(subject=subject):
                self.assertFalse(R._native_genitive_subject_heads(head,len(subject),M.tokenize(head)))
        # A surface containing no-like letters cannot invent its own particle.
        head='もののけがよんだ'
        with patch.object(R,'native_genitive_nominal_splits',return_value=((1,('も',),('のけ',)),)):
            self.assertFalse(R._native_genitive_subject_heads(head,4,M.tokenize(head)))

    def test_genitive_subject_requires_each_original_token_and_dictionary(self):
        from types import SimpleNamespace as T
        tokenize=M.tokenize;dictionary=M.dictionary_inflections
        for head,end in (('二人の先生がよんだ',5),('私の先生がよんだ',4)):
            original=tokenize(head)
            for index,token in enumerate(original):
                if token.start>=end:continue
                for attribute,value in (('reading','別読み'),('has_reading',False),('surface','別語'),
                        ('pos','記号'),('pos_sub','別分類'),('base_form','別語'),('infl_form','別活用'),
                        ('start',token.start+1),('end',token.end+1)):
                    changed=[T(**{k:getattr(t,k) for k in t.__slots__}) for t in original]
                    setattr(changed[index],attribute,value)
                    with self.subTest(head=head,index=index,attribute=attribute):
                        self.assertFalse(R._native_genitive_subject_heads(head,end,changed))
                    with self.subTest(parsed=head,index=index,attribute=attribute),patch.object(M,'tokenize',side_effect=lambda x:changed if x==head else tokenize(x)):
                        self.assertFalse(R._native_genitive_subject_heads(head,end,changed))
                with self.subTest(dictionary=token.surface),patch.object(M,'dictionary_inflections',side_effect=lambda x:() if x==token.surface else dictionary(x)):
                    self.assertFalse(R._native_genitive_subject_heads(head,end,original))
        head='私の先生がよんだ'
        for splits in ((),((1,(),('先生',)),),((1,('私',),()),),((2,('私',),('先生',)),)):
            with self.subTest(splits=splits),patch.object(R,'native_genitive_nominal_splits',return_value=splits):
                self.assertFalse(R._native_genitive_subject_heads(head,4,tokenize(head)))

    def test_genitive_subject_keeps_same_lexeme_and_outer_clause(self):
        import semantic_roles as S,kana_spelling as K
        for head,relative,nouns,written in (
                ('二人の先生がゆっくりかかなかった','かかなかった',('文章',),False),
                ('二人の先生がゆっくり書かなかった','書かなかった',('文章',),True),
                ('私の先生がよくよんだ','よんだ',('内容',),False)):
            proof=lambda:R._native_subject_kana_verb_nominal(head,(relative,('が',)),nouns,allow_written=written)
            with self.subTest(head=head):self.assertTrue(proof())
            for function in ('subject_candidate_evidence','candidate_evidence'):
                with self.subTest(head=head,function=function),patch.object(S,function,return_value=None):self.assertFalse(proof())
            with patch.object(R,'_completed_native_verb_surface',return_value=False):self.assertFalse(proof())
            with patch.object(R,'_native_genitive_subject_heads',return_value=('先生','ぷねら')):self.assertFalse(proof())
        source='私の先生がよくかいたぶんしょうを記録します'
        self.assertTrue(K._subject_verb_relative_boundaries(source))
        for bad in (source.replace('先生','機械'),source.replace('ぶんしょう','ぷねら'),source.replace('記録','ぷねら'),
                    source.replace('します','して'),source.replace('します','しますです')):
            with self.subTest(source=bad):self.assertFalse(K._subject_verb_relative_boundaries(bad))

    def test_genitive_subject_body_preserves_common_gate(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        sources=[('二人の先生がゆっくりかかなかったぶんしょうを記録します','二人の先生がゆっくり書かなかった文章を記録します'),
                 ('私の先生がよくかくないようを共有します','私の先生がよく書く内容を共有します')]
        seen=[];check=C._check_replacement
        def observed(line,replacement,*args,**kwargs):
            r=check(line,replacement,*args,**kwargs);seen.append((replacement[2],r[0] is not None));return r
        def analyze(text):
            a=initial();return app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        try:
            for source,expected in sources:
                seen.clear()
                with patch.object(C,'_check_replacement',side_effect=observed):r=analyze(source)
                with self.subTest(source=source):
                    self.assertEqual(r['corrected'],expected);self.assertFalse(r['odd_spans']);self.assertEqual(r['analysis_status'],'complete')
                    self.assertTrue(any(face.startswith('書') and allowed for face,allowed in seen))
                with patch.object(C,'_check_replacement',return_value=(None,'test_forced_reject')):
                    self.assertEqual(analyze(source)['corrected'],source)
            source=sources[1][0]
            for text in (source.replace('共有','ぷねら'),source.replace('共有します','共有して'),
                         '入力は「'+source+'」です。',source+'という文字列です。'):
                with self.subTest(text=text):self.assertEqual(analyze(text)['corrected'],text)
        finally:set_active(None)

    def test_single_na_boundary_owns_stem_and_particle(self):
        for text,edge in (('丁寧に書かなかった',3),('丁寧に読んだ',3),('ていねいにかかなかった',5)):
            with self.subTest(text=text):self.assertIn(edge,R.native_adverbial_reading_cuts(text))
        for text,edge in (('丁寧を読んだ',3),('丁寧で読んだ',3),('丁寧 に読んだ',4),
                          ('丁寧\tに読んだ',4),('しずかにゆっくりよんだ',8),('ぷねらに読んだ',4)):
            with self.subTest(text=text):self.assertNotIn(edge,R.native_adverbial_reading_cuts(text))

    def test_single_na_boundary_requires_each_own_token(self):
        from types import SimpleNamespace as T
        text='丁寧に書かなかった';tokenize=M.tokenize;dictionary=M.dictionary_inflections
        cuts=R.native_adverbial_reading_cuts.__wrapped__
        for start in (0,2):
            for attribute,value in (('reading','別読み'),('has_reading',False),('surface','別語'),('pos','記号'),
                    ('pos_sub','別分類'),('base_form','別語'),('infl_form','別活用'),('start',start+1),('end',start+5)):
                changed=[T(**{k:getattr(t,k) for k in t.__slots__}) for t in tokenize(text)]
                setattr(next(t for t in changed if t.start==start),attribute,value)
                with self.subTest(start=start,attribute=attribute),patch.object(M,'tokenize',side_effect=lambda x:changed if x==text else tokenize(x)):
                    self.assertNotIn(3,cuts(text))
        for word in ('丁寧','に'):
            with self.subTest(word=word),patch.object(M,'dictionary_inflections',side_effect=lambda x:() if x==word else dictionary(x)):
                self.assertNotIn(3,cuts(text))
        for start,kind in ((0,'一般'),(2,'格助詞:一般')):
            changed=[T(**{k:getattr(t,k) for k in t.__slots__}) for t in tokenize(text)]
            next(t for t in changed if t.start==start).pos_sub=kind
            with self.subTest(kind=kind),patch.object(M,'tokenize',side_effect=lambda x:changed if x==text else tokenize(x)):
                self.assertNotIn(3,cuts(text))

    def test_single_na_boundary_keeps_candidate_clause_proofs(self):
        import kana_spelling as K,semantic_roles as S,contextual_repair as Q
        source='先生がていねいに書かなかった文章を共有します'
        self.assertTrue(Q.object_predicate_candidate_allowed(source,3,7,'丁寧',spelling=True))
        raw='先生がていねいにかかなかったぶんしょうを共有します'
        self.assertEqual(K._subject_verb_relative_boundaries(raw),(8,10,14,19))
        for function in ('subject_candidate_evidence','candidate_evidence'):
            with patch.object(S,function,return_value=None):self.assertFalse(K._subject_verb_relative_boundaries(raw))
        for bad in (raw.replace('先生','機械'),raw.replace('ぶんしょう','ぷねら'),raw.replace('共有','ぷねら'),
                    raw.replace('します','して'),raw.replace('します','しますです')):
            with self.subTest(source=bad):self.assertFalse(K._subject_verb_relative_boundaries(bad))

    def test_single_na_boundary_body_and_common_gate(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        source='先生がていねいにかかなかったぶんしょうを共有します';seen=[];check=C._check_replacement
        def observed(line,replacement,*args,**kwargs):
            r=check(line,replacement,*args,**kwargs);seen.append((tuple(replacement[:3]),r[0] is not None));return r
        def analyze(text):
            a=initial();return app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        try:
            with patch.object(C,'_check_replacement',side_effect=observed):r=analyze(source)
            self.assertEqual(r['corrected'],'先生が丁寧に書かなかった文章を共有します')
            self.assertEqual(r['analysis_status'],'complete');self.assertFalse(r['odd_spans'])
            self.assertEqual(r['original_spans'],[(3,7),(8,10),(14,19)])
            self.assertTrue(any(rep[2]=='丁寧' and accepted for rep,accepted in seen))
            self.assertTrue(any(rep[2]=='書か' and accepted for rep,accepted in seen))
            with patch.object(C,'_check_replacement',return_value=(None,'test_forced_reject')):
                self.assertEqual(analyze(source)['corrected'],source)
            for text in (source.replace('共有','ぷねら'),source.replace('共有します','共有して'),
                         '入力は「'+source+'」です。',source+'という文字列です。'):
                self.assertEqual(analyze(text)['corrected'],text)
        finally:set_active(None)

    def test_na_modifier_edge_is_own_grammar_not_usage_or_a_noun_slot(self):
        import kango_tier as T
        source='先生がいつもていねいに書く内容を記録します'
        self.assertTrue(R.native_adverbial_stem_spelling(source,6,10,'丁寧'))
        self.assertTrue(R.native_adverbial_stem_spelling(source,6,10,'叮嚀'))
        self.assertEqual(T.usage_tier_for_reading('丁寧','ていねい'),1)
        self.assertEqual(T.usage_tier_for_reading('叮嚀','ていねい'),3)
        for bad in ('いつもていねいに書く内容','先生がいつもていねいで書く内容',
                    '先生がいつもていねいを読む内容','先生がいつも\tていねいに書く内容'):
            a=bad.index('ていねい')
            with self.subTest(text=bad):self.assertFalse(R.native_adverbial_stem_spelling(bad,a,a+4,'丁寧'))
        self.assertFalse(R.native_adverbial_stem_spelling(source,6,10,'内容'))
        self.assertFalse(R.native_adverbial_stem_spelling(source,7,10,'丁寧'))

    def test_na_modifier_edge_requires_original_and_candidate_token_identity(self):
        from types import SimpleNamespace as T
        source='先生がいつもていねいに書く内容を記録します'
        changed=source.replace('ていねい','丁寧');tokenize=M.tokenize;dictionary=M.dictionary_inflections
        for text,target in ((source,6),(source,10),(changed,6),(changed,8)):
            for attribute,value in (('reading','べつ'),('has_reading',False),('surface','別'),('pos','記号'),
                    ('pos_sub','一般'),('base_form','別'),('infl_form','基本形'),('start',target+1),('end',target+3)):
                parts=[T(**{k:getattr(t,k) for k in t.__slots__}) for t in tokenize(text)]
                setattr(next(t for t in parts if t.start==target),attribute,value)
                with self.subTest(text=text,target=target,attribute=attribute),patch.object(M,'tokenize',side_effect=lambda x:parts if x==text else tokenize(x)):
                    self.assertFalse(R.native_adverbial_stem_spelling(source,6,10,'丁寧'))
        for word in ('ていねい','丁寧','に','が'):
            with self.subTest(word=word),patch.object(M,'dictionary_inflections',side_effect=lambda x:() if x==word else dictionary(x)):
                self.assertFalse(R.native_adverbial_stem_spelling(source,6,10,'丁寧'))
        with patch.object(R,'native_adverbial_reading_cuts',return_value=()):
            self.assertFalse(R.native_adverbial_stem_spelling(source,6,10,'丁寧'))

    def test_na_modifier_retention_rechecks_original_subject_and_candidate_frame(self):
        source='せんせいがいつもていねいにかくないようを記録します'
        changes=[(0,4,'先生'),(13,15,'書く'),(15,19,'内容')]
        self.assertTrue(R.native_dictionary_relative_retention(source,changes,8,12,'丁寧'))
        self.assertFalse(R.native_dictionary_relative_retention(source,changes[1:],8,12,'丁寧'))
        self.assertFalse(R.native_dictionary_relative_retention(source,changes,8,12,'内容'))
        self.assertFalse(R.native_dictionary_relative_retention(source,changes+[(5,8,'時々')],8,12,'丁寧'))
        for function,value in (('native_dictionary_subject_spelling',None),('native_adverbial_stem_spelling',False),
                               ('_native_subject_kana_verb_nominal',False),('native_object_predicate_proof',False)):
            with self.subTest(function=function),patch.object(R,function,return_value=value):
                self.assertFalse(R.native_dictionary_relative_retention(source,changes,8,12,'丁寧'))

    def test_na_modifier_body_keeps_usage_common_gate_and_original_offsets(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        source='せんせいがいつもていねいにかくないようを記録します';seen=[];check=C._check_replacement
        def observed(line,replacement,*args,**kwargs):
            r=check(line,replacement,*args,**kwargs);seen.append((tuple(replacement[:3]),r[0] is not None));return r
        def analyze(text):
            a=initial();return app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        try:
            with patch.object(C,'_check_replacement',side_effect=observed):r=analyze(source)
            self.assertEqual(r['corrected'],'先生がいつも丁寧に書く内容を記録します')
            self.assertEqual(r['analysis_status'],'complete');self.assertFalse(r['odd_spans'])
            self.assertEqual(r['original_spans'],[(0,4),(8,12),(13,15),(15,19)])
            self.assertTrue(any(rep[2]=='丁寧' and accepted for rep,accepted in seen))
            self.assertFalse(any(rep[2]=='叮嚀' for rep,accepted in seen))
            with patch.object(C,'_check_replacement',return_value=(None,'test_forced_reject')):
                self.assertEqual(analyze(source)['corrected'],source)
            for text in (source.replace('記録','ぷねら'),source.replace('記録します','記録して'),
                         '入力は「'+source+'」です。',source+'という文字列です。'):
                self.assertEqual(analyze(text)['corrected'],text)
        finally:set_active(None)

    def test_na_sequence_whole_actual_stem_and_particle(self):
        for text,cuts in (('いつもていねいにかいた',(3,8)),('ていねいにゆっくりよんだ',(5,9)),
                          ('やさしくていねいによんだ',(4,9)),('いつも丁寧に書いた',(3,6)),
                          ('丁寧にゆっくり読んだ',(7,))):
            with self.subTest(text=text):self.assertEqual(R.native_adverbial_reading_cuts(text),cuts)
        self.assertEqual(R.native_adverbial_reading_cuts('ていねいにかいた'),(5,))
        for text,edge in (('いつもていねいでかいた',8),('いつもていねいをかいた',8),
                          ('いつもていねい\tにかいた',9),('いつもていねい にかいた',9),
                          ('いつもぷねらにかいた',7),('しずかにゆっくりよんだ',8),
                          ('いつもていねいに本をかいた',9)):
            with self.subTest(text=text):self.assertNotIn(edge,R.native_adverbial_reading_cuts(text))

    def test_na_sequence_each_original_dictionary_and_coordinate(self):
        from types import SimpleNamespace as T
        text='いつもていねいにかいた';tokenize=M.tokenize;dictionary=M.dictionary_inflections
        cuts=R.native_adverbial_reading_cuts.__wrapped__
        for start in (0,3,7):
            for attribute,value in (('reading','別読み'),('has_reading',False),('surface','別語'),('pos','記号'),
                    ('pos_sub','別分類'),('base_form','別語'),('infl_form','別活用'),('start',start+1),('end',start+2)):
                changed=[T(**{k:getattr(t,k) for k in t.__slots__}) for t in tokenize(text)]
                setattr(next(t for t in changed if t.start==start),attribute,value)
                with self.subTest(start=start,attribute=attribute),patch.object(M,'tokenize',side_effect=lambda x:changed if x==text else tokenize(x)):
                    self.assertNotIn(8,cuts(text))
        for word in ('いつも','ていねい','に'):
            with self.subTest(word=word),patch.object(M,'dictionary_inflections',side_effect=lambda x:() if x==word else dictionary(x)):
                self.assertNotIn(8,cuts(text))
        for start,kind in ((3,'一般'),(7,'格助詞:一般')):
            changed=[T(**{k:getattr(t,k) for k in t.__slots__}) for t in tokenize(text)]
            next(t for t in changed if t.start==start).pos_sub=kind
            with self.subTest(kind=kind),patch.object(M,'tokenize',side_effect=lambda x:changed if x==text else tokenize(x)):
                self.assertNotIn(8,cuts(text))

    def test_na_sequence_written_stem_has_own_identity(self):
        from types import SimpleNamespace as T
        tokenize=M.tokenize;dictionary=M.dictionary_inflections
        text='いつも丁寧に書いた';cuts=R.native_adverbial_reading_cuts.__wrapped__
        self.assertIn(6,cuts(text))
        for attribute,value in (('reading','べつ'),('has_reading',False),('surface','別'),('pos','副詞'),
                ('pos_sub','一般'),('base_form','別'),('infl_form','基本形'),('start',4),('end',6)):
            changed=[T(**{k:getattr(t,k) for k in t.__slots__}) for t in tokenize(text)]
            setattr(next(t for t in changed if t.start==3),attribute,value)
            with self.subTest(attribute=attribute),patch.object(M,'tokenize',side_effect=lambda x:changed if x==text else tokenize(x)):
                self.assertNotIn(6,cuts(text))
        with patch.object(M,'dictionary_inflections',side_effect=lambda x:() if x=='丁寧' else dictionary(x)):
            self.assertNotIn(6,cuts(text))
        for bad in ('いつも丁寧で書いた','いつも丁寧を読んだ','いつも丁寧\tに書いた','いつも書類に書いた'):
            with self.subTest(text=bad):self.assertNotIn(6,cuts(bad))

    def test_na_sequence_requires_source_and_candidate_meanings(self):
        import kana_spelling as K,semantic_roles as S
        source='先生がいつもていねいにかいたないようを保存します'
        self.assertEqual(K._subject_verb_relative_boundaries(source),(11,13,14,18))
        for function in ('subject_candidate_evidence','candidate_evidence'):
            with patch.object(S,function,return_value=None):self.assertFalse(K._subject_verb_relative_boundaries(source))
        for bad in (source.replace('先生','機械'),source.replace('ないよう','ぷねら'),source.replace('保存','ぷねら'),
                    source.replace('します','して'),source.replace('します','しますです'),source.replace('ていねい','\tていねい')):
            with self.subTest(source=bad):self.assertFalse(K._subject_verb_relative_boundaries(bad))

    def test_na_sequence_body_and_common_gate(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        source='先生がいつもていねいにかいたないようを保存します';seen=[];check=C._check_replacement
        def observed(line,replacement,*args,**kwargs):
            r=check(line,replacement,*args,**kwargs);seen.append((tuple(replacement[:3]),r[0] is not None));return r
        def analyze(text):
            a=initial();return app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        try:
            with patch.object(C,'_check_replacement',side_effect=observed):r=analyze(source)
            self.assertEqual(r['corrected'],'先生がいつも丁寧に書いた内容を保存します')
            self.assertEqual(r['analysis_status'],'complete');self.assertFalse(r['odd_spans'])
            self.assertEqual(r['original_spans'],[(6,10),(11,13),(14,18)])
            self.assertTrue(any(rep[2]=='丁寧' and accepted for rep,accepted in seen))
            self.assertTrue(any(rep[2]=='書い' and accepted for rep,accepted in seen))
            with patch.object(C,'_check_replacement',return_value=(None,'test_forced_reject')):
                self.assertEqual(analyze(source)['corrected'],source)
            for text in (source.replace('保存','ぷねら'),source.replace('保存します','保存して'),
                         '入力は「'+source+'」です。',source+'という文字列です。'):
                self.assertEqual(analyze(text)['corrected'],text)
        finally:set_active(None)

    def test_final_particle_relative_keeps_two_original_analyses(self):
        import kana_spelling as K
        source='先生がいつもくわしくかいたぶんしょう'
        before=M.tokenize(source)
        owner=next(t for t in before if t.start==10)
        self.assertEqual((owner.surface,owner.reading,owner.pos,owner.pos_sub,owner.end),('かい','かい','助詞','終助詞',12))
        proof=R.native_bound_relative_nominal_parts(source)
        self.assertEqual(proof[:4],(13,('文章',),10,12))
        verb=next(t for t in proof[4] if t.start==10)
        self.assertEqual((verb.surface,verb.reading,verb.pos,verb.base_form,verb.infl_form,verb.end),('かい','かい','動詞','かく','連用タ接続',12))
        self.assertNotIn(13,R.native_relative_nominal_cuts(source,before))
        full=source+'を確認します';original=M.tokenize(full)
        rebuilt,edges=K._relative_source_parts(full,original)
        self.assertEqual(edges,(10,12,13,18))
        self.assertEqual(''.join(t.surface for t in rebuilt),full)
        self.assertTrue(all(full[t.start:t.end]==t.surface for t in rebuilt))
        self.assertEqual(next(t for t in rebuilt if t.start==12).surface,'た')
        self.assertEqual(next(t for t in original if t.start==10).pos,'助詞')
        with patch.object(R,'native_bound_relative_nominal_parts',return_value=()):
            self.assertEqual(K._relative_source_parts(full,original),(original,()))

    def test_final_particle_relative_attests_whole_source_and_prefix(self):
        from types import SimpleNamespace as T
        source='先生がいつもくわしくかいたぶんしょう';head=source[:13]
        tokenize=M.tokenize;dictionary=M.dictionary_inflections
        for target,start in ((source,10),(head,10),(head,12),(head,6)):
            for attribute,value in (('reading','別読み'),('has_reading',False),('surface','別語'),
                    ('pos','記号'),('pos_sub','別分類'),('base_form','別語'),('infl_form','別活用'),
                    ('start',start+1),('end',start+1)):
                changed=[T(**{k:getattr(t,k) for k in t.__slots__}) for t in tokenize(target)]
                setattr(next(t for t in changed if t.start==start),attribute,value)
                with self.subTest(target=target,start=start,attribute=attribute),patch.object(M,'tokenize',side_effect=lambda x:changed if x==target else tokenize(x)):
                    self.assertFalse(R.native_bound_relative_nominal_parts(source))
        for role in ('助詞,終助詞,','動詞,自立,'):
            with self.subTest(missing_role=role),patch.object(M,'dictionary_inflections',side_effect=lambda x:
                    tuple(row for row in dictionary(x) if not row[0].startswith(role)) if x=='かい' else dictionary(x)):
                self.assertFalse(R.native_bound_relative_nominal_parts(source))
        for word in ('た','たぶん','が'):
            with self.subTest(missing_word=word),patch.object(M,'dictionary_inflections',side_effect=lambda x:() if x==word else dictionary(x)):
                self.assertFalse(R.native_bound_relative_nominal_parts(source))

    def test_final_particle_relative_needs_own_meaning_and_closed_outer(self):
        import kana_spelling as K,semantic_roles as S
        source='先生がいつもくわしくかいたぶんしょう'
        for function in ('subject_candidate_evidence','candidate_evidence'):
            with patch.object(S,function,return_value=None):self.assertFalse(R.native_bound_relative_nominal_parts(source))
        faces=R.native_nominal_phrase_faces
        with patch.object(R,'native_nominal_phrase_faces',side_effect=lambda x:('文章','未知') if x=='ぶんしょう' else faces(x)):
            self.assertFalse(R.native_bound_relative_nominal_parts(source))
        for bad in ('先生は来るかい','先生が書いたのかい',source.replace('先生','機械'),
                    source.replace('ぶんしょう','ぷねら'),source.replace('かいた','かい'),
                    source.replace('かいた','かいて'),source.replace('かいた','かい\tた')):
            with self.subTest(source=bad):self.assertFalse(R.native_bound_relative_nominal_parts(bad))
        for tail in ('をぷねらします','を確認して','を確認しますです'):
            full=source+tail;parts=M.tokenize(full)
            self.assertEqual(K._relative_source_parts(full,parts),(parts,()))

    def test_final_particle_relative_body_and_common_gate(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        source='先生がいつもくわしくかいたぶんしょうを確認します';seen=[];check=C._check_replacement
        def observed(line,replacement,*args,**kwargs):
            r=check(line,replacement,*args,**kwargs);seen.append((tuple(replacement[:3]),r[0] is not None));return r
        def analyze(text):
            a=initial();return app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        try:
            with patch.object(C,'_check_replacement',side_effect=observed):r=analyze(source)
            self.assertEqual(r['corrected'],'先生がいつもくわしく書いた文章を確認します')
            self.assertEqual(r['analysis_status'],'complete');self.assertFalse(r['odd_spans'])
            self.assertEqual(r['original_spans'],[(10,12),(13,18)])
            self.assertTrue(any(rep[2]=='書い' and accepted for rep,accepted in seen))
            self.assertTrue(any(rep[2]=='文章' and accepted for rep,accepted in seen))
            with patch.object(C,'_check_replacement',return_value=(None,'test_forced_reject')):
                self.assertEqual(analyze(source)['corrected'],source)
            for text in (source.replace('確認','ぷねら'),source.replace('確認します','確認して'),
                         '入力は「'+source+'」です。',source+'という文字列です。'):
                self.assertEqual(analyze(text)['corrected'],text)
        finally:set_active(None)

    def test_partial_outer_proof_is_separate_from_original_normality(self):
        import kana_spelling as K
        source='先生がいつもくわしくかいたないようをぷねらします'
        self.assertIn((0,18),R.native_context_ranges(source))
        for change in ((10,12,'書い'),(13,17,'内容')):
            self.assertTrue(K._partial_relative_nominal_preserved(source,*change))
            self.assertFalse(K._relative_outer_spelling_proved(source,*change))
        self.assertIn((0,18),R.native_context_ranges(source))
        self.assertTrue(K._relative_outer_spelling_proved('未知をぷねらします',3,6,'保存'))
        self.assertTrue(K._relative_outer_spelling_proved(source,18,21,'保存'))
        good=source.replace('ぷねらします','保存します')
        for change in ((10,12,'書い'),(13,17,'内容')):
            self.assertTrue(K._relative_outer_spelling_proved(good,*change))
        for tail in ('確認して','保存し','保存をします'):
            bad=source[:18]+tail
            self.assertFalse(K._relative_outer_spelling_proved(bad,10,12,'書い'))

    def test_partial_outer_proof_requires_same_candidate_case_and_predicate(self):
        import kana_spelling as K,semantic_roles as S
        source='先生がいつもくわしくかいたないようを保存します'
        proof=R.native_object_predicate_proof;meaning=S.candidate_nominal_spelling_evidence
        for change in ((10,12,'書い'),(13,17,'内容')):
            a,b,face=change;candidate=source[:a]+face+source[b:];case=18+len(face)-(b-a)
            seen=[]
            def observe(text,pos,nouns,*args,**kwargs):
                seen.append((text,pos,nouns));return proof(text,pos,nouns,*args,**kwargs)
            with patch.object(R,'native_object_predicate_proof',side_effect=observe):
                self.assertTrue(K._relative_outer_spelling_proved(source,*change))
            self.assertIn((candidate,case,('内容',)),seen)
            with patch.object(R,'native_object_predicate_proof',side_effect=lambda text,*args,**kwargs:
                    False if text==candidate else proof(text,*args,**kwargs)):
                self.assertFalse(K._relative_outer_spelling_proved(source,*change))
        with patch.object(K,'_argument_relative_nominal_scope',return_value=()):
            self.assertFalse(K._relative_outer_spelling_proved(source,10,12,'書い'))
        with patch.object(K,'_argument_relative_nominal_scope',return_value=(12,17,('内容',))):
            self.assertFalse(K._relative_outer_spelling_proved(source,10,12,'書い'))
        for result in (None,dict(predicate='別語',case='を',shared_roles=('information',)),
                       dict(predicate='保存',case='が',shared_roles=('information',)),
                       dict(predicate='保存',case='を',shared_roles=())):
            with patch.object(S,'candidate_nominal_spelling_evidence',return_value=result):
                self.assertFalse(K._relative_outer_spelling_proved(source,10,12,'書い'))

    def test_partial_outer_proof_binds_candidate_tail_coordinates(self):
        import kana_spelling as K
        from types import SimpleNamespace as T
        source='先生がいつもくわしくかいたないようを保存します'
        candidate=source[:13]+'内容'+source[17:];tokenize=M.tokenize
        for key,value in (('start',14),('end',18),('surface','が'),('reading','が'),
                          ('has_reading',False),('pos','名詞'),('pos_sub','別分類'),
                          ('base_form','が'),('infl_form','基本形')):
            changed=[T(**{k:getattr(t,k) for k in t.__slots__}) for t in tokenize(candidate)]
            setattr(next(t for t in changed if t.start==15),key,value)
            with self.subTest(key=key),patch.object(M,'tokenize',side_effect=lambda text:changed if text==candidate else tokenize(text)):
                self.assertFalse(K._relative_outer_spelling_proved(source,13,17,'内容'))

    def test_partial_outer_proof_body_and_shared_gate(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        bad='先生がいつもくわしくかいたないようをぷねらします。'
        unfinished='先生がやさしくゆっくりよんだないようを確認して'
        good='先生がいつもくわしくかいたないようを保存します。'
        seen=[];check=C._check_replacement
        def observe(line,replacement,*args,**kwargs):
            result=check(line,replacement,*args,**kwargs)
            seen.append((line,tuple(replacement[:3]),result[0] is not None));return result
        def analyze(text):
            a=initial();return app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        try:
            for source in (bad,unfinished):
                with patch.object(C,'_check_replacement',new=observe):r=analyze(source)
                self.assertEqual(r['corrected'],source);self.assertEqual(r['analysis_status'],'complete')
            self.assertTrue(any(rep==(10,12,'書い') and ok for line,rep,ok in seen))
            r=analyze(good);self.assertEqual(r['corrected'],'先生がいつもくわしく書いた内容を保存します。')
            self.assertFalse(r['odd_spans']);self.assertEqual(r['analysis_status'],'complete')
            with patch.object(C,'_check_replacement',return_value=(None,'test_forced_reject')):
                r=analyze(good);self.assertEqual(r['corrected'],good)
            for text in ('入力は「'+good+'」です。',good.rstrip('。')+'という文字列です。'):
                r=analyze(text);self.assertEqual(r['corrected'],text);self.assertFalse(r['odd_spans'])
        finally:set_active(None)

    def test_manner_sequence_whole_original_inflections(self):
        for text,edges in (('やさしくゆっくりよんだ',(4,8)),('いつもくわしくかいた',(3,7))):
            with self.subTest(text=text):self.assertEqual(R.native_adverbial_reading_cuts(text),edges)
        for text,edge in (('やさしいゆっくりよんだ',8),('いつもくわしくっかいた',8),
                          ('いつもくわしければかいた',9),('やさしく\tゆっくりよんだ',9),
                          ('いつもぷねらかいた',6),('やさしく読んでゆっくりかいた',11)):
            with self.subTest(text=text):self.assertNotIn(edge,R.native_adverbial_reading_cuts(text))

    def test_manner_sequence_original_and_suffix_identity(self):
        from types import SimpleNamespace as T
        text='いつもくわしくかいた';tokenize=M.tokenize;dictionary=M.dictionary_inflections
        cuts=R.native_adverbial_reading_cuts.__wrapped__
        for attribute,value in (('reading','ぷねら'),('has_reading',False),('surface','別語'),
                                ('pos','名詞'),('pos_sub','別分類'),('base_form','別語'),
                                ('infl_form','基本形'),('start',4),('end',6)):
            changed=[T(**{k:getattr(t,k) for k in t.__slots__}) for t in tokenize(text)]
            setattr(changed[1],attribute,value)
            with self.subTest(attribute=attribute),patch.object(M,'tokenize',side_effect=lambda x:changed if x==text else tokenize(x)):
                self.assertNotIn(7,cuts(text))
        with patch.object(M,'dictionary_inflections',side_effect=lambda x:() if x=='くわしく' else dictionary(x)):
            self.assertNotIn(7,cuts(text))
        with patch.object(R,'native_adjective_adverbial_prefix',return_value=False):self.assertNotIn(7,cuts(text))
        suffix=text[3:]
        for attribute,value in (('reading','別読み'),('pos','名詞'),('base_form','別語'),('start',1),('end',3)):
            changed=[T(**{k:getattr(t,k) for k in t.__slots__}) for t in tokenize(suffix)]
            setattr(changed[0],attribute,value)
            with self.subTest(suffix_attribute=attribute),patch.object(M,'tokenize',side_effect=lambda x:changed if x==suffix else tokenize(x)):
                self.assertNotIn(7,cuts(text))

    def test_manner_sequence_requires_whole_source_and_candidate_meaning(self):
        import kana_spelling as K,semantic_roles as S
        source='先生がやさしくゆっくりよんだないようを確認します'
        self.assertEqual(K._subject_verb_relative_boundaries(source),(11,13,14,18))
        for bad in (source.replace('先生','機械'),source.replace('ないよう','ぷねら'),
                    source.replace('確認','ぷねら'),source.replace('します','して'),
                    source.replace('します','しますです'),source.replace('ゆっくり','\tゆっくり')):
            with self.subTest(text=bad):self.assertFalse(K._subject_verb_relative_boundaries(bad))
        for helper in ('subject_candidate_evidence','candidate_evidence'):
            with self.subTest(helper=helper),patch.object(S,helper,return_value=None):
                self.assertFalse(K._subject_verb_relative_boundaries(source))

    def test_manner_sequence_body_and_common_gate(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        rows=(('先生がやさしくゆっくりよんだないようを確認します。','先生がやさしくゆっくり読んだ内容を確認します。',[(11,13),(14,18)]),
              ('先生がいつもくわしくかいたないようを保存します。','先生がいつもくわしく書いた内容を保存します。',[(10,12),(13,17)]))
        def analyze(text):
            a=initial();return app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        seen=[];check=C._check_replacement
        def observe(line,replacement,*args,**kwargs):
            result=check(line,replacement,*args,**kwargs);seen.append((tuple(replacement[:3]),result[0] is not None));return result
        try:
            for source,expected,spans in rows:
                with self.subTest(source=source),patch.object(C,'_check_replacement',new=observe):
                    r=analyze(source);self.assertEqual(r['corrected'],expected);self.assertFalse(r['odd_spans'])
                    self.assertEqual(r['analysis_status'],'complete');self.assertEqual(r['original_spans'],spans)
            for face in ('読ん','書い'):self.assertTrue(any(rep[2]==face and ok for rep,ok in seen))
            source=rows[0][0]
            with patch.object(C,'_check_replacement',return_value=(None,'test_forced_reject')):
                r=analyze(source);self.assertEqual(r['corrected'],source);self.assertEqual(r['analysis_status'],'complete')
            for text in ('入力は「'+source+'」です。',source.rstrip('。')+'という文字列です。'):
                r=analyze(text);self.assertEqual(r['corrected'],text);self.assertFalse(r['odd_spans'])
        finally:set_active(None)

    def test_adverb_sequence_whole_words_and_original_edges(self):
        for text,edges in (('とてもゆっくりかく',(3,7)),('いつもよくよんだ',(3,5))):
            with self.subTest(text=text):
                self.assertEqual(R.native_adverbial_reading_cuts(text),edges)
                parts=M.tokenize(text);adverbs=[t for t in parts if t.pos=='副詞']
                self.assertEqual([t.end for t in adverbs],list(edges))
                self.assertTrue(all(text[t.start:t.end]==t.surface==t.reading for t in adverbs))
        for text,edge in (('とてもぷねらかく',6),('とても書いてよくかく',8),
                          ('とても\tゆっくりかく',8),('とても ゆっくりかく',8)):
            with self.subTest(text=text):self.assertNotIn(edge,R.native_adverbial_reading_cuts(text))

    def test_adverb_sequence_each_original_dictionary_identity(self):
        from types import SimpleNamespace as T
        # Inspect the function body under each mock, not a previously cached result.
        cuts=R.native_adverbial_reading_cuts.__wrapped__
        text='とてもゆっくりかく';tokenize=M.tokenize;dictionary=M.dictionary_inflections
        for start in (0,3):
            for attribute,value in (('reading','ぷねら'),('has_reading',False),('surface','別語'),
                                    ('pos','名詞'),('pos_sub','別分類'),('base_form','別語'),
                                    ('infl_form','別形'),('start',start+1),('end',start)):
                changed=[T(**{k:getattr(t,k) for k in t.__slots__}) for t in tokenize(text)]
                setattr(next(t for t in changed if t.start==start),attribute,value)
                with self.subTest(start=start,attribute=attribute),patch.object(M,'tokenize',side_effect=lambda x:changed if x==text else tokenize(x)):
                    self.assertNotIn(7,cuts(text))
        for word in ('とても','ゆっくり'):
            with self.subTest(word=word),patch.object(M,'dictionary_inflections',side_effect=lambda x:() if x==word else dictionary(x)):
                self.assertNotIn(7,cuts(text))
        faces=R._native_adverbial_faces
        with patch.object(R,'_native_adverbial_faces',side_effect=lambda x:() if x=='ゆっくり' else faces(x)):
            self.assertNotIn(7,cuts(text))

    def test_adverb_sequence_boundary_still_requires_whole_frame(self):
        import kana_spelling as K,semantic_roles as S
        text='先生がとてもゆっくりかくないようを確認します'
        self.assertEqual(K._subject_verb_relative_boundaries(text),(10,12,12,16))
        for bad in (text.replace('先生','機械'),text.replace('ないよう','ぷねら'),
                    text.replace('確認','ぷねら'),text.replace('します','して'),
                    text.replace('します','しますです'),text.replace('ゆっくり','\tゆっくり')):
            with self.subTest(text=bad):self.assertFalse(K._subject_verb_relative_boundaries(bad))
        head='先生がとてもゆっくりかくないよう'
        for helper in ('subject_candidate_evidence','candidate_evidence'):
            with self.subTest(helper=helper),patch.object(S,helper,return_value=None):
                self.assertFalse(R.native_dictionary_relative_nominal_parts(head))

    def test_adverb_sequence_body_uses_candidate_own_common_gate(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        rows=(('先生がとてもゆっくりかくないようを確認します。','先生がとてもゆっくり書く内容を確認します。',[(10,12),(12,16)]),
              ('先生がいつもよくよんだほうほうを保存します。','先生がいつもよく読んだ方法を保存します。',[(8,10),(11,15)]))
        def analyze(text):
            a=initial();return app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        seen=[];check=C._check_replacement
        def observe(line,replacement,*args,**kwargs):
            result=check(line,replacement,*args,**kwargs);seen.append((tuple(replacement[:3]),result[0] is not None));return result
        try:
            for source,expected,spans in rows:
                with self.subTest(source=source),patch.object(C,'_check_replacement',new=observe):
                    r=analyze(source);self.assertEqual(r['corrected'],expected)
                    self.assertFalse(r['odd_spans']);self.assertEqual(r['analysis_status'],'complete');self.assertEqual(r['original_spans'],spans)
            self.assertTrue(any(rep[2]=='書く' and ok for rep,ok in seen))
            self.assertTrue(any(rep[2]=='読ん' and ok for rep,ok in seen))
            source=rows[0][0]
            with patch.object(C,'_check_replacement',return_value=(None,'test_forced_reject')):
                r=analyze(source);self.assertEqual(r['corrected'],source);self.assertEqual(r['analysis_status'],'complete')
            for text in ('入力は「'+source+'」です。',source.rstrip('。')+'という文字列です。'):
                r=analyze(text);self.assertEqual(r['corrected'],text);self.assertFalse(r['odd_spans'])
        finally:set_active(None)

    def test_unknown_dictionary_subject_preserves_both_source_analyses(self):
        source='せんせいがすぐかくぶんしょうを記録します';head=source[:14]
        parts=M.tokenize(source);owner=next(t for t in parts if not t.has_reading)
        self.assertEqual((owner.start,owner.end,owner.surface),(6,15,'ぐかくぶんしょうを'))
        self.assertFalse(any(t.start==7 and t.end==9 for t in parts))
        self.assertFalse(R.native_dictionary_relative_nominal_parts(head))
        inner=R.native_dictionary_relative_nominal_parts(head,subject_face='先生')
        self.assertEqual(inner[:4],(9,('文章',),7,9))
        self.assertEqual([(t.surface,t.start,t.end) for t in inner[4]],[('せんせい',0,4),('が',4,5),('すぐ',5,7),('かく',7,9)])
        self.assertTrue(R._native_unknown_relative_prefix(source,parts,9,inner[4]))
        proof=R.native_dictionary_subject_spelling(source,0,4,'先生')
        self.assertEqual(proof['noun_span'],(9,14));self.assertEqual(proof['verb_span'],(7,9))
        self.assertEqual(proof['outer_case'],(14,15));self.assertEqual(proof['outer_predicate'],'記録')
        self.assertFalse(R.native_dictionary_relative_nominal_parts(head))
        self.assertFalse(R.native_object_predicate_proof(source,15,('文章',)))
        for face in ('先制','宣誓','専制','せんせい'):
            self.assertIsNone(R.native_dictionary_subject_spelling(source,0,4,face))

    def test_unknown_dictionary_subject_requires_original_owner_and_prefix(self):
        from types import SimpleNamespace as T
        source='せんせいがすぐかくぶんしょうを記録します';original=M.tokenize(source);prefix=M.tokenize(source[:9]);dictionary=M.dictionary_inflections
        clone=lambda values:[T(**{k:getattr(t,k) for k in t.__slots__}) for t in values]
        for position,attribute,value in ((6,'has_reading',True),(6,'surface','未知'),(6,'base_form','別'),(6,'reading','別'),(6,'start',7),(6,'end',14),(5,'pos','名詞'),(5,'pos_sub','一般'),(5,'reading','別'),(5,'base_form','別'),(5,'end',7),(4,'reading','別')):
            changed=clone(original);setattr(next(t for t in changed if t.start==position),attribute,value)
            with self.subTest(position=position,attribute=attribute):self.assertFalse(R._native_unknown_relative_prefix(source,changed,9,prefix))
        for position in (0,4,5,7):
            for attribute,value in (('has_reading',False),('reading','別'),('base_form','別'),('infl_form','別'),('pos','別'),('start',position+1),('end',position)):
                changed=clone(prefix);setattr(next(t for t in changed if t.start==position),attribute,value)
                with self.subTest(prefix=position,attribute=attribute):self.assertFalse(R._native_unknown_relative_prefix(source,original,9,changed))
        for target in ('す','すぐ','かく','が'):
            with self.subTest(target=target),patch.object(M,'dictionary_inflections',side_effect=lambda text:() if text==target else dictionary(text)):
                self.assertFalse(R._native_unknown_relative_prefix(source,original,9,prefix))
        self.assertFalse(R._native_unknown_relative_prefix(source,original,8,prefix))
        self.assertFalse(R._native_unknown_relative_prefix(source,original,9,prefix[:-1]))

    def test_unknown_dictionary_subject_keeps_own_meaning_and_outer_case(self):
        import semantic_roles as S
        source='せんせいがすぐかくぶんしょうを記録します';dictionary=M.dictionary_inflections;faces=R.native_nominal_phrase_faces
        for target in ('を','先生'):
            with self.subTest(target=target),patch.object(M,'dictionary_inflections',side_effect=lambda text:() if text==target else dictionary(text)):
                self.assertIsNone(R.native_dictionary_subject_spelling(source,0,4,'先生'))
        for name in ('subject_candidate_evidence','candidate_evidence','candidate_nominal_spelling_evidence'):
            with self.subTest(name=name),patch.object(S,name,return_value=None):
                self.assertIsNone(R.native_dictionary_subject_spelling(source,0,4,'先生'))
        with patch.object(R,'native_nominal_phrase_faces',side_effect=lambda text:('文章','未知') if text=='ぶんしょう' else faces(text)):
            self.assertIsNone(R.native_dictionary_subject_spelling(source,0,4,'先生'))
        with patch.object(R,'native_nominal_case_boundary',return_value=None):
            self.assertIsNone(R.native_dictionary_subject_spelling(source,0,4,'先生'))
        with patch.object(R,'native_object_predicate_proof',return_value=False):
            self.assertIsNone(R.native_dictionary_subject_spelling(source,0,4,'先生'))
        for text in (source.replace('記録','ぷねら'),source.replace('記録します','記録して'),source+'です',source.replace('ぶんしょう','ぷねら'),source.replace('すぐ','すぐ\t')):
            with self.subTest(text=text):self.assertIsNone(R.native_dictionary_subject_spelling(text,0,4,'先生'))

    def test_unknown_dictionary_subject_body_uses_common_gate(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        source='せんせいがすぐかくぶんしょうを記録します';seen=[];check=C._check_replacement
        def observe(line,replacement,*args,**kwargs):
            result=check(line,replacement,*args,**kwargs);seen.append((line,tuple(replacement[:3]),result[0] is not None));return result
        def analyze(text):
            a=initial();return app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        try:
            with patch.object(C,'_check_replacement',side_effect=observe):r=analyze(source)
            self.assertEqual(r['corrected'],'先生がすぐ書く文章を記録します')
            self.assertFalse(r['odd_spans']);self.assertEqual(r['analysis_status'],'complete')
            self.assertEqual(r['original_spans'],[(0,4),(7,9),(9,14)])
            self.assertTrue(any(line==source and rep==(0,4,'先生') and accepted for line,rep,accepted in seen))
            self.assertTrue(any(rep[2]=='書く' and accepted for line,rep,accepted in seen))
            with patch.object(C,'_check_replacement',return_value=(None,'test_forced_reject')):
                r=analyze(source);self.assertEqual(r['corrected'],source);self.assertEqual(r['analysis_status'],'complete')
            for text in (source.replace('記録','ぷねら'),'入力は「'+source+'」です。',source+'という文字列です。'):
                r=analyze(text);self.assertEqual(r['corrected'],text);self.assertEqual(r['analysis_status'],'complete')
        finally:set_active(None)

    def test_finite_dictionary_subject_retains_only_each_own_source_frame(self):
        import semantic_roles as S
        source='せんせいがゆっくりかくぶんしょうを共有します';changes=[(0,4,'先生')]
        check=R.native_dictionary_relative_retention
        self.assertTrue(check(source,changes,9,11,'書く'))
        self.assertTrue(check(source,changes,11,16,'文章'))
        self.assertTrue(check(source,changes+[(9,11,'書く')],11,16,'文章'))
        self.assertTrue(check(source,changes+[(11,16,'文章')],9,11,'書く'))
        self.assertFalse(R.native_dictionary_relative_nominal_parts(source[:16]))
        self.assertFalse(R.native_object_predicate_proof(source,17,('文章',)))
        for prior,a,b,face in (([],9,11,'書く'),([(0,4,'先制')],9,11,'書く'),
                (changes,9,11,'描く'),(changes,9,13,'各分'),(changes,11,16,'未知'),
                (changes,11,15,'文章'),(changes+[(5,9,'すぐ')],11,16,'文章'),
                (changes+[(9,11,'描く')],11,16,'文章'),(changes+[(11,16,'文章')],11,16,'文章')):
            with self.subTest(prior=prior,span=(a,b),face=face):self.assertFalse(check(source,prior,a,b,face))
        for name in ('subject_candidate_evidence','candidate_evidence','candidate_nominal_spelling_evidence'):
            with self.subTest(name=name),patch.object(S,name,return_value=None):
                self.assertFalse(check(source,changes,9,11,'書く'))
        with patch.object(R,'native_object_predicate_proof',return_value=False):
            self.assertFalse(check(source,changes,11,16,'文章'))
        # The subject can be valid while a different pending spelling's
        # outer frame is not; the second check must use the whole candidate.
        real=R.native_object_predicate_proof;seen=[]
        def outer(text,*args,**kwargs):
            seen.append(text)
            return False if '書く' in text else real(text,*args,**kwargs)
        with patch.object(R,'native_object_predicate_proof',side_effect=outer):
            self.assertFalse(check(source,changes,9,11,'書く'))
        self.assertIn('先生がゆっくり書くぶんしょうを共有します',seen)

    def test_finite_dictionary_subject_keeps_actual_verb_and_conditional_meaning(self):
        for source,verb,noun,case,face in (
                ('せんせいがすぐかくほうほうを確認します',(7,9),(9,13),(13,14),'方法'),
                ('せんせいがゆっくりかくぶんしょうを共有します',(9,11),(11,16),(16,17),'文章')):
            with self.subTest(source=source):
                owner=next(t for t in M.tokenize(source) if (t.start,t.end)==verb)
                self.assertEqual((owner.pos,owner.pos_sub,owner.infl_form),('動詞','自立','基本形'))
                head=source[:case[0]]
                self.assertFalse(R.native_dictionary_relative_nominal_parts(head))
                parts=R.native_dictionary_relative_nominal_parts(head,subject_face='先生')
                self.assertEqual(parts[:4],(noun[0],(face,),verb[0],verb[1]))
                copied=parts[4][-1]
                self.assertEqual(tuple(getattr(copied,k) for k in copied.__slots__),tuple(getattr(owner,k) for k in owner.__slots__))
                proof=R.native_dictionary_subject_spelling(source,0,4,'先生')
                self.assertEqual(proof['verb_span'],verb);self.assertEqual(proof['noun_span'],noun)
                self.assertEqual(proof['outer_case'],case);self.assertEqual(proof['noun_faces'],(face,))
                self.assertFalse(R.native_dictionary_relative_nominal_parts(head))
                for other in ('先制','宣誓','専制','せんせい'):
                    self.assertIsNone(R.native_dictionary_subject_spelling(source,0,4,other))

    def test_finite_dictionary_subject_requires_actual_verb_identity(self):
        from types import SimpleNamespace as T
        source='せんせいがすぐかくほうほう';tokenize=M.tokenize;dictionary=M.dictionary_inflections
        for attribute,value in (('reading','ぷねら'),('has_reading',False),('base_form','別語'),('infl_form','連用形'),('pos','名詞'),('pos_sub','非自立'),('start',8),('end',8)):
            changed=[T(**{key:getattr(t,key) for key in t.__slots__}) for t in tokenize(source)]
            setattr(next(t for t in changed if t.start==7),attribute,value)
            with self.subTest(attribute=attribute),patch.object(M,'tokenize',side_effect=lambda text:changed if text==source else tokenize(text)):
                self.assertFalse(R.native_dictionary_relative_nominal_parts(source,subject_face='先生'))
        for target in ('かく','が','先生'):
            with self.subTest(target=target),patch.object(M,'dictionary_inflections',side_effect=lambda text:() if text==target else dictionary(text)):
                self.assertFalse(R.native_dictionary_relative_nominal_parts(source,subject_face='先生'))
        for text in ('せんせいがすぐかくない','せんせいがすぐ\tかくほうほう','せんせいをすぐかくほうほう'):
            with self.subTest(text=text):self.assertFalse(R.native_dictionary_relative_nominal_parts(text,subject_face='先生'))

    def test_finite_dictionary_subject_requires_own_meaning_and_outer_frame(self):
        import semantic_roles as S
        source='せんせいがすぐかくほうほうを確認します';sub=S.subject_candidate_evidence;faces=R.native_nominal_phrase_faces
        for name in ('subject_candidate_evidence','candidate_evidence','candidate_nominal_spelling_evidence'):
            with self.subTest(name=name),patch.object(S,name,return_value=None):
                self.assertIsNone(R.native_dictionary_subject_spelling(source,0,4,'先生'))
        with patch.object(S,'subject_candidate_evidence',side_effect=lambda n,f,t:sub(n,f,t) if f=='書く' else None),patch.object(S,'candidate_evidence',side_effect=lambda n,f,t:dict(predicate=f,case='を',shared_roles=['test']) if f=='描く' else None):
            self.assertIsNone(R.native_dictionary_subject_spelling(source,0,4,'先生'))
        with patch.object(R,'native_nominal_phrase_faces',side_effect=lambda text:('方法','未知') if text=='ほうほう' else faces(text)):
            self.assertIsNone(R.native_dictionary_subject_spelling(source,0,4,'先生'))
        with patch.object(R,'native_object_predicate_proof',return_value=False):
            self.assertIsNone(R.native_dictionary_subject_spelling(source,0,4,'先生'))
        for text in (source.replace('確認','ぷねら'),source.replace('確認します','確認して'),source+'です',source.replace('ほうほう','ぷねら'),source.replace('すぐ','すぐ\t')):
            with self.subTest(text=text):self.assertIsNone(R.native_dictionary_subject_spelling(text,0,4,'先生'))

    def test_finite_dictionary_subject_body_uses_common_gate(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        seen=[];check=C._check_replacement
        def observe(line,replacement,*args,**kwargs):
            result=check(line,replacement,*args,**kwargs);seen.append((line,tuple(replacement[:3]),result[0] is not None));return result
        def analyze(text):
            a=initial();return app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        try:
            for source,expected,spans in (
                    ('せんせいがすぐかくほうほうを確認します','先生がすぐ書く方法を確認します',[(0,4),(7,9),(9,13)]),
                    ('せんせいがゆっくりかくぶんしょうを共有します','先生がゆっくり書く文章を共有します',[(0,4),(9,11),(11,16)])):
                with self.subTest(source=source),patch.object(C,'_check_replacement',side_effect=observe):r=analyze(source)
                self.assertEqual(r['corrected'],expected);self.assertFalse(r['odd_spans'])
                self.assertEqual(r['analysis_status'],'complete');self.assertEqual(r['original_spans'],spans)
                self.assertTrue(any(line==source and rep==(0,4,'先生') and accepted for line,rep,accepted in seen))
            source='せんせいがすぐかくほうほうを確認します'
            with patch.object(C,'_check_replacement',return_value=(None,'test_forced_reject')):
                r=analyze(source);self.assertEqual(r['corrected'],source);self.assertEqual(r['analysis_status'],'complete')
            for text in (source.replace('確認','ぷねら'),'入力は「'+source+'」です。',source+'という文字列です。'):
                r=analyze(text);self.assertEqual(r['corrected'],text);self.assertEqual(r['analysis_status'],'complete')
        finally:set_active(None)

    def test_conditional_dictionary_subject_keeps_original_and_candidate_separate(self):
        import kana_spelling as K
        source='せんせいがよくかくないようを保存します'
        self.assertFalse(R.native_dictionary_relative_nominal_parts(source[:13]))
        proof=R.native_dictionary_subject_spelling(source,0,4,'先生')
        self.assertEqual(proof['source'],'conditional_original_relative_subject')
        self.assertEqual(proof['source_span'],(0,4));self.assertEqual(proof['verb_span'],(7,9))
        self.assertEqual(proof['noun_span'],(9,13));self.assertEqual(proof['noun_faces'],('内容',))
        self.assertEqual(proof['outer_case'],(13,14));self.assertEqual(proof['outer_predicate'],'保存')
        self.assertFalse(R.native_dictionary_relative_nominal_parts(source[:13]))
        self.assertFalse(R.native_object_predicate_proof(source,14,('内容',)))
        self.assertTrue(K._relative_subject_spelling_evidence(source,0,4,'先生'))
        for face in ('先制','宣誓','専制','せんせい','先生たち','教師'):
            with self.subTest(face=face):self.assertIsNone(R.native_dictionary_subject_spelling(source,0,4,face))
        nouns=set();units=K._lexical_units(source,M.tokenize(source),nouns)
        self.assertIn((0,4),units)
        with patch.object(R,'native_dictionary_subject_spelling',return_value=None):
            units=K._lexical_units(source,M.tokenize(source),set())
            self.assertTrue(any(a<4<b for a,b in units))

    def test_conditional_dictionary_subject_requires_original_tokens_and_dictionary(self):
        from types import SimpleNamespace as T
        source='せんせいがよくかくないようを保存します';tokenize=M.tokenize;dictionary=M.dictionary_inflections
        for position in (0,4,7,13):
            for attribute,value in (('reading','ぷねら'),('has_reading',False),('base_form','別語'),('infl_form','別形'),('pos','別品詞'),('start',position+1),('end',position)):
                changed=[T(**{key:getattr(t,key) for key in t.__slots__}) for t in tokenize(source)]
                setattr(next(t for t in changed if t.start==position),attribute,value)
                with self.subTest(position=position,attribute=attribute),patch.object(M,'tokenize',side_effect=lambda text:changed if text==source else tokenize(text)):
                    self.assertIsNone(R.native_dictionary_subject_spelling(source,0,4,'先生'))
        for target in ('せんせい','先生','が','かく','を'):
            with self.subTest(target=target),patch.object(M,'dictionary_inflections',side_effect=lambda text:() if text==target else dictionary(text)):
                self.assertIsNone(R.native_dictionary_subject_spelling(source,0,4,'先生'))
        for start,end in ((1,4),(0,3),(0,5)):
            self.assertIsNone(R.native_dictionary_subject_spelling(source,start,end,'先生'))

    def test_conditional_dictionary_subject_requires_same_lexeme_and_whole_outer_frame(self):
        import semantic_roles as S
        source='せんせいがよくかくないようを保存します';sub=S.subject_candidate_evidence;obj=S.candidate_evidence
        for name in ('subject_candidate_evidence','candidate_evidence','candidate_nominal_spelling_evidence'):
            with self.subTest(name=name),patch.object(S,name,return_value=None):
                self.assertIsNone(R.native_dictionary_subject_spelling(source,0,4,'先生'))
        with patch.object(S,'subject_candidate_evidence',side_effect=lambda n,f,t:sub(n,f,t) if f=='書く' else None),patch.object(S,'candidate_evidence',side_effect=lambda n,f,t:dict(predicate=f,case='を',shared_roles=['test']) if f=='描く' else None):
            self.assertIsNone(R.native_dictionary_subject_spelling(source,0,4,'先生'))
        faces=R.native_nominal_phrase_faces
        with patch.object(R,'native_nominal_phrase_faces',side_effect=lambda text:('内容','未知') if text=='ないよう' else faces(text)):
            self.assertIsNone(R.native_dictionary_subject_spelling(source,0,4,'先生'))
        with patch.object(R,'native_object_predicate_proof',return_value=False):
            self.assertIsNone(R.native_dictionary_subject_spelling(source,0,4,'先生'))
        for text in (source.replace('保存','ぷねら'),source.replace('保存します','保存して'),source+'です',source.replace('ないよう','ぷねら'),source.replace('よく','よく\t'),source[:9]+'ない',source.replace('が','を',1)):
            with self.subTest(text=text):self.assertIsNone(R.native_dictionary_subject_spelling(text,0,4,'先生'))

    def test_conditional_dictionary_subject_body_uses_common_gate(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        source='せんせいがよくかくないようを保存します';seen=[];check=C._check_replacement
        def observe(line,replacement,*args,**kwargs):
            result=check(line,replacement,*args,**kwargs);seen.append((line,tuple(replacement[:3]),result[0] is not None));return result
        def analyze(text):
            a=initial();return app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        try:
            with patch.object(C,'_check_replacement',side_effect=observe):r=analyze(source)
            self.assertEqual(r['corrected'],'先生がよく書く内容を保存します')
            self.assertFalse(r['odd_spans']);self.assertEqual(r['analysis_status'],'complete')
            self.assertEqual(r['original_spans'],[(0,4),(7,9),(9,13)])
            self.assertTrue(any(line==source and rep==(0,4,'先生') and accepted for line,rep,accepted in seen))
            self.assertTrue(any(rep[2]=='書く' and accepted for line,rep,accepted in seen))
            with patch.object(C,'_check_replacement',return_value=(None,'test_forced_reject')):
                r=analyze(source);self.assertEqual(r['corrected'],source);self.assertEqual(r['analysis_status'],'complete')
            for text in (source.replace('保存','ぷねら'),'入力は「'+source+'」です。',source+'という文字列です。'):
                r=analyze(text);self.assertEqual(r['corrected'],text);self.assertEqual(r['analysis_status'],'complete')
        finally:set_active(None)

    def test_dictionary_relative_source_identity(self):
        import kana_spelling as K
        source='先生がよくかくないよう'
        original=M.tokenize(source);proof=R.native_dictionary_relative_nominal_parts(source)
        self.assertEqual(proof[:4],(7,('内容',),5,7))
        before=next(t for t in original if t.start==5);after=proof[4][-1]
        self.assertEqual(before.pos,'副詞');self.assertEqual(after.pos,'動詞')
        self.assertEqual((after.surface,after.reading,after.start,after.end),(before.surface,before.reading,before.start,before.end))
        self.assertEqual(after.infl_form,'基本形');self.assertEqual(after.base_form,'かく')
        self.assertEqual(''.join(t.surface for t in proof[4]),source[:7])
        self.assertTrue(R._native_subject_kana_verb_nominal(source[:7],('かく',('が',)),('内容',),source_parts=proof[4],candidate_face='書く'))
        self.assertFalse(R._native_subject_kana_verb_nominal(source[:7],('かく',('が',)),('内容',),source_parts=proof[4],candidate_face='描く'))
        self.assertFalse(R._native_subject_kana_verb_nominal(source[:7],('かく',('が',)),('内容',),source_parts=proof[4],candidate_face='書いた'))
        full=source+'を共有します';parts,edges=K._relative_source_parts(full,M.tokenize(full))
        self.assertEqual(edges,(5,7,7,11));self.assertEqual(''.join(t.surface for t in parts),full)
        self.assertTrue(all(full[t.start:t.end]==t.surface for t in parts))

    def test_dictionary_relative_source_requires_original_dictionary(self):
        from types import SimpleNamespace as T
        source='先生がよくかくないよう';tokenize=M.tokenize;dictionary=M.dictionary_inflections
        for position in (2,5):
            for attribute,value in (('reading','ぷねら'),('has_reading',False),('base_form','別語'),('infl_form','別形'),('pos','別品詞'),('pos_sub','別分類'),('start',position+1),('end',position)):
                changed=[T(**{k:getattr(t,k) for k in t.__slots__}) for t in tokenize(source)]
                setattr(next(t for t in changed if t.start==position),attribute,value)
                with self.subTest(position=position,attribute=attribute),patch.object(M,'tokenize',side_effect=lambda text:changed if text==source else tokenize(text)):
                    self.assertFalse(R.native_dictionary_relative_nominal_parts(source))
        for kind in ('副詞,','動詞,自立,'):
            with self.subTest(kind=kind),patch.object(M,'dictionary_inflections',side_effect=lambda text:tuple(row for row in dictionary(text) or () if not row[0].startswith(kind)) if text=='かく' else dictionary(text)):
                self.assertFalse(R.native_dictionary_relative_nominal_parts(source))
        with patch.object(R,'native_adverbial_reading_cuts',return_value=()):self.assertFalse(R.native_dictionary_relative_nominal_parts(source))

    def test_dictionary_relative_source_own_meaning_and_scope(self):
        import semantic_roles as S,kana_spelling as K
        source='先生がよくかくないよう'
        for name in ('subject_candidate_evidence','candidate_evidence'):
            with patch.object(S,name,return_value=None):self.assertFalse(R.native_dictionary_relative_nominal_parts(source))
        sf=S.subject_candidate_evidence;ob=S.candidate_evidence
        with patch.object(S,'subject_candidate_evidence',side_effect=lambda n,f,t:sf(n,f,t) if f=='書く' else None),patch.object(S,'candidate_evidence',side_effect=lambda n,f,t:dict(predicate=f,case='を',shared_roles=['test']) if f=='描く' else None):
            self.assertFalse(R.native_dictionary_relative_nominal_parts(source))
        faces=R.native_nominal_phrase_faces
        with patch.object(R,'native_nominal_phrase_faces',side_effect=lambda text:('内容','未知') if text=='ないよう' else faces(text)):
            self.assertFalse(R.native_dictionary_relative_nominal_parts(source))
        for text in ('先生がよくかくない','先生がよくかくぷねら','ぷねらがよくかくないよう','機械がよくかくないよう','先生がよく\tかくないよう','先生がよくかいてないよう'):
            with self.subTest(text=text):self.assertFalse(R.native_dictionary_relative_nominal_parts(text))
        for tail in ('を共有して','をぷねらします','を共有しますです'):
            full=source+tail;parts=M.tokenize(full)
            self.assertEqual(K._relative_source_parts(full,parts),(parts,()))

    def test_dictionary_relative_source_function_gate(self):
        import kana_spelling as K,ime_spelling as I
        text='先生がよくかくないようを共有します'
        self.assertTrue(K._dictionary_relative_spelling_evidence(text,5,7,'書く'))
        self.assertFalse(I._reinterprets_function_attachment(text,5,7,'書く'))
        for face in ('描く','書いた','角'):
            with self.subTest(face=face):
                self.assertFalse(K._dictionary_relative_spelling_evidence(text,5,7,face))
                self.assertTrue(I._reinterprets_function_attachment(text,5,7,face))
        for source in (text.replace('共有','ぷねら'),text.replace('します','して'),text.replace('先生','機械'),text.replace('ないよう','ぷねら')):
            with self.subTest(source=source):
                self.assertFalse(K._dictionary_relative_spelling_evidence(source,5,7,'書く'))
                self.assertTrue(I._reinterprets_function_attachment(source,5,7,'書く'))
        with patch.object(K,'_dictionary_relative_spelling_evidence',return_value=False):
            self.assertTrue(I._reinterprets_function_attachment(text,5,7,'書く'))

    def test_dictionary_relative_source_body_and_common_gate(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        source='先生がよくかくないようを共有します';seen=[];check=C._check_replacement
        def observed(line,replacement,*args,**kwargs):
            result=check(line,replacement,*args,**kwargs);seen.append((tuple(replacement[:3]),result[0] is not None));return result
        def analyze(text):
            a=initial();return app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        try:
            with patch.object(C,'_check_replacement',side_effect=observed):r=analyze(source)
            self.assertEqual(r['corrected'],'先生がよく書く内容を共有します')
            self.assertFalse(r['odd_spans']);self.assertEqual(r['analysis_status'],'complete')
            self.assertEqual(r['original_spans'],[(5,7),(7,11)])
            self.assertTrue(any(rep[2]=='書く' and allowed for rep,allowed in seen))
            self.assertTrue(any(rep[2]=='内容' and allowed for rep,allowed in seen))
            with patch.object(C,'_check_replacement',return_value=(None,'test_forced_reject')):self.assertEqual(analyze(source)['corrected'],source)
            bad=source.replace('共有','ぷねら');self.assertEqual(analyze(bad)['corrected'],bad)
            for text in ('入力は「'+source+'」です。',source+'という文字列です。'):
                r=analyze(text);self.assertEqual(r['corrected'],text);self.assertFalse(r['odd_spans'])
        finally:set_active(None)

    def test_progressive_bound_original_whole_reading(self):
        import kana_spelling as K
        source='先生がゆっくりかいていたぶんしょう'
        proof=R.native_progressive_bound_relative_nominal_parts(source)
        self.assertEqual(proof[:4],(12,('文章',),7,9))
        original=next(t for t in M.tokenize(source) if t.start==7)
        segment=[t for t in proof[4] if 7<=t.start and t.end<=11]
        self.assertEqual(original.pos,'名詞');self.assertEqual(len(segment),3)
        self.assertEqual(''.join(t.surface for t in segment),original.surface)
        self.assertEqual(''.join(t.reading for t in segment),original.reading)
        self.assertEqual([t.pos for t in segment],['動詞','助詞','動詞'])
        self.assertFalse(R.native_bound_relative_nominal_parts(source))
        self.assertNotIn(12,R.native_relative_nominal_cuts(source,M.tokenize(source)))
        full=source+'を共有します';parts,edges=K._relative_source_parts(full,M.tokenize(full))
        self.assertEqual(edges,(7,9,12,17));self.assertEqual(''.join(t.surface for t in parts),full)
        self.assertTrue(all(full[t.start:t.end]==t.surface for t in parts))

    def test_progressive_bound_requires_each_original_word(self):
        from types import SimpleNamespace as T
        source='先生がゆっくりかいていたぶんしょう';tokenize=M.tokenize
        for target,position in ((source,7),(source,11),(source[:12],7),(source[:12],9),(source[:12],10),(source[:12],11)):
            for attribute,value in (('reading','ぷねら'),('has_reading',False),('pos','記号'),('pos_sub','別分類'),('base_form','別語'),('infl_form','別形'),('start',position+1),('end',position)):
                changed=[T(**{k:getattr(t,k) for k in t.__slots__}) for t in tokenize(target)]
                setattr(next(t for t in changed if t.start==position),attribute,value)
                with self.subTest(target=target,position=position,attribute=attribute),patch.object(M,'tokenize',side_effect=lambda text:changed if text==target else tokenize(text)):
                    self.assertFalse(R.native_progressive_bound_relative_nominal_parts(source))
        dictionary=M.dictionary_inflections
        for word in ('かいてい','かい','て','い','た','たぶん'):
            with self.subTest(word=word),patch.object(M,'dictionary_inflections',side_effect=lambda text:() if text==word else dictionary(text)):
                self.assertFalse(R.native_progressive_bound_relative_nominal_parts(source))

    def test_progressive_bound_keeps_same_meaning_and_outer_scope(self):
        import kana_spelling as K,semantic_roles as S,contextual_repair as Q
        source='先生がゆっくりかいていたぶんしょう'
        for function in ('subject_candidate_evidence','candidate_evidence'):
            with patch.object(S,function,return_value=None):self.assertFalse(R.native_progressive_bound_relative_nominal_parts(source))
        with patch.object(Q,'_native_te_auxiliary_tail',return_value=False):self.assertFalse(R.native_progressive_bound_relative_nominal_parts(source))
        with patch.object(S,'native_te_auxiliary_forms',return_value=()):self.assertFalse(R.native_progressive_bound_relative_nominal_parts(source))
        faces=R.native_nominal_phrase_faces
        with patch.object(R,'native_nominal_phrase_faces',side_effect=lambda text:('文章','未知') if text=='ぶんしょう' else faces(text)):
            self.assertFalse(R.native_progressive_bound_relative_nominal_parts(source))
        for text in ('海底の資料','先生がゆっくりかいていたぷねら','機械がゆっくりかいていたぶんしょう','ぷねらがゆっくりかいていたぶんしょう','先生がゆっくりかいてい\tたぶんしょう'):
            with self.subTest(text=text):self.assertFalse(R.native_progressive_bound_relative_nominal_parts(text))
        for tail in ('を共有して','をぷねらします','を共有しますです'):
            full=source+tail;parts=M.tokenize(full)
            self.assertEqual(K._relative_source_parts(full,parts),(parts,()))

    def test_progressive_bound_body_and_common_gate(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        source='先生がゆっくりかいていたぶんしょうを共有します';seen=[];check=C._check_replacement
        def observed(line,replacement,*args,**kwargs):
            r=check(line,replacement,*args,**kwargs);seen.append((tuple(replacement[:3]),r[0] is not None));return r
        def analyze(text):
            a=initial();return app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        try:
            with patch.object(C,'_check_replacement',side_effect=observed):r=analyze(source)
            self.assertEqual(r['corrected'],'先生がゆっくり書いていた文章を共有します')
            self.assertFalse(r['odd_spans']);self.assertEqual(r['analysis_status'],'complete')
            self.assertEqual(r['original_spans'],[(7,9),(12,17)])
            self.assertTrue(any(rep[2]=='書い' and allowed for rep,allowed in seen))
            self.assertTrue(any(rep[2]=='文章' and allowed for rep,allowed in seen))
            with patch.object(C,'_check_replacement',return_value=(None,'test_forced_reject')):self.assertEqual(analyze(source)['corrected'],source)
            bad=source.replace('共有','ぷねら');self.assertEqual(analyze(bad)['corrected'],bad)
            for text in ('入力は「'+source+'」です。',source+'という文字列です。'):
                r=analyze(text);self.assertEqual(r['corrected'],text);self.assertFalse(r['odd_spans'])
        finally:set_active(None)

    def test_written_bound_owns_its_candidate_frame(self):
        import kana_spelling as K
        source='先生がゆっくり書かなかったぶんしょう'
        proof=R.native_bound_relative_nominal_parts(source)
        self.assertEqual(proof[:4],(13,('文章',),7,9))
        self.assertEqual(R.native_written_action_nominal_parts(source),proof[:2])
        verb=next(t for t in proof[4] if t.start==7)
        self.assertEqual((verb.surface,verb.reading,verb.base_form,verb.infl_form),('書か','かか','書く','未然形'))
        relative=R.native_written_relative_action(source[:13])
        self.assertFalse(R._native_subject_kana_verb_nominal(source[:13],relative,('文章',)))
        self.assertTrue(R._native_subject_kana_verb_nominal(source[:13],relative,('文章',),allow_written=True))
        original=source.replace('書か','かか')+'を記録します'
        self.assertTrue(K._partial_relative_nominal_preserved(original,7,9,'書か'))
        self.assertTrue(K._relative_outer_spelling_proved(original,7,9,'書か'))
        for tail in ('をぷねらします','を記録して','を記録しますです'):
            self.assertFalse(K._relative_outer_spelling_proved(source.replace('書か','かか')+tail,7,9,'書か'))

    def test_written_bound_requires_each_own_dictionary_token(self):
        from types import SimpleNamespace as T
        source='先生がゆっくり書かなかったぶんしょう';tokenize=M.tokenize
        for target,position in ((source,7),(source,9),(source,12),(source[:13],7),(source[:13],9),(source[:13],12)):
            for attribute,value in (('reading','ぷねら'),('has_reading',False),('pos','記号'),('pos_sub','別分類'),('base_form','別語'),('infl_form','別形'),('start',position+1),('end',position)):
                changed=[T(**{k:getattr(t,k) for k in t.__slots__}) for t in tokenize(target)]
                setattr(next(t for t in changed if t.start==position),attribute,value)
                with self.subTest(target=target,position=position,attribute=attribute),patch.object(M,'tokenize',side_effect=lambda text:changed if text==target else tokenize(text)):
                    self.assertFalse(R.native_bound_relative_nominal_parts(source))
        dictionary=M.dictionary_inflections
        for word in ('書か','なかっ','たぶん','た'):
            with self.subTest(word=word),patch.object(M,'dictionary_inflections',side_effect=lambda text:() if text==word else dictionary(text)):
                self.assertFalse(R.native_bound_relative_nominal_parts(source))

    def test_written_bound_keeps_one_lexeme_and_all_nouns(self):
        import semantic_roles as S
        source='先生がゆっくり書かなかったぶんしょう'
        for function in ('subject_candidate_evidence','candidate_evidence'):
            with self.subTest(function=function),patch.object(S,function,return_value=None):
                self.assertFalse(R.native_bound_relative_nominal_parts(source))
        faces=R.native_nominal_phrase_faces
        with patch.object(R,'native_nominal_phrase_faces',side_effect=lambda text:('文章','未知') if text=='ぶんしょう' else faces(text)):
            self.assertFalse(R.native_bound_relative_nominal_parts(source))
        forms=S._native_lexeme_forms
        with patch.object(S,'_native_lexeme_forms',side_effect=lambda lemma,form,reading:('描か',) if lemma=='書く' else forms(lemma,form,reading)):
            self.assertFalse(R.native_bound_relative_nominal_parts(source))
        lexemes=S.native_verb_lexemes
        with patch.object(S,'native_verb_lexemes',side_effect=lambda face,form,reading:{'書く','描く'} if face=='書か' else lexemes(face,form,reading)):
            self.assertFalse(R.native_bound_relative_nominal_parts(source))
        for text in ('機械がゆっくり書かなかったぶんしょう','ぷねらがゆっくり書かなかったぶんしょう','先生がゆっくり書かなかったぷねら','先生がゆっくり書くなかったぶんしょう','先生がゆっくり書かなかっぶんしょう','先生がゆっくり書かなかった\tぶんしょう'):
            with self.subTest(text=text):self.assertFalse(R.native_bound_relative_nominal_parts(text))

    def test_bound_auxiliary_chain_keeps_original_tokens(self):
        import kana_spelling as K
        source='先生がゆっくりかかなかったぶんしょう'
        original=M.tokenize(source);proof=R.native_bound_relative_nominal_parts(source)
        self.assertEqual(proof[:4],(13,('文章',),7,9))
        fields=('surface','reading','pos','pos_sub','base_form','infl_form','start','end')
        old=next(t for t in original if t.start==9)
        new=next(t for t in proof[4] if t.start==9)
        self.assertEqual(tuple(getattr(old,k) for k in fields),tuple(getattr(new,k) for k in fields))
        self.assertEqual(new.surface,'なかっ');self.assertEqual(new.pos,'助動詞')
        self.assertNotIn(13,R.native_relative_nominal_cuts(source,original))
        full=source+'を記録します';parts,edges=K._relative_source_parts(full,M.tokenize(full))
        self.assertEqual(edges,(7,9,13,18))
        self.assertEqual(''.join(t.surface for t in parts),full)
        self.assertTrue(all(full[t.start:t.end]==t.surface for t in parts))
        self.assertEqual(next(t for t in parts if t.start==12).surface,'た')

    def test_bound_auxiliary_chain_requires_each_source_entry(self):
        from types import SimpleNamespace as T
        source='先生がゆっくりかかなかったぶんしょう';tokenize=M.tokenize
        for target in (source,source[:13]):
            original=tokenize(target)
            for attribute,value in (('has_reading',False),('reading','ぷねら'),('pos','名詞'),
                    ('base_form','別語'),('infl_form','基本形'),('start',10),('end',11)):
                changed=[T(**{k:getattr(t,k) for k in t.__slots__}) for t in original]
                setattr(next(t for t in changed if t.start==9),attribute,value)
                with self.subTest(target=target,attribute=attribute),patch.object(M,'tokenize',side_effect=lambda text:
                        changed if text==target else tokenize(text)):
                    self.assertFalse(R.native_bound_relative_nominal_parts(source))
        dictionary=M.dictionary_inflections
        for word in ('なかっ','かか','た','たぶん'):
            with self.subTest(word=word),patch.object(M,'dictionary_inflections',side_effect=lambda text:
                    () if text==word else dictionary(text)):
                self.assertFalse(R.native_bound_relative_nominal_parts(source))

    def test_bound_auxiliary_chain_keeps_own_meaning_and_finite_scope(self):
        import kana_spelling as K,semantic_roles as S
        source='先生がゆっくりかかなかったぶんしょう'
        for function in ('subject_candidate_evidence','candidate_evidence'):
            with patch.object(S,function,return_value=None):self.assertFalse(R.native_bound_relative_nominal_parts(source))
        faces=R.native_nominal_phrase_faces
        with patch.object(R,'native_nominal_phrase_faces',side_effect=lambda text:
                ('文章','未知') if text=='ぶんしょう' else faces(text)):
            self.assertFalse(R.native_bound_relative_nominal_parts(source))
        for bad in ('先生がゆっくりかかますたぶんしょう','ぷねらがゆっくりかかなかったぶんしょう',
                    '機械がゆっくりかかなかったぶんしょう','先生がゆっくりかかなかったぷねら',
                    '先生がゆっくりかか\tなかったぶんしょう','先生がゆっくりかいていたぶんしょう'):
            with self.subTest(source=bad):self.assertFalse(R.native_bound_relative_nominal_parts(bad))
        for tail in ('を記録して','をぷねらします','を記録しますです'):
            full=source+tail;parts=M.tokenize(full)
            self.assertEqual(K._relative_source_parts(full,parts),(parts,()))

    def test_bound_auxiliary_chain_body_preserves_common_gate(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        source='先生がゆっくりかかなかったぶんしょうを記録します';seen=[];check=C._check_replacement
        def observed(line,replacement,*args,**kwargs):
            r=check(line,replacement,*args,**kwargs);seen.append((tuple(replacement[:3]),r[0] is not None));return r
        def analyze(text):
            a=initial();return app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        try:
            with patch.object(C,'_check_replacement',side_effect=observed):r=analyze(source)
            self.assertEqual(r['corrected'],'先生がゆっくり書かなかった文章を記録します')
            self.assertFalse(r['odd_spans']);self.assertEqual(r['analysis_status'],'complete')
            self.assertEqual(r['original_spans'],[(7,9),(13,18)])
            self.assertTrue(any(rep[2]=='書か' and allowed for rep,allowed in seen))
            self.assertTrue(any(rep[2]=='文章' and allowed for rep,allowed in seen))
            with patch.object(C,'_check_replacement',return_value=(None,'test_forced_reject')):
                self.assertEqual(analyze(source)['corrected'],source)
            bad=source.replace('記録','ぷねら')
            self.assertEqual(analyze(bad)['corrected'],bad)
            for text in ('入力は「'+source+'」です。',source+'という文字列です。'):
                r=analyze(text);self.assertEqual(r['corrected'],text);self.assertFalse(r['odd_spans'])
        finally:set_active(None)

    def tearDown(self):
        # Meaning/dictionary mocks must not leave cached negative grammar
        # evidence for a later initial-state example in this test class.
        R.native_written_relative_action.cache_clear()
        R.native_object_predicate_proof.cache_clear()

    def test_bound_relative_source_keeps_completed_original_inflection(self):
        import kana_spelling as K
        source='先生がゆっくりかいたぶんしょう'
        original=M.tokenize(source)
        proof=R.native_bound_relative_nominal_parts(source)
        self.assertEqual(proof[:4],(10,('文章',),7,9))
        self.assertNotIn(10,R.native_relative_nominal_cuts(source,original))
        full=source+'を保存します'
        before=M.tokenize(full)
        rebuilt,edges=K._relative_source_parts(full,before)
        self.assertEqual(edges,(7,9,10,15))
        self.assertEqual(''.join(t.surface for t in rebuilt),full)
        self.assertTrue(all(full[t.start:t.end]==t.surface for t in rebuilt))
        self.assertEqual(next(t for t in before if t.start==7).infl_form,'連用形')
        self.assertEqual(next(t for t in rebuilt if t.start==7).infl_form,'連用タ接続')
        self.assertEqual(next(t for t in rebuilt if t.start==9).pos,'助動詞')
        self.assertEqual(R.native_written_action_nominal_parts(source),(10,('文章',)))
        nouns=set();units=K._lexical_units(full,rebuilt,nouns)
        self.assertIn((10,15),nouns);self.assertNotIn((9,12),units)
        with patch.object(R,'native_bound_relative_nominal_parts',return_value=()):
            self.assertEqual(K._relative_source_parts(full,before),(before,()))

    def test_bound_relative_source_requires_original_owner_and_dictionary(self):
        from types import SimpleNamespace as T
        source='先生がゆっくりかいたぶんしょう';tokenize=M.tokenize
        original=tokenize(source)
        for start,attribute,value in ((9,'has_reading',False),(9,'reading','ぷねら'),(9,'start',8),
                (9,'base_form','別語'),(9,'pos','名詞'),(7,'reading','よみ'),
                (7,'end',10),(7,'infl_form','未然形'),(7,'base_form','別語')):
            changed=[T(**{key:getattr(t,key) for key in t.__slots__}) for t in original]
            setattr(next(t for t in changed if t.start==start),attribute,value)
            with self.subTest(start=start,attribute=attribute),patch.object(M,'tokenize',side_effect=lambda text:
                    changed if text==source else tokenize(text)):
                self.assertFalse(R.native_bound_relative_nominal_parts(source))
        dictionary=M.dictionary_inflections
        for word in ('たぶん','かい','た','が'):
            with self.subTest(word=word),patch.object(M,'dictionary_inflections',side_effect=lambda text:
                    () if text==word else dictionary(text)):
                self.assertFalse(R.native_bound_relative_nominal_parts(source))

        prefix=source[:10];native_prefix=tokenize(prefix)
        for start,attribute,value in ((7,'reading','よみ'),(7,'start',6),(7,'base_form','別語'),
                (9,'pos','名詞'),(9,'reading','だ'),(9,'end',11),(9,'infl_form','未然形')):
            changed=[T(**{key:getattr(t,key) for key in t.__slots__}) for t in native_prefix]
            setattr(next(t for t in changed if t.start==start),attribute,value)
            with self.subTest(prefix_attribute=attribute,start=start),patch.object(M,'tokenize',side_effect=lambda text:
                    changed if text==prefix else tokenize(text)):
                self.assertFalse(R.native_bound_relative_nominal_parts(source))

    def test_bound_relative_source_does_not_lend_other_meanings_or_open_tail(self):
        import kana_spelling as K,semantic_roles as S
        source='先生がゆっくりかいたぶんしょう'
        for function in ('subject_candidate_evidence','candidate_evidence'):
            with patch.object(S,function,return_value=None):
                self.assertFalse(R.native_bound_relative_nominal_parts(source))
        faces=R.native_nominal_phrase_faces
        with patch.object(R,'native_nominal_phrase_faces',side_effect=lambda text:
                ('文章','未知') if text=='ぶんしょう' else faces(text)):
            self.assertFalse(R.native_bound_relative_nominal_parts(source))
        for bad in ('先生がたぶん書いた文章','先生がゆっくりかいたぷねら',
                    'ぷねらがゆっくりかいたぶんしょう','機械がゆっくりかいたぶんしょう',
                    '先生がゆっくりかいてぶんしょう','先生がゆっくりかきますですぶんしょう',
                    '先生がゆっくり\tかいたぶんしょう'):
            with self.subTest(source=bad):self.assertFalse(R.native_bound_relative_nominal_parts(bad))
        for tail in ('を保存して','をぷねらします','を保存しますです','を保存し'):
            full=source+tail;parts=M.tokenize(full)
            self.assertEqual(K._relative_source_parts(full,parts),(parts,()))

    def test_bound_relative_source_body_still_checks_each_candidate(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        source='先生がゆっくりかいたぶんしょうを保存します';seen=[];check=C._check_replacement
        def observed(line,replacement,*args,**kwargs):
            r=check(line,replacement,*args,**kwargs);seen.append((tuple(replacement[:3]),r[0] is not None));return r
        def analyze(text):
            a=initial()
            return app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        try:
            with patch.object(C,'_check_replacement',side_effect=observed):r=analyze(source)
            self.assertEqual(r['corrected'],'先生がゆっくり書いた文章を保存します')
            self.assertEqual(r['analysis_status'],'complete');self.assertFalse(r['odd_spans'])
            self.assertEqual(r['original_spans'],[(7,9),(10,15)])
            self.assertTrue(any(rep[2]=='書い' and allowed for rep,allowed in seen))
            self.assertTrue(any(rep[2]=='文章' and allowed for rep,allowed in seen))
            with patch.object(C,'_check_replacement',return_value=(None,'test_forced_reject')):
                r=analyze(source);self.assertEqual(r['corrected'],source)
            bad='先生がゆっくりかいたぶんしょうをぷねらします'
            self.assertEqual(analyze(bad)['corrected'],bad)
            for text in ('入力は「'+source+'」です。',source+'という文字列です。'):
                r=analyze(text);self.assertEqual(r['corrected'],text);self.assertFalse(r['odd_spans'])
        finally:set_active(None)

    def test_partial_relative_retention_uses_candidate_whole_noun(self):
        import kana_spelling as K
        source='先生がすぐかいたぶんしょうをぷねらします'
        self.assertIn((0,14),R.native_context_ranges(source))
        self.assertTrue(K._partial_relative_nominal_preserved(source,5,7,'書い'))
        self.assertTrue(K._partial_relative_nominal_preserved(source,8,13,'文章'))
        self.assertFalse(K._partial_relative_nominal_preserved(source,5,7,'買い'))
        self.assertFalse(K._partial_relative_nominal_preserved(source,7,10,'多分'))
        self.assertFalse(K._partial_relative_nominal_preserved(source,8,13,'紋章'))
        self.assertIn((0,14),R.native_context_ranges(source))
        # An unproved original or an outside edit has no new veto.
        self.assertTrue(K._partial_relative_nominal_preserved('未知をぷねらします',3,6,'保存'))
        self.assertTrue(K._partial_relative_nominal_preserved(source,14,17,'保存'))

    def test_partial_relative_retention_keeps_same_proof_and_coordinates(self):
        import kana_spelling as K
        source='先生がすぐかいたぶんしょうをぷねらします'
        helper=R.native_written_action_nominal_parts
        for answer in ((),(7,('文章',)),(7,('方法',))):
            with patch.object(R,'native_written_action_nominal_parts',side_effect=lambda text,answer=answer:
                    answer if '書い' in text else helper(text)):
                self.assertFalse(K._partial_relative_nominal_preserved(source,5,7,'書い'))
        noun_faces=R._native_written_nominal_faces
        with patch.object(R,'_native_written_nominal_faces',side_effect=lambda text:
                ('文章','ぷねら') if text=='文章' else noun_faces(text)):
            self.assertFalse(K._partial_relative_nominal_preserved(source,8,13,'文章'))
        with patch.object(M,'native_spelling_only',return_value=False):
            self.assertFalse(K._partial_relative_nominal_preserved(source,8,13,'文章'))
        for boundary in (None,('文章',True)):
            with patch.object(R,'native_nominal_case_boundary',return_value=boundary):
                self.assertTrue(K._partial_relative_nominal_preserved(source,7,10,'多分'))

    def test_partial_relative_retention_does_not_replace_common_gate(self):
        import kana_spelling as K,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        source='先生がすぐかいたぶんしょうをぷねらします'
        calls=[];gate=C._check_replacement
        def observe(line,replacement,*args,**kwargs):
            result=gate(line,replacement,*args,**kwargs)
            calls.append((tuple(replacement[:3]),result[0] is not None));return result
        a=initial()
        try:
            with patch.object(C,'_check_replacement',side_effect=observe):
                self.assertIsNone(K.project(source,a.store,a.dict_index,a.decisions,partial=True))
            self.assertIn(((5,7,'買い'),True),calls)
            self.assertIn(((7,10,'多分'),True),calls)
        finally:set_active(None)

    def test_partial_relative_retention_body_and_valid_spelling(self):
        from tests_analysis_async import initial
        import app
        from last_choice import set_active
        import corrector as C
        bad='先生がすぐかいたぶんしょうをぷねらします。'
        good='先生がすぐかいたぶんしょうを確認します。'
        def analyze(text,a):
            return app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        try:
            a=initial();result=analyze(bad,a)
            self.assertEqual(result['corrected'],bad)
            self.assertEqual(result['analysis_status'],'complete');self.assertTrue(result['odd_spans'])
            a=initial();result=analyze(good,a)
            self.assertEqual(result['corrected'],'先生がすぐ書いた文章を確認します。')
            self.assertEqual(result['analysis_status'],'complete');self.assertFalse(result['odd_spans'])
            a=initial()
            with patch.object(C,'_check_replacement',return_value=(None,'forced_test_rejection')):
                result=analyze(good,a)
            self.assertEqual(result['corrected'],good)
            for source in ('入力は「'+bad+'」です。',bad.rstrip('。')+'という文字列です。'):
                a=initial();result=analyze(source,a)
                self.assertEqual(result['corrected'],source);self.assertFalse(result['odd_spans'])
        finally:set_active(None)

    def test_unknown_relative_seams_keep_entire_source_frame(self):
        import kana_spelling as K
        source='先生がすぐかいたぶんしょうを確認します'
        self.assertEqual(R.native_written_action_nominal_parts(source[:13]),(8,('文章',)))
        self.assertEqual(K._subject_verb_relative_boundaries(source),(5,7,8,13))
        self.assertEqual(R.native_written_relative_action(source,allow_finite=True),('確認',('を',)))
        self.assertTrue(R.native_object_predicate_proof(source,14,('文章',)))
        self.assertFalse(R.native_written_relative_action(source,allow_link=True))
        self.assertFalse(R.native_written_relative_action(source,allow_open_polite=True))
        nouns=set();units=K._lexical_units(source,M.tokenize(source),nouns)
        self.assertIn((8,13),nouns);self.assertIn((5,7),units)
        for bad in ('先生がすぐかいたぷねらを確認します','ぷねらがすぐかいたぶんしょうを確認します',
                    '機械がすぐかいたぶんしょうを確認します','先生がすぐかいてぶんしょうを確認します',
                    '先生がすぐかいたぶんしょうを確認して','先生がすぐかいたぶんしょうをぷねらします',
                    '先生がすぐ\tかいたぶんしょうを確認します'):
            with self.subTest(source=bad):self.assertFalse(K._subject_verb_relative_boundaries(bad))

        # Development164 proves this full source using independent
        # dictionary/meaning/outer-clause evidence. It is no longer an
        # unproved frame; the negative cases above retain their contract.
        self.assertEqual(K._subject_verb_relative_boundaries(
            '先生がよくかくないようを共有します'),(5,7,7,11))

    def test_unknown_relative_seams_do_not_split_known_words(self):
        import kana_spelling as K
        from types import SimpleNamespace as T
        source='先生がすぐかいたぶんしょう'
        original=M.tokenize(source)
        self.assertIn(8,R.native_relative_nominal_cuts(source,original))
        changed=[T(**{key:getattr(t,key) for key in t.__slots__}) for t in original]
        for t in changed:
            if not t.has_reading:t.has_reading=True
        self.assertNotIn(8,R.native_relative_nominal_cuts(source,changed))
        tokenize=M.tokenize
        with patch.object(M,'tokenize',side_effect=lambda text:changed if text==source else tokenize(text)):
            self.assertFalse(R.native_written_action_nominal_parts(source))
        full=source+'を確認します';dictionary=M.dictionary_inflections
        for face in ('を','が','かい'):
            with patch.object(M,'dictionary_inflections',side_effect=lambda text:() if text==face else dictionary(text)):
                self.assertFalse(K._subject_verb_relative_boundaries(full),face)
        with patch.object(R,'native_nominal_case_boundary',return_value=None):
            self.assertFalse(K._subject_verb_relative_boundaries(full))

    def test_unknown_relative_seams_require_each_own_meaning(self):
        import kana_spelling as K,semantic_roles as S
        source='先生がすぐかいたぶんしょうを確認します'
        for name in ('subject_candidate_evidence','candidate_evidence','candidate_nominal_spelling_evidence'):
            with patch.object(S,name,return_value=None):
                self.assertFalse(K._subject_verb_relative_boundaries(source),name)
        nouns=R.native_nominal_phrase_faces
        with patch.object(R,'native_nominal_phrase_faces',side_effect=lambda text:('文章','未知') if text=='ぶんしょう' else nouns(text)):
            self.assertFalse(K._subject_verb_relative_boundaries(source))
        with patch.object(R,'native_adverbial_reading_cuts',return_value=()):
            self.assertFalse(K._subject_verb_relative_boundaries(source))

    def test_unknown_relative_outer_frame_keeps_source_and_predicate(self):
        import semantic_roles as S
        from types import SimpleNamespace as T
        source='先生がすぐかいたぶんしょうを確認します';parts=M.tokenize(source)
        self.assertEqual(R.native_unknown_relative_object_action(source,parts),('確認',('を',)))
        for field,value in (('has_reading',True),('end',13)):
            changed=[T(**{key:getattr(t,key) for key in t.__slots__}) for t in parts]
            owner=next(t for t in changed if not t.has_reading)
            setattr(owner,field,value)
            self.assertFalse(R.native_unknown_relative_object_action(source,changed))
        tail=next(t for t in parts if t.start==14)
        for field,value in (('has_reading',False),('start',15)):
            changed=[T(**{key:getattr(t,key) for key in t.__slots__}) for t in parts]
            target=next(t for t in changed if t.start==tail.start);setattr(target,field,value)
            self.assertFalse(R.native_unknown_relative_object_action(source,changed))
        for key,value in (('predicate','別の述語'),('case','に'),('shared_roles',[])):
            proof=dict(predicate='確認',case='を',shared_roles=['text']);proof[key]=value
            with patch.object(S,'candidate_nominal_spelling_evidence',return_value=proof):
                self.assertFalse(R.native_unknown_relative_object_action(source,parts))
        for suffix in ('確認して','確認し','確認しますです','確認','確認します\t保存します'):
            text=source[:14]+suffix
            self.assertFalse(R.native_unknown_relative_object_action(text,M.tokenize(text)),suffix)

    def test_unknown_relative_seams_complete_through_common_gate(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        source='先生がすぐかいたぶんしょうを確認します';a=initial();seen=[];check=C._check_replacement
        def observed(line,replacement,*args,**kwargs):
            r=check(line,replacement,*args,**kwargs);seen.append((replacement,r[0] is not None));return r
        def result(text):return app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        try:
            with patch.object(C,'_check_replacement',side_effect=observed):r=result(source)
            self.assertEqual(r['corrected'],'先生がすぐ書いた文章を確認します')
            self.assertFalse(r['odd_spans']);self.assertEqual(r['analysis_status'],'complete')
            self.assertEqual(r['original_spans'],[(5,7),(8,13)])
            self.assertTrue(any(rep[2]=='文章' and allowed for rep,allowed in seen))
            self.assertTrue(any(rep[2]=='書い' and allowed for rep,allowed in seen))
            with patch.object(C,'_check_replacement',return_value=(None,'test_reject')):
                r=result(source);self.assertEqual(r['corrected'],source);self.assertEqual(r['analysis_status'],'complete')
            for text in ('入力は「'+source+'」です。',source+'という文字列です。'):
                r=result(text);self.assertEqual(r['corrected'],text);self.assertFalse(r['odd_spans'])
        finally:set_active(None)

    def test_subject_verb_boundaries_keep_same_source_clause(self):
        import kana_spelling as K
        for suffix,end in (('ないよう',15),('内容',13)):
            for outer in ('','を確認します'):
                source='先生がよくかかなかった'+suffix+outer
                with self.subTest(source=source):
                    self.assertEqual(K._subject_verb_relative_boundaries(source),(5,7,11,end))
                    nouns=set();units=K._lexical_units(source,M.tokenize(source),nouns)
                    self.assertIn((5,7),units);self.assertIn((11,end),nouns)
                    self.assertFalse(any(a<5<b or a<7<b for a,b in units))
        for source in ('先生がよくかかなかったぷねら','ぷねらがよくかかなかったないよう',
                       '先生がよくかきますですないよう','先生がよくかいてないよう',
                       '先生がよくかかなかったないようを確認して',
                       '先生がよくかかなかったないようをぷねらします',
                       '先生がよく\tかかなかったないよう','先生がよくかかなかったない'):
            self.assertFalse(K._subject_verb_relative_boundaries(source),source)

    def test_subject_verb_boundaries_require_original_inflection_and_adverb(self):
        import kana_spelling as K
        import reading_segments as R
        from types import SimpleNamespace
        source='先生がよくかかなかったないようを確認します';tokenize=M.tokenize;dictionary=M.dictionary_inflections
        for attr,value in (('reading','かき'),('infl_form','基本形'),('base_form','読む'),
                           ('start',4),('end',8),('has_reading',False)):
            def altered(text):
                return [SimpleNamespace(**dict({key:getattr(t,key) for key in ('surface','pos','pos_sub','reading','base_form','infl_form','start','end','has_reading')},**{attr:value})) if t.start==5 and t.surface=='かか' else t for t in tokenize(text)]
            with self.subTest(attr=attr),patch.object(M,'tokenize',side_effect=altered):
                self.assertFalse(K._subject_verb_relative_boundaries(source))
        with patch.object(R,'native_adverbial_reading_cuts',return_value=()):
            self.assertFalse(K._subject_verb_relative_boundaries(source))
        for face in ('かか','が','を'):
            with patch.object(M,'dictionary_inflections',side_effect=lambda value:() if value==face else dictionary(value)):
                self.assertFalse(K._subject_verb_relative_boundaries(source),face)

    def test_subject_verb_boundaries_require_both_own_meanings(self):
        import kana_spelling as K
        import reading_segments as R,semantic_roles as S
        source='先生がよくかかなかったないようを確認します'
        self.assertTrue(K._subject_verb_relative_boundaries(source))
        for function in ('subject_candidate_evidence','candidate_evidence'):
            with patch.object(S,function,return_value=None):self.assertFalse(K._subject_verb_relative_boundaries(source))
        nouns=R.native_nominal_phrase_faces
        with patch.object(R,'native_nominal_phrase_faces',side_effect=lambda text:('内容','未知') if text=='ないよう' else nouns(text)):
            self.assertFalse(K._subject_verb_relative_boundaries(source))
        with patch.object(R,'_native_subject_kana_verb_nominal',return_value=False):
            units=K._lexical_units(source,M.tokenize(source))
            self.assertIn((3,6),units)
        # Source boundaries supply no spelling candidate or sense ranking.
        self.assertIsInstance(K._subject_verb_relative_boundaries(source)[0],int)

    def test_subject_verb_boundaries_complete_through_common_gate(self):
        import app,corrector as C,semantic_roles as S
        from tests_analysis_async import initial
        from last_choice import set_active
        a=initial();source='先生がよくかかなかったないようを確認します';seen=[];check=C._check_replacement
        def observed(line,replacement,*args,**kwargs):
            ret=check(line,replacement,*args,**kwargs);seen.append((replacement,ret[0] is not None));return ret
        def result(text):return app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        try:
            with patch.object(C,'_check_replacement',side_effect=observed):r=result(source)
            self.assertEqual(r['corrected'],'先生がよく書かなかった内容を確認します')
            self.assertFalse(r['odd_spans']);self.assertEqual(r['analysis_status'],'complete')
            self.assertEqual(r['original_spans'],[(5,7),(11,15)])
            self.assertTrue(any(replacement[2]=='書か' and allowed for replacement,allowed in seen))
            with patch.object(C,'_check_replacement',return_value=(None,'test_reject')):
                r=result(source);self.assertEqual(r['corrected'],source);self.assertEqual(r['analysis_status'],'complete')
            for text in ('入力は「'+source+'」です。',source+'という文字列です。'):
                r=result(text);self.assertEqual(r['corrected'],text);self.assertFalse(r['odd_spans'])
        finally:set_active(None)

    def test_subject_adverb_reuses_native_argument_boundary(self):
        import semantic_roles as S
        def tok(text):return [(t.surface,t.pos+':'+t.pos_sub,t.reading,t.start,t.end,t.has_reading,t.infl_form) for t in M.tokenize(text)]
        for prefix in ('先生が','先生がすぐ','先生がよく','先生がゆっくり','先生が静かに','先生が大きく'):
            source=prefix+'よんだ内容';start=len(prefix)
            with self.subTest(prefix=prefix):
                self.assertEqual(S.subject_before(source,start,tok),'先生')
                parts,edge=S._argument_prefix(source,start,tok)
                self.assertEqual(edge,3);self.assertEqual(parts[-1][0],'が')
        for prefix in ('先生がすぐ ','先生がすぐ\t','先生が読んで','先生が\n','先生がぷねら'):
            self.assertFalse(S.subject_before(prefix+'よんだ内容',len(prefix),tok),prefix)

    def test_subject_adverb_keeps_dictionary_reading_and_original_coordinates(self):
        import semantic_roles as S
        source='先生がすぐよんだ内容';start=5
        rows=[(t.surface,t.pos+':'+t.pos_sub,t.reading,t.start,t.end,t.has_reading,t.infl_form) for t in M.tokenize(source)]
        dictionary=M.dictionary_inflections
        self.assertEqual(S.subject_before(source,start,lambda _:rows),'先生')
        for index,value in ((2,'よく'),(3,2),(4,4),(5,False)):
            changed=list(rows);t=list(changed[2]);t[index]=value;changed[2]=tuple(t)
            with self.subTest(index=index):self.assertFalse(S.subject_before(source,start,lambda _:changed))
        with patch.object(M,'dictionary_inflections',side_effect=lambda face:() if face=='すぐ' else dictionary(face)):
            self.assertFalse(S.subject_before(source,start,lambda _:rows))
        for noun_kind in ('名詞:固有名詞:人名','名詞:接尾:一般'):
            changed=list(rows);t=list(changed[0]);t[1]=noun_kind;changed[0]=tuple(t)
            self.assertFalse(S.subject_before(source,start,lambda _:changed))
        # The last part of an unclassified compound is not its whole subject.
        compounded=[('元','名詞:一般','もと',0,1,True,''),('先生','名詞:一般','せんせい',1,3,True,''),('が','助詞:格助詞','が',3,4,True,''),('すぐ','副詞:一般','すぐ',4,6,True,'')]
        self.assertFalse(S.subject_before('元先生がすぐよんだ',6,lambda _:compounded))

    def test_subject_adverb_boundary_does_not_supply_predicate_meaning(self):
        import semantic_roles as S
        def tok(text):return [(t.surface,t.pos+':'+t.pos_sub,t.reading,t.start,t.end,t.has_reading,t.infl_form) for t in M.tokenize(text)]
        self.assertEqual(S.subject_before('先生がすぐよんだ',5,tok),'先生')
        proof=S.subject_candidate_evidence('先生','読ん','だ')
        self.assertEqual(proof['predicate'],'読ん');self.assertIn('person',proof['shared_roles'])
        self.assertEqual(S.subject_before('機械がすぐよんだ',5,tok),'機械')
        self.assertFalse(S.subject_candidate_evidence('機械','読ん','だ')['shared_roles'])
        self.assertFalse(S.subject_candidate_evidence('先生','検討','した')['shared_roles'])
        self.assertIsNone(S.subject_candidate_evidence('先生','読ま','れた'))

    def test_subject_adverb_spelling_uses_own_meaning_and_common_gate(self):
        import app,corrector as C,semantic_roles as S
        from tests_analysis_async import initial
        from last_choice import set_active
        a=initial();source='先生がすぐよんだないようを確認します';seen=[];check=C._check_replacement
        def observed(line,replacement,*args,**kwargs):
            ret=check(line,replacement,*args,**kwargs);seen.append((replacement,ret[0] is not None));return ret
        def result(text):return app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        try:
            with patch.object(C,'_check_replacement',side_effect=observed):r=result(source)
            self.assertEqual(r['corrected'],'先生がすぐ読んだ内容を確認します')
            self.assertFalse(r['odd_spans']);self.assertEqual(r['analysis_status'],'complete')
            self.assertEqual(r['original_spans'],[(5,7),(8,12)])
            self.assertTrue(any(replacement[2]=='読ん' and allowed for replacement,allowed in seen))
            with patch.object(C,'_check_replacement',return_value=(None,'test_reject')):
                r=result(source);self.assertEqual(r['corrected'],source);self.assertEqual(r['analysis_status'],'complete')
            with patch.object(S,'subject_candidate_evidence',return_value=None):
                r=result(source);self.assertNotIn('読ん',r['corrected'])
            for text in ('入力は「'+source+'」です。',source+'という文字列です。'):
                r=result(text);self.assertEqual(r['corrected'],text);self.assertFalse(r['odd_spans'])
        finally:set_active(None)

    def test_subject_kana_verb_nominal_keeps_source_case_and_same_lexeme(self):
        phrase='先生がよんだないよう'
        self.assertEqual(R.native_written_relative_action('先生がよんだ'),('よんだ',('が',)))
        self.assertEqual(R.native_written_action_nominal_parts(phrase),(6,('内容',)))
        self.assertEqual(R.native_written_relative_nominal_heads(phrase),('内容',))
        for source in ('先生が文章をよんだないよう','ぷねらがよんだないよう',
                '先生がよんでないよう','先生がよみますですないよう',
                '先生がよんだぷねら','先生がよんだない','先生が\tよんだないよう',
                '先生がよまないよう'):
            self.assertFalse(R.native_written_action_nominal_parts(source),source)
        import ime_spelling as I
        source=phrase+'を確認します'
        self.assertFalse(I._crosses_negative_attachment(source,6,10))
        with patch.object(R,'_native_subject_kana_verb_nominal',return_value=False):
            self.assertTrue(I._crosses_negative_attachment(source,6,10))

    def test_subject_kana_verb_nominal_requires_actual_tokens_and_dictionary(self):
        from types import SimpleNamespace
        head='先生がよんだ';relative=('よんだ',('が',));tokenize=M.tokenize;dictionary=M.dictionary_inflections
        proof=lambda:R._native_subject_kana_verb_nominal(head,relative,('内容',))
        self.assertTrue(proof());original=tokenize(head)
        for surface,fields in (('よん',(('reading','かい'),('pos_sub','非自立'),('base_form','書く'),
                ('infl_form','未然形'),('start',2),('end',6),('has_reading',False))),
                ('が',(('reading','を'),('pos_sub','接続助詞'),('base_form','を'),
                ('infl_form','基本形'),('start',1),('end',4),('has_reading',False)))):
            for field,value in fields:
                rows=[SimpleNamespace(**{key:getattr(t,key) for key in t.__slots__}) for t in original]
                token=next(t for t in rows if t.surface==surface);setattr(token,field,value)
                with self.subTest(surface=surface,field=field),patch.object(M,'tokenize',side_effect=lambda text:rows if text==head else tokenize(text)):
                    self.assertFalse(proof())
        for removed in ('よん','読ん','が'):
            with self.subTest(dictionary=removed),patch.object(M,'dictionary_inflections',side_effect=lambda word:() if word==removed else dictionary(word)):
                self.assertFalse(proof())
        with patch.object(M,'dictionary_inflections',side_effect=lambda word:tuple(dictionary(word) or ())+(('動詞,自立,*,*','連用タ接続','呼ぶ','よん'),) if word=='読ん' else dictionary(word)):
            self.assertFalse(proof())
        adjunct='先生がよくよんだ'
        self.assertTrue(R._native_subject_kana_verb_nominal(adjunct,relative,('内容',)))
        with patch.object(R,'native_adverbial_reading_cuts',return_value=()):
            self.assertFalse(R._native_subject_kana_verb_nominal(adjunct,relative,('内容',)))
        self.assertFalse(R._native_subject_kana_verb_nominal(head,('かいた',('が',)),('内容',)))
        self.assertFalse(R._native_subject_kana_verb_nominal(head,('よんだ',('が','を')),('内容',)))

    def test_subject_kana_verb_nominal_does_not_union_homophone_arguments(self):
        import semantic_roles as S
        head='先生がよんだ';relative=('よんだ',('が',));nominal=R.native_nominal_phrase_faces
        proof=lambda:R._native_subject_kana_verb_nominal(head,relative,('内容',))
        with patch.object(S,'subject_candidate_evidence',return_value=None):self.assertFalse(proof())
        with patch.object(S,'candidate_evidence',return_value=None):self.assertFalse(proof())
        with patch.object(S,'candidate_evidence',return_value=dict(predicate='呼ん',case='を',shared_roles=['information'])):self.assertFalse(proof())
        with patch.object(S,'candidate_evidence',return_value=dict(predicate='読ん',case='が',shared_roles=['information'])):self.assertFalse(proof())
        with patch.object(R,'_completed_native_verb_surface',return_value=False):self.assertFalse(proof())
        with patch.object(R,'native_nominal_phrase_faces',side_effect=lambda text:('内容','ぷねら') if text=='ないよう' else nominal(text)):
            self.assertFalse(R.native_written_action_nominal_parts(head+'ないよう'))
        # Separate positive arguments on two native homophones cannot be
        # joined into a proof. These patched semantic results never enter C.
        seen=[]
        def lexemes(surface,form,reading):
            return {'読む','呼ぶ'} if surface=='よん' else {'読む'} if surface=='読ん' else {'呼ぶ'} if surface=='呼ん' else set()
        def subject(noun,face,tail):
            seen.append(('subject',face));return dict(predicate=face,shared_roles=['person'] if face=='呼ん' else [])
        def obj(noun,face,tail):
            seen.append(('object',face));return dict(predicate=face,case='を',shared_roles=['information'] if face=='読ん' else [])
        with patch.object(S,'native_verb_lexemes',side_effect=lexemes),patch.object(S,'_native_lexeme_forms',side_effect=lambda lemma,form,reading:('読ん',) if lemma=='読む' else ('呼ん',)),patch.object(R,'_completed_native_verb_surface',return_value=True),patch.object(S,'subject_candidate_evidence',side_effect=subject),patch.object(S,'candidate_evidence',side_effect=obj):
            self.assertFalse(proof())
        self.assertEqual(set(seen),{('subject','読ん'),('object','読ん'),('subject','呼ん'),('object','呼ん')})

    def test_subject_kana_verb_nominal_application_keeps_common_gate(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        a=initial();source='先生がよんだないようを確認します';seen=[];check=C._check_replacement
        def observed(line,replacement,*args,**kwargs):
            ret=check(line,replacement,*args,**kwargs);seen.append((replacement,ret[0] is not None));return ret
        def result(text):
            return app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        try:
            with patch.object(C,'_check_replacement',side_effect=observed):r=result(source)
            self.assertEqual(r['corrected'],'先生が読んだ内容を確認します')
            self.assertFalse(r['odd_spans']);self.assertEqual(r['analysis_status'],'complete')
            self.assertEqual(r['original_spans'],[(3,5),(6,10)])
            for face in ('読ん','内容'):
                self.assertTrue(any(replacement[2]==face and allowed for replacement,allowed in seen),face)
            with patch.object(C,'_check_replacement',return_value=(None,'test_reject')):
                r=result(source);self.assertEqual(r['corrected'],source);self.assertEqual(r['analysis_status'],'complete')
            for text in ('入力は「'+source+'」です。',source+'という文字列です。'):
                r=result(text);self.assertEqual(r['corrected'],text);self.assertFalse(r['odd_spans'])
        finally:set_active(None)

    def test_written_verb_nominal_preserves_tail_cases_and_whole_noun(self):
        import semantic_roles as S
        phrase='先生がよく読んだないよう'
        self.assertEqual(R.native_written_relative_action('先生がよく読んだ'),('読んだ',('が',)))
        self.assertEqual(R.native_written_action_nominal_parts(phrase),(8,('内容',)))
        self.assertEqual(R.native_written_relative_nominal_heads(phrase),('内容',))
        proof=S.candidate_evidence('内容','読んだ','')
        self.assertEqual((proof['predicate'],proof['case']),('読んだ','を'))
        self.assertIn('information',proof['shared_roles'])
        for source in ('先生が文章を読んだないよう','ぷねらが読んだないよう',
                '先生が読んでないよう','先生が読みますですないよう',
                '先生が読んだぷねら','先生が読んだない','先生が\t読んだないよう'):
            self.assertFalse(R.native_written_action_nominal_parts(source),source)

    def test_written_verb_nominal_rechecks_actual_dictionary_and_coordinates(self):
        from types import SimpleNamespace
        phrase='先生がよく読んだないよう';tokenize=M.tokenize;dictionary=M.dictionary_inflections
        original=tokenize(phrase)
        self.assertEqual(R.native_written_action_nominal_parts(phrase),(8,('内容',)))
        for field,value in (('reading','かい'),('base_form','書く'),('infl_form','未然形'),
                ('start',4),('end',8),('has_reading',False),('surface','書い')):
            rows=[SimpleNamespace(**{key:getattr(t,key) for key in t.__slots__}) for t in original]
            token=next(t for t in rows if t.surface=='読ん');setattr(token,field,value)
            with self.subTest(field=field),patch.object(M,'tokenize',side_effect=lambda text:rows if text==phrase else tokenize(text)):
                self.assertFalse(R.native_written_action_nominal_parts(phrase))
        with patch.object(M,'dictionary_inflections',side_effect=lambda word:() if word=='読ん' else dictionary(word)):
            self.assertFalse(R.native_written_action_nominal_parts(phrase))

    def test_written_verb_nominal_cannot_borrow_other_head_or_noun_meaning(self):
        import semantic_roles as S
        phrase='先生がよく読んだないよう';nominal=R.native_nominal_phrase_faces;relative=R.native_written_relative_action
        with patch.object(R,'native_nominal_phrase_faces',side_effect=lambda text:('内容','ぷねら') if text=='ないよう' else nominal(text)):
            self.assertFalse(R.native_written_action_nominal_parts(phrase))
        with patch.object(S,'candidate_evidence',return_value=None):
            self.assertFalse(R.native_written_action_nominal_parts(phrase))
        with patch.object(R,'native_written_relative_action',side_effect=lambda text:('書いた',('が',)) if text=='先生がよく読んだ' else relative(text)):
            self.assertFalse(R.native_written_action_nominal_parts(phrase))
        import ime_spelling as I
        source=phrase+'を確認します'
        self.assertFalse(I._crosses_negative_attachment(source,8,12))
        with patch.object(R,'native_written_action_nominal_parts',return_value=()):
            self.assertTrue(I._crosses_negative_attachment(source,8,12))
        # An actual negative ending still owns its noun/link boundary.
        self.assertFalse(R.native_written_action_nominal_parts('先生が読まないよう'))

    def test_written_verb_nominal_application_uses_common_gate_and_source_span(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        a=initial();source='先生がよく読んだないようを確認します';seen=[];check=C._check_replacement
        def observed(line,replacement,*args,**kwargs):
            ret=check(line,replacement,*args,**kwargs);seen.append((replacement,ret[0] is not None));return ret
        def result(text):
            return app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        try:
            with patch.object(C,'_check_replacement',side_effect=observed):r=result(source)
            self.assertEqual(r['corrected'],'先生がよく読んだ内容を確認します')
            self.assertFalse(r['odd_spans']);self.assertEqual(r['analysis_status'],'complete')
            self.assertEqual(r['original_spans'],[(8,12)])
            self.assertTrue(any(replacement[2]=='内容' and allowed for replacement,allowed in seen))
            with patch.object(C,'_check_replacement',return_value=(None,'test_reject')):
                r=result(source);self.assertEqual(r['corrected'],source);self.assertEqual(r['analysis_status'],'complete')
            for text in ('入力は「'+source+'」です。',source+'という文字列です。'):
                r=result(text);self.assertEqual(r['corrected'],text);self.assertFalse(r['odd_spans'])
        finally:set_active(None)

    def test_argument_relative_nominal_heads_share_original_object_proof(self):
        phrase='先生がほうこくするないよう'
        self.assertEqual(R.native_argument_relative_nominal_parts(phrase),(9,('内容',)))
        self.assertEqual(R.native_written_relative_nominal_heads(phrase),('内容',))
        self.assertEqual(R.native_surface_nominal_heads(phrase),('内容',))
        source=phrase+'を保存します'
        self.assertIn((0,len(source)),R.native_context_ranges(source))
        self.assertEqual(R.native_object_predicate_proof(source,len(phrase)+1,('内容',),return_action=True),'保存')
        import kana_spelling as K
        self.assertFalse(K._argument_relative_nominal_scope(phrase+'を保存して'))
        for text in (phrase+'をぷねらします',phrase+'\tを保存します'):
            self.assertNotIn((0,len(text)),R.native_context_ranges(text),text)

    def test_argument_relative_nominal_heads_do_not_replace_missing_proof(self):
        phrase='先生がほうこくするないよう'
        direct=R.native_written_relative_nominal_heads.__wrapped__
        self.assertEqual(direct(phrase),('内容',))
        with patch.object(R,'native_argument_relative_nominal_parts',return_value=None):
            self.assertFalse(direct(phrase))
        for text in ('先生がほうこくしてないよう','先生がほうこくしますですないよう',
                '先生がほうこくするぷねら','ぷねらがほうこくするないよう',
                '先生が内容をほうこくするないよう','先制がほうこくするないよう',
                '先生が\tほうこくするないよう'):
            self.assertFalse(direct(text),text)
        actual=R.native_argument_relative_object_evidence
        with patch.object(R,'native_argument_relative_object_evidence',return_value=None):
            self.assertFalse(direct(phrase))
        nominal=R.native_nominal_phrase_faces
        with patch.object(R,'native_nominal_phrase_faces',side_effect=lambda text:('内容','ぷねら') if text=='ないよう' else nominal(text)):
            self.assertFalse(direct(phrase))

    def test_argument_relative_head_app_retains_common_gate_and_source_edits(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        a=initial();source='先生がほうこくするないようを保存します';seen=[];check=C._check_replacement
        def observed(line,replacement,*args,**kwargs):
            ret=check(line,replacement,*args,**kwargs);seen.append((replacement,ret[0] is not None));return ret
        def result(text):
            return app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        try:
            with patch.object(C,'_check_replacement',side_effect=observed):r=result(source)
            self.assertEqual(r['corrected'],'先生が報告する内容を保存します')
            self.assertFalse(r['odd_spans']);self.assertEqual(r['analysis_status'],'complete')
            self.assertEqual(r['original_spans'],[(3,7),(9,13)])
            for face in ('報告','内容'):
                self.assertTrue(any(replacement[2]==face and allowed for replacement,allowed in seen),face)
            with patch.object(C,'_check_replacement',return_value=(None,'test_reject')):
                r=result(source);self.assertEqual(r['corrected'],source);self.assertEqual(r['analysis_status'],'complete')
            for text in ('入力は「'+source+'」です。',source+'という文字列です。'):
                r=result(text);self.assertEqual(r['corrected'],text);self.assertFalse(r['odd_spans'])
        finally:set_active(None)

    def test_internal_adverb_keeps_subject_case_and_source_coordinates(self):
        for head,start,end,action in (('先生がよくほうこくした',5,9,'報告'),
                ('せんせいがよくせつめいした',7,11,'説明')):
            proof=R.native_subject_sahen_action(head)
            self.assertEqual(proof[:3],(start,end,action))
            self.assertIn('先生',proof[3])
            if head.startswith('先生'):
                self.assertEqual(R.native_written_relative_action(head),(action,('が',)))
            meaning=R.native_argument_relative_object_evidence(head,'内容')
            self.assertEqual((meaning['predicate'],meaning['case']),(action,'を'))
            self.assertTrue(meaning['shared_roles'])
        self.assertEqual(R.native_written_relative_action('先生がよく報告した'),('報告',('が',)))
        for source in ('先制がよく報告した','先生がぷねら報告した','先生が\tよく報告した','先生がよく報告して','先生がよく報告しますです'):
            self.assertFalse(R.native_written_relative_action(source),source)
        for source in ('先生がよくほうこくして','先生がよくほうこくしますです',
                '先生がぷねらほうこくした','先生が内容をよくほうこくした',
                'ぷねらがよくほうこくした','先制がよくほうこくした',
                '先生が\tよくほうこくした'):
            self.assertFalse(R.native_subject_sahen_action(source),source)

    def test_internal_adverb_requires_native_boundary_and_same_meaning(self):
        import semantic_roles as S
        source='先生がよくほうこくした'
        with patch.object(R,'native_adverbial_reading_cuts',return_value=()):
            self.assertFalse(R.native_subject_sahen_action(source))
            self.assertFalse(R.native_written_relative_action.__wrapped__('先生がよく報告した'))
        with patch.object(R,'completed_sahen_reading',return_value=False):
            self.assertFalse(R.native_subject_sahen_action(source))
        with patch.object(S,'subject_candidate_evidence',return_value=dict(predicate='説明',shared_roles=['person'])):
            self.assertFalse(R.native_subject_sahen_action(source))
        actual=M.dictionary_inflections
        for missing in ('が','報告'):
            with patch.object(M,'dictionary_inflections',side_effect=lambda face:() if face==missing else actual(face)):
                self.assertFalse(R.native_subject_sahen_action(source),missing)
        # A normal relative clause may share the original adjunct. The
        # additional path is not a new license for the helper's other modes.
        for option in ('allow_link','allow_finite','allow_note','allow_open_polite'):
            self.assertFalse(R.native_written_relative_action.__wrapped__('先生がよく報告した',**{option:True}),option)

    def test_internal_adverb_candidate_rechecks_original_scope_and_both_roles(self):
        import kana_spelling as K,semantic_roles as S
        source='先生がよくほうこくした内容を確認します'
        proof=K._sahen_relative_spelling_evidence(source,5,9,'報告')
        self.assertEqual((proof['predicate'],proof['noun_start'],proof['noun_faces']),('報告',11,('内容',)))
        for a,b,face in ((3,9,'報告'),(5,8,'報告'),(5,9,'説明')):
            self.assertIsNone(K._sahen_relative_spelling_evidence(source,a,b,face))
        members=set();links={};units=K._lexical_units(source,M.tokenize(source),members,links)
        self.assertIn((5,9),units);self.assertEqual(links[(5,9)],11)
        self.assertFalse(any(lo<5<hi or lo<9<hi for lo,hi in units))
        with patch.object(S,'subject_candidate_evidence',return_value=None):
            self.assertIsNone(K._sahen_relative_spelling_evidence(source,5,9,'報告'))
        with patch.object(K,'_relative_object_spelling_evidence',return_value=dict(predicate='説明',case='を',shared_roles=['information'])):
            self.assertIsNone(K._sahen_relative_spelling_evidence(source,5,9,'報告'))
        with patch.object(K,'_argument_relative_nominal_scope',return_value=(11,13,('内容','ぷねら'))):
            self.assertIsNone(K._sahen_relative_spelling_evidence(source,5,9,'報告'))

    def test_internal_adverb_application_keeps_common_gate_and_literal(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        a=initial();seen=[];check=C._check_replacement
        def observed(line,replacement,*args,**kwargs):
            ret=check(line,replacement,*args,**kwargs);seen.append((replacement,ret[0] is not None));return ret
        def result(text):
            return app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        try:
            for source,expected,edits in (
                    ('先生がよくほうこくした内容を確認します。','先生がよく報告した内容を確認します。',[(5,9)]),
                    ('せんせいがよくせつめいしたほうほう','先生がよく説明した方法',[(0,4),(7,11),(13,17)])):
                seen.clear()
                with patch.object(C,'_check_replacement',side_effect=observed):r=result(source)
                self.assertEqual(r['corrected'],expected)
                self.assertFalse(r['odd_spans']);self.assertEqual(r['analysis_status'],'complete')
                self.assertEqual(r['original_spans'],edits)
                self.assertTrue(any(replacement[2] in ('報告','説明') and allowed for replacement,allowed in seen))
            source='先生がよくほうこくした内容を確認します'
            with patch.object(C,'_check_replacement',return_value=(None,'test_reject')):
                r=result(source);self.assertEqual(r['corrected'],source);self.assertEqual(r['analysis_status'],'complete')
            for text in ('入力は「'+source+'」です。',source+'という文字列です。'):
                r=result(text);self.assertEqual(r['corrected'],text);self.assertFalse(r['odd_spans'])
        finally:set_active(None)

    def test_subject_sahen_source_keeps_actual_case_and_complete_tail(self):
        for head,start,end in (('せんせいがほうこくする',5,9),('先生がほうこくする',3,7)):
            proof=R.native_subject_sahen_action(head)
            self.assertEqual(proof[:3],(start,end,'報告'))
            self.assertIn('先生',proof[3])
            if start==3:self.assertEqual(R.native_written_relative_action(head),('報告',('が',)))
            meaning=R.native_argument_relative_object_evidence(head,'内容')
            self.assertEqual((meaning['predicate'],meaning['case'],meaning['shared_roles']),('報告','を',['information']))
            self.assertEqual(R.native_argument_relative_nominal_parts(head+'ないよう'),(len(head),('内容',)))
        for source in ('先生がほうこくして','先生がほうこくしますです','先生がほうこくし',
                '先生が内容をほうこくする','ぷねらがほうこくする','先生が\tほうこくする',
                '先制がほうこくする','先生がぷねらする'):
            self.assertFalse(R.native_subject_sahen_action(source),source)

    def test_subject_sahen_source_requires_original_ga_and_dictionary(self):
        from copy import copy
        source='先生がほうこくする';tokens=M.tokenize(source);tokenize=M.tokenize
        for field,value in (('surface','は'),('reading','は'),('pos','名詞'),('pos_sub','係助詞'),
                ('base_form','は'),('infl_form','未然形'),('start',1),('end',4),('has_reading',False)):
            changed=[copy(t) for t in tokens];setattr(next(t for t in changed if t.surface=='が'),field,value)
            with patch.object(M,'tokenize',side_effect=lambda text:changed if text==source else tokenize(text)):
                self.assertFalse(R.native_subject_sahen_action(source),field)
        import semantic_roles as S
        with patch.object(S,'subject_candidate_evidence',return_value=dict(predicate='説明',shared_roles=['person'])):
            self.assertFalse(R.native_subject_sahen_action(source))
        actual=M.dictionary_inflections
        for missing in ('が','報告'):
            with patch.object(M,'dictionary_inflections',side_effect=lambda face:() if face==missing else actual(face)):
                self.assertFalse(R.native_subject_sahen_action(source),missing)
        with patch.object(R,'completed_sahen_reading',return_value=False):
            self.assertFalse(R.native_subject_sahen_action(source))
        with patch.object(R,'native_attributive_predicate_end',return_value=False):
            self.assertFalse(R.native_subject_sahen_action(source))
        with patch.object(R,'_native_written_nominal_faces',return_value=()):
            self.assertFalse(R.native_subject_sahen_action(source))

    def test_subject_sahen_candidate_owns_both_meanings_and_exact_seam(self):
        import kana_spelling as K,semantic_roles as S
        source='せんせいがほうこくするないようを共有します'
        proof=K._sahen_relative_spelling_evidence(source,5,9,'報告')
        self.assertEqual((proof['predicate'],proof['noun_start'],proof['noun_faces']),('報告',11,('内容',)))
        for a,b,face in ((4,9,'報告'),(5,8,'報告'),(5,9,'説明')):
            self.assertIsNone(K._sahen_relative_spelling_evidence(source,a,b,face))
        with patch.object(S,'subject_candidate_evidence',return_value=None):
            self.assertIsNone(K._sahen_relative_spelling_evidence(source,5,9,'報告'))
        real=K._relative_object_spelling_evidence
        with patch.object(K,'_relative_object_spelling_evidence',side_effect=lambda head,noun:dict(predicate='説明',case='を',shared_roles=['information'])):
            self.assertIsNone(K._sahen_relative_spelling_evidence(source,5,9,'報告'))
        with patch.object(K,'_argument_relative_nominal_scope',return_value=(11,15,('内容','ぷねら'))):
            self.assertIsNone(K._sahen_relative_spelling_evidence(source,5,9,'報告'))
        members=set();links={};units=K._lexical_units(source,M.tokenize(source),members,links)
        self.assertIn((5,9),units);self.assertEqual(links[(5,9)],11)
        self.assertFalse(any(lo<9<hi for lo,hi in units))
        with patch.object(K,'_argument_relative_nominal_scope',return_value=()):
            self.assertIsNone(K._sahen_relative_spelling_evidence(source,5,9,'報告'))
        for text in ('先生がほうこくするないようを共有して','先生がほうこくするぷねらを共有します',
                '先生がほうこくしてないようを共有します','先生がほうこくするないよう\tを共有します'):
            self.assertFalse(K._sahen_relative_spelling_evidence(text,3,7,'報告'),text)

    def test_subject_sahen_app_finishes_through_common_gate(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        a=initial();source='せんせいがほうこくするないようを共有します';seen=[];check=C._check_replacement
        def observed(line,replacement,*args,**kwargs):
            ret=check(line,replacement,*args,**kwargs);seen.append((replacement,ret[0] is not None));return ret
        def result(text):
            return app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        try:
            with patch.object(C,'_check_replacement',side_effect=observed):r=result(source)
            self.assertEqual(r['corrected'],'先生が報告する内容を共有します')
            self.assertFalse(r['odd_spans']);self.assertEqual(r['analysis_status'],'complete')
            self.assertEqual(r['original_spans'],[(0,4),(5,9),(11,15)])
            for face in ('先生','報告','内容'):
                self.assertTrue(any(replacement[2]==face and allowed for replacement,allowed in seen),face)
            with patch.object(C,'_check_replacement',return_value=(None,'test_reject')):
                r=result(source);self.assertEqual(r['corrected'],source);self.assertEqual(r['analysis_status'],'complete')
            for text in ('入力は「'+source+'」です。',source+'という文字列です。'):
                r=result(text);self.assertEqual(r['corrected'],text);self.assertFalse(r['odd_spans'])
        finally:set_active(None)

    def test_written_relative_whole_function_token_is_not_a_noun(self):
        import oddness as O
        source='変更するない';parts=M.tokenize(source)
        last=parts[-1]
        self.assertEqual((last.surface,last.start,last.end,last.pos,last.infl_form),('ない',4,6,'助動詞','基本形'))
        self.assertIn('内',R._native_nominal_reading_faces(source[4:]))
        self.assertFalse(R.native_written_sahen_nominal_parts(source))
        self.assertFalse(R.native_written_action_nominal_parts(source))
        self.assertNotIn((0,len(source)),R.native_context_ranges(source))
        self.assertFalse(O.changed_auxiliary_chain_allowed(source,0,2,original='へんこうするない'))
        for text,original in (('変更しない','へんこうしない'),('変更しなかった','へんこうしなかった')):
            self.assertTrue(O.changed_auxiliary_chain_allowed(text,0,2,original=original),text)
        for text in ('変更するないよう','変更したないよう'):
            self.assertIn((0,len(text)),R.native_context_ranges(text),text)

    def test_written_relative_function_token_reaches_common_validation(self):
        import corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        a=initial();tokenize=C.make_tokenizer(a.store)
        try:
            for lo,hi,face in ((0,4,'変更'),(0,8,'変更するない')):
                accepted,reason=C._check_replacement('へんこうするない',(lo,hi,face,'かな入力'),a.store,tokenize,a.dict_index,a.decisions)
                self.assertIsNone(accepted)
                self.assertEqual(reason,'native_auxiliary_chain')
        finally:set_active(None)

    def test_written_relative_function_token_keeps_source_anomaly(self):
        import app
        from tests_analysis_async import initial
        from last_choice import set_active
        a=initial()
        def result(text):
            return app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        try:
            r=result('変更するない')
            self.assertEqual(r['corrected'],'変更するない')
            self.assertTrue(r['odd_spans'])
            self.assertEqual(r['analysis_status'],'complete')
            # The bare input label has no existing explicit-example protection.
            # Keep its body contract; record its raw marks in the frozen controls.
            self.assertEqual(result('入力は「変更するない」です。')['corrected'],'入力は「変更するない」です。')
            for text in ('変更しない','変更しなかった','入力の例は「変更するない」です。','変更するないという文字列です。'):
                r=result(text);self.assertEqual(r['corrected'],text)
                self.assertFalse(r['odd_spans']);self.assertEqual(r['analysis_status'],'complete')
        finally:set_active(None)

    def test_written_action_whole_kana_noun_retains_own_meaning(self):
        import semantic_roles as S
        source='変更するないよう'
        self.assertEqual(R.native_written_action_nominal_parts(source),(4,('内容',)))
        self.assertEqual(R.native_written_relative_nominal_heads(source),('内容',))
        self.assertTrue(any(a==0 and b==len(source) for a,b in R.native_context_ranges(source)))
        self.assertEqual(R.native_written_action_nominal_parts('先生が説明するないよう'),(7,('内容',)))
        proof=S.candidate_evidence('内容','変更する','')
        self.assertEqual((proof['predicate'],proof['case'],proof['shared_roles']),('変更','を',['information']))
        self.assertFalse(R.native_written_action_nominal_parts('偏向するないよう'))
        self.assertFalse(R.native_written_action_nominal_parts('整理するないよう'))

    def test_written_action_nominal_requires_all_original_proofs(self):
        import semantic_roles as S
        source='変更するないよう';real=R.native_nominal_phrase_faces
        with patch.object(R,'native_nominal_phrase_faces',side_effect=lambda t:('内容','ぷねら') if t=='ないよう' else real(t)):
            self.assertFalse(R.native_written_action_nominal_parts(source))
        for owner,name,value in ((R,'native_written_relative_action',()),
                (R,'native_attributive_predicate_end',False),
                (S,'candidate_evidence',None)):
            with patch.object(owner,name,return_value=value):
                self.assertFalse(R.native_written_action_nominal_parts(source),name)
        proof=dict(S.candidate_evidence('内容','変更する',''),predicate='説明')
        with patch.object(S,'candidate_evidence',return_value=proof):
            self.assertFalse(R.native_written_action_nominal_parts(source))
        actual=M.dictionary_inflections
        with patch.object(M,'dictionary_inflections',side_effect=lambda face:() if face=='変更' else actual(face)):
            self.assertFalse(R.native_written_action_nominal_parts(source))
        tokens=M.tokenize(source);from copy import copy
        changed=[copy(t) for t in tokens];changed[0].start=1
        tokenize=M.tokenize
        with patch.object(M,'tokenize',side_effect=lambda t:changed if t==source else tokenize(t)):
            self.assertFalse(R.native_written_action_nominal_parts(source))
        for text in ('変更しないように','変更するない','変更するないようだ',
                '変更しますですないよう','変更してないよう','変更するぷねら',
                '先生が内容を説明するないよう','変更する\tないよう'):
            self.assertFalse(R.native_written_action_nominal_parts(text),text)

    def test_written_action_noun_proof_reaches_same_auxiliary_gate(self):
        import oddness as O
        old='へんこうするないようをかくにんします'
        candidate='変更するないようをかくにんします'
        self.assertTrue(O.changed_auxiliary_chain_allowed(candidate,0,2,original=old))
        with patch.object(R,'native_context_ranges',return_value=()):
            self.assertFalse(O.changed_auxiliary_chain_allowed.__wrapped__(candidate,0,2,original=old))
        self.assertFalse(O.changed_auxiliary_chain_allowed('偏向するないようをかくにんします',0,2,original=old))
        # The former full-function-token defect has a separate regression.
        # This action-specific nominal proof must still reject the token.
        self.assertFalse(R.native_written_action_nominal_parts('変更するない'))
        self.assertFalse(O.changed_auxiliary_chain_allowed('変更しますです',0,2,original='へんこうしますです'))

    def test_written_action_nominal_case_is_original_and_dictionary_backed(self):
        import ime_spelling as I
        from copy import copy
        source='変更するないようを確認します'
        self.assertFalse(I._crosses_negative_attachment(source,4,8))
        with patch.object(R,'native_written_action_nominal_parts',return_value=()):
            self.assertTrue(I._crosses_negative_attachment(source,4,8))
        tokens=M.tokenize(source);tokenize=M.tokenize
        for field,value in (('reading','が'),('pos','名詞'),('base_form','が'),('infl_form','未然形'),('end',10),('has_reading',False)):
            changed=[copy(t) for t in tokens];case=next(t for t in changed if t.start==8);setattr(case,field,value)
            with patch.object(M,'tokenize',side_effect=lambda t:changed if t==source else tokenize(t)):
                self.assertTrue(I._crosses_negative_attachment(source,4,8),field)
        actual=M.dictionary_inflections
        with patch.object(M,'dictionary_inflections',side_effect=lambda face:() if face=='を' else actual(face)):
            self.assertTrue(I._crosses_negative_attachment(source,4,8))
        for text in ('変更するないようぷねら','変更するないよう\tを確認します'):
            self.assertTrue(I._crosses_negative_attachment(text,4,8),text)

    def test_written_action_kana_noun_finishes_through_common_gate(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        a=initial();source='変更するないようを確認します';seen=[];check=C._check_replacement
        def observed(line,replacement,*args,**kwargs):
            result=check(line,replacement,*args,**kwargs);seen.append((replacement,result[0] is not None));return result
        def result(text):
            return app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        try:
            with patch.object(C,'_check_replacement',side_effect=observed):r=result(source)
            self.assertEqual(r['corrected'],'変更する内容を確認します')
            self.assertFalse(r['odd_spans']);self.assertEqual(r['analysis_status'],'complete')
            self.assertEqual(r['original_spans'],[(4,8)])
            self.assertTrue(any(replacement[2]=='内容' and allowed for replacement,allowed in seen))
            with patch.object(C,'_check_replacement',return_value=(None,'test_reject')):
                r=result(source);self.assertEqual(r['corrected'],source);self.assertEqual(r['analysis_status'],'complete')
            for text in ('入力は「変更するないよう」です。','変更するないようという文字列です。'):
                self.assertEqual(result(text)['corrected'],text)
        finally:set_active(None)

    def test_prefix_relative_noun_boundary_survives_unresolved_action_spelling(self):
        import kana_spelling as K
        source='さいけんとうしたしょるい'
        proof=R.native_prefix_sahen_relative_parts(source)
        self.assertTrue(any(edge==8 for head,edge,stem,faces in proof))
        self.assertTrue(any('再検討' in faces and '再見当' in faces
                            for head,edge,stem,faces in proof))
        for text,edge in ((source,8),('さいひょうかしたしょるい',8),
                          ('さいにゅうりょくしたしょるい',10)):
            nominal=set();units=K._lexical_units(text,M.tokenize(text),nominal)
            self.assertIn((edge,len(text)),nominal,text)
            self.assertIn((edge,len(text)),units,text)
            self.assertFalse(any(a<edge<b for a,b in units),text)
        nominal=set()
        with patch.object(R,'native_prefix_sahen_relative_parts',return_value=()):
            units=K._lexical_units(source,M.tokenize(source),nominal)
        self.assertNotIn((8,len(source)),nominal)
        self.assertNotIn((8,len(source)),units)
        for text in ('さいぷねらしたしょるい','さいけんとうすたしょるい',
                     'さいけんとうししょるい','さいけんとうしたぷねら',
                     'さいけんとうしたしょるいぷねら','さいけんとうした\tしょるい'):
            self.assertFalse(R.native_prefix_sahen_relative_parts(text),text)

    def test_prefix_relative_noun_spelling_keeps_ambiguous_head_and_common_gate(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        a=initial()
        def result(text):
            return app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                decisions=a.decisions,context_vec=None)
        try:
            source='さいけんとうしたしょるい'
            r=result(source)
            self.assertEqual(r['corrected'],'さいけんとうした書類')
            self.assertFalse(r['odd_spans']);self.assertEqual(r['analysis_status'],'complete')
            self.assertEqual(r['original_spans'],[(8,12)])
            for text in ('さいけんとうしたあん','さいけんとうしたしょうひん',
                         '再検討した書類','入力は「さいけんとうしたしょるい」です。',
                         'さいけんとうしたしょるいという文字列です。'):
                self.assertEqual(result(text)['corrected'],text)
            with patch.object(C,'_check_replacement',return_value=(None,'test_reject')):
                self.assertEqual(result(source)['corrected'],source)
        finally:set_active(None)

    def test_prefix_relative_noun_crossing_protection_keeps_original_seam(self):
        import app,kana_spelling as K
        from tests_analysis_async import initial
        from last_choice import set_active
        source='さいけんとうしたぶんしょう'
        parts=M.tokenize(source)
        self.assertTrue(any(t.surface=='たぶん' and t.pos=='副詞'
                            and (t.start,t.end)==(7,10) for t in parts))
        self.assertTrue(any(head==6 and edge==8 for head,edge,stem,faces
                            in R.native_prefix_sahen_relative_parts(source)))
        self.assertEqual(R.native_nominal_phrase_faces(source[8:]),('文章',))
        self.assertFalse(K._relative_object_spelling_evidence(source[:8],'文章'))
        a=initial()
        try:
            r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                decisions=a.decisions,context_vec=None)
            self.assertEqual(r['corrected'],'さいけんとうした文章')
            self.assertEqual(r['original_spans'],[(8,13)])
            self.assertFalse(r['odd_spans']);self.assertEqual(r['analysis_status'],'complete')
            with patch.object(R,'native_prefix_sahen_relative_parts',return_value=()):
                self.assertIsNone(K.project(source,a.store,a.dict_index,a.decisions))
        finally:set_active(None)

    def test_prefix_relative_noun_crossing_preserves_whole_protection_and_gate(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        a=initial()
        def result(text):
            return app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                decisions=a.decisions,context_vec=None)
        try:
            for text in ('さいけんとうしたほうほう','さいけんとうしたないよう',
                         'さいけんとうしたしょうひん','たぶん書類です。','再検討した文章',
                         '入力は「さいけんとうしたぶんしょう」です。',
                         'さいけんとうしたぶんしょうという文字列です。'):
                self.assertEqual(result(text)['corrected'],text)
            for text in ('さいぷねらしたぶんしょう','さいけんとうすたぶんしょう',
                         'さいけんとうしぶんしょう','さいけんとうしたぶんしょうぷねら',
                         'さいけんとうした\tぶんしょう'):
                self.assertFalse(R.native_prefix_sahen_relative_parts(text),text)
            source='さいけんとうしたぶんしょう'
            with patch.object(C,'_check_replacement',return_value=(None,'test_reject')):
                self.assertEqual(result(source)['corrected'],source)
        finally:set_active(None)

    def test_written_relative_noun_shares_source_range_and_negative_boundary(self):
        for text in ('確認したしゃしん','修正したずめん','保存したしょるい'):
            self.assertTrue(R.native_written_sahen_nominal_parts(text),text)
            self.assertIn((0,len(text)),R.native_context_ranges(text),text)
            self.assertFalse(R.native_negative_auxiliary_chains(text),text)
        for text in ('試してみずに決めます。','確かめてみずに進みます。','確認しない写真'):
            self.assertTrue(R.native_negative_auxiliary_chains(text),text)
        for text in ('確認したぷねら','修正すたずめん','保存しますしょるい'):
            self.assertFalse(R.native_written_sahen_nominal_parts(text),text)
            self.assertNotIn((0,len(text)),R.native_context_ranges(text),text)

    def test_written_relative_noun_finishes_after_common_source_validation(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        a=initial()
        def result(text):
            return app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                decisions=a.decisions,context_vec=None)
        try:
            for text,expected in (('確認したしゃしん','確認した写真'),('修正したずめん','修正した図面'),('保存したしょるい','保存した書類')):
                r=result(text);self.assertEqual(r['corrected'],expected)
                self.assertFalse(r['odd_spans']);self.assertEqual(r['analysis_status'],'complete')
            for text in ('確認したぷねら','試してみずに決めます。','「確認したしゃしん」と入力しました。'):
                self.assertEqual(result(text)['corrected'],text)
            with patch.object(C,'_check_replacement',return_value=(None,'test_reject')):
                self.assertEqual(result('確認したしゃしん')['corrected'],'確認したしゃしん')
        finally:set_active(None)

    def test_written_suru_relative_seam_keeps_the_entire_noun_reading(self):
        import kana_spelling as K
        from tests_analysis_async import initial
        from last_choice import set_active
        a=initial()
        try:
            for text,edge in (('紹介したさくひん',4),('評価したさくひん',4),('再評価したしょうひん',5)):
                proof=R.native_written_sahen_nominal_parts(text)
                self.assertTrue(any(end==edge for begin,end,faces in proof),text)
                nominal=set();units=K._lexical_units(text,M.tokenize(text),nominal)
                self.assertIn((edge,len(text)),nominal)
                self.assertFalse(any(begin<edge<end for begin,end in units),text)
            for text in ('紹介すたさくひん','紹介しますさくひん','ぷねらしたさくひん',
                         '紹介したさくひんぷねら','紹介した寝ます','紹介したさくひん\t商品'):
                self.assertFalse(R.native_written_sahen_nominal_parts(text),text)
        finally:set_active(None)

    def test_written_suru_relative_spelling_retains_unknown_senses_and_final_gate(self):
        import app,corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        a=initial()
        def result(text):
            return app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                decisions=a.decisions,context_vec=None)
        try:
            for text,expected in (('紹介したさくひん','紹介した作品'),('評価したさくひん','評価した作品')):
                r=result(text);self.assertEqual(r['corrected'],expected)
                self.assertFalse(r['odd_spans']);self.assertEqual(r['analysis_status'],'complete')
            # 商品/賞品 are both ordinary native senses; grammar alone does
            # not select the intended meaning of an unchanged noun reading.
            self.assertEqual(result('再評価したしょうひん')['corrected'],'再評価したしょうひん')
            for text in ('紹介したぷねら','「紹介したさくひん」と入力しました。'):
                self.assertEqual(result(text)['corrected'],text)
            with patch.object(C,'_check_replacement',return_value=(None,'test_reject')):
                self.assertEqual(result('紹介したさくひん')['corrected'],'紹介したさくひん')
        finally:set_active(None)

    def test_nominal_style_requires_positive_person_meaning(self):
        for face,rd in (('物','もの'),('者','もの'),('事','こと'),('古都','こと')):
            self.assertTrue(F.prefers_kana(face,rd))
        for following in ('が読んだ。','を招待します。'):
            self.assertFalse(F.prefers_kana('者','もの','',following))
            self.assertTrue(F.prefers_kana('物','もの','',following))
        for following in ('が動きます。','を運ぶ。','は資料です。'):
            self.assertTrue(F.prefers_kana('者','もの','',following))
        self.assertFalse(F.prefers_kana('着物','きもの'))
        self.assertFalse(F.prefers_kana('物語','ものがたり'))

    def test_source_auxiliary_and_colloquial_word_are_not_shorter_nouns(self):
        import app
        from tests_analysis_async import initial
        a=initial();revision=a.store.revision()
        for text in ('コピーしたいものを','おもしれえ','ということは',
                     '物をそのまま残す','事を荒立てない。','者を招待します。'):
            with self.subTest(text=text):
                r=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                                   decisions=a.decisions,context_vec=None)
                self.assertEqual(r['corrected'],text)
                self.assertFalse(r['odd_spans'])
        self.assertEqual(a.store.revision(),revision)

    def test_same_reading_person_choice_is_not_turned_into_object_spelling(self):
        from kana_spelling import finish
        import corrector as E
        from tests_analysis_async import initial
        a=initial();tok=E.make_tokenizer(a.store);text='ものを招待します。'
        with patch('last_choice.surface_for_reading',side_effect=lambda rd:'者' if rd=='もの' else ''):
            result=finish(text,dict(corrected=text),a.store,tok,a.dict_index,a.decisions)
        self.assertEqual(result['corrected'],'者を招待します。')

    def test_native_unknown_whole_word_restores_without_splitting_names(self):
        unknown=M.Token('オフ','名詞','オフ','',0,2,False,'一般')
        original=M.dictionary_inflections('オフ')
        restored=M._restore_attested_nouns('オフ',[unknown])
        self.assertEqual([(t.surface,t.reading,t.has_reading) for t in restored],[('オフ','おふ',True)])
        for word in ('オフプネラ','プネラオフ'):
            t=M.Token(word,'名詞',word,'',0,len(word),False,'一般')
            self.assertEqual(M._restore_attested_nouns(word,[t]),[t])
        name=M.Token('オフ','名詞','オフ','おふ',0,2,True,'固有名詞:組織')
        self.assertIs(M._restore_attested_nouns('オフ',[name])[0],name)
        self.assertEqual(M.dictionary_inflections('オフ'),original)

    def test_attested_bound_stems_share_only_their_complete_noun(self):
        before=M.dictionary_inflections('焙煎')
        parts=M.tokenize('焙煎度')
        self.assertEqual((parts[0].surface,parts[0].reading,parts[0].pos),('焙煎','ばいせん','名詞'))
        self.assertEqual(M.dictionary_inflections('焙煎'),before)
        for word in ('対象外','焙煎度'):
            self.assertIn(word,R.native_written_derived_nominal_faces(word))
        for word in ('プネラ外','プネラ度','対象がい','焙煎ど'):
            self.assertFalse(R.native_written_derived_nominal_faces(word))

    def test_likeness_needs_an_actual_finite_predicate_and_copula(self):
        for text in ('しているような','読み終わったようです'):
            self.assertEqual(R.native_likeness_predicate_ranges(text),((0,len(text)),))
        for text in ('しような','しますような','プネラような','読んでような'):
            self.assertFalse(R.native_likeness_predicate_ranges(text))

    def test_rare_bare_lemma_does_not_erase_real_negation(self):
        self.assertFalse(R.native_negative_auxiliary_chains('ひらんがな'))
        for text in ('知らんがな','行かない','屁をひらん'):
            self.assertTrue(R.native_negative_auxiliary_chains(text))
        # Lack of a usage judgment alone is never a negative-chain exception.
        with patch('kango_tier.is_restricted',return_value=False):
            R.native_negative_auxiliary_chains.cache_clear()
            self.assertTrue(R.native_negative_auxiliary_chains('ひらんがな'))
        R.native_negative_auxiliary_chains.cache_clear()

    def test_screen_marker_role_does_not_certify_an_unrelated_action(self):
        import semantic_roles as S
        for word in ('カーソル','ポインター','キャレット'):
            self.assertTrue(S.support(word,'持つ'))
            self.assertFalse(S.support(word,'食べる'))

    def test_narrow_suru_connection_keeps_the_original_action_noun(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        result=app.correct_line('クリック詩ながら',a.store,input_method='kana',
                                dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        self.assertEqual(result['corrected'],'クリックしながら')
        self.assertFalse(result['odd_spans'])


    def test_sourced_suru_evidence_reaches_connections_without_ime(self):
        import particle_frames as P
        from general_words import sourced_sahen_noun
        before=M.dictionary_inflections('クリック')
        with patch('ime_language._factory',None):
            P._native_action_noun.cache_clear()
            for face,reading in (('クリック','くりっく'),('プレイ','ぷれい'),('アンドゥ','あんどぅ')):
                with self.subTest(face=face):
                    self.assertTrue(sourced_sahen_noun(face,reading))
                    self.assertTrue(P._native_action_noun(face,reading))
                    self.assertFalse(P._native_action_noun(face,reading+'ん'))
                    self.assertTrue(P.converted_suru_connection_frames(face+'詩ながら'))
            for source in ('詩ながら','天気詩ながら','ぷねら詩ながら','クリック詩',
                           'クリック詩を書きます。','「クリック詩ながら」と入力した。'):
                with self.subTest(source=source):
                    self.assertFalse(P.converted_suru_connection_frames(source))
            self.assertEqual(M.dictionary_inflections('クリック'),before)
        P._native_action_noun.cache_clear()

    def test_sourced_suru_connection_keeps_action_and_scope(self):
        import app,particle_frames as P
        from tests_analysis_async import initial
        a=initial()
        with patch('ime_language._factory',None):
            P._native_action_noun.cache_clear()
            for source,expected in (('クリック詩ながら','クリックしながら'),
                                    ('プレイ詩つつ','プレイしつつ'),
                                    ('コピー詩ながら','コピーしながら'),
                                    ('クリックしながら','クリックしながら'),
                                    ('「クリック詩ながら」と入力した。','「クリック詩ながら」と入力した。')):
                with self.subTest(source=source):
                    result=app.correct_line(source,a.store,input_method='kana',
                        dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
                    self.assertEqual(result['corrected'],expected)
                    self.assertFalse(result['odd_spans'])
        P._native_action_noun.cache_clear()

    def test_neutral_inflection_keeps_existing_positive_usage(self):
        import app,corrector as C,kango_tier as K
        self.assertEqual(K.known_usage_tier('残る'),1)
        self.assertIsNone(K.known_usage_tier('遺る'))
        for source,expected in (('のこっています','残っています'),
                                ('のこっています\tのこっています','残っています\t残っています')):
            with self.subTest(source=source):
                r=self.run_line(source)
                self.assertEqual(r['corrected'],expected)
                self.assertEqual(r['odd_spans'],[])
                self.assertEqual(r['analysis_status'],'complete')
        for source in ('遺っています。','「のこっています」と入力します。'):
            self.assertEqual(self.run_line(source)['corrected'],source)
        with patch.object(C,'_check_replacement',return_value=(None,'test_reject')):
            self.assertEqual(self.run_line('のこっています')['corrected'],'のこっています')

    def test_potential_origin_usage_does_not_choose_an_unrelated_neutral_lemma(self):
        import kango_tier as K
        row=next(row for row in M.dictionary_inflections('買える')
                 if row[1:]==('基本形','買える','かえる'))
        self.assertIsNone(K.usage_tier_for_reading('買える','かえる'))
        self.assertEqual(K.native_inflection_usage_tier('買える',*row),1)
        source='入力してかえる'
        result=self.run_line(source)
        self.assertEqual(result['corrected'],source)
        self.assertEqual(result['odd_spans'],[])
        self.assertEqual(result['analysis_status'],'complete')
        for source,expected in (('とれるしゅだん','取れる手段'),
                                ('のこっています','残っています'),
                                ('入力して買える','入力して買える')):
            self.assertEqual(self.run_line(source)['corrected'],expected)

    def test_neutral_potential_keeps_explicit_choice_and_common_gate(self):
        import corrector as C
        source='入力してかえる'
        with patch('last_choice.surface_for_reading',side_effect=lambda rd:'買える' if rd=='かえる' else None):
            self.assertEqual(self.run_line(source)['corrected'],'入力して買える')
            with patch.object(C,'_check_replacement',return_value=(None,'test_reject')):
                self.assertEqual(self.run_line(source)['corrected'],source)
        quoted='「入力してかえる」と入力します。'
        self.assertEqual(self.run_line(quoted)['corrected'],quoted)

    def test_original_case_relations_precede_potential_usage(self):
        from semantic_roles import candidate_evidence
        prefix='言葉を別の言葉に'
        for face in ('変え','替え','代え'):
            for case in ('を','に'):
                self.assertTrue(candidate_evidence('言葉',face,'ます。',prefix,case=None if case=='を' else case)['shared_roles'])
        self.assertTrue(candidate_evidence('言葉','買え','ます。',prefix)['shared_roles'])
        self.assertFalse(candidate_evidence('言葉','買え','ます。',prefix,case='に')['shared_roles'])
        for source in ('言葉を別の言葉にかえます。','えらんだことばをべつのことばにかえます。'):
            with self.subTest(source=source):
                result=self.run_line(source)
                assert_reviewed_source_spelling(self,result['corrected'],source)
                self.assertEqual(result['odd_spans'],[])
                self.assertEqual(result['analysis_status'],'complete')

    def test_more_case_evidence_keeps_unknowns_choice_and_shared_gate(self):
        import corrector as C
        source='言葉を別の言葉にかえます。'
        with patch('last_choice.surface_for_reading',side_effect=lambda rd:'買え' if rd=='かえ' else None):
            self.assertEqual(self.run_line(source)['corrected'],'言葉を別の言葉に買えます。')
            with patch.object(C,'_check_replacement',return_value=(None,'test_reject')):
                self.assertEqual(self.run_line(source)['corrected'],source)
        for text in ('本を買えます。','店で本を買えます。','入力してかえる',
                     '「言葉を別の言葉にかえます。」と入力します。'):
            with self.subTest(text=text):self.assertEqual(self.run_line(text)['corrected'],text)

    def test_neutral_usage_cannot_choose_equal_or_unjudged_senses(self):
        import kana_spelling as P,kango_tier as K
        for value in (None,1):
            with patch.object(K,'usage_tier_for_reading',return_value=value):
                self.assertIsNone(P.project('のこっています',self.a.store,self.a.dict_index,self.a.decisions))
        with patch('last_choice.surface_for_reading',side_effect=lambda rd:'遺っ' if rd=='のこっ' else None):
            r=P.project('のこっています',self.a.store,self.a.dict_index,self.a.decisions)
            self.assertIsNotNone(r)
            self.assertEqual(r[0],'遺っています')

    def test_kana_identity_is_not_a_competing_adjective_sense(self):
        for source,expected in (('あかい皿です。','赤い皿です。'),('しろい棚です。','白い棚です。'),('紅い皿です。','紅い皿です。'),('明い場所です。','明い場所です。')):
            result=self.run_line(source)
            self.assertEqual(result['corrected'],expected)
            self.assertEqual(result.get('odd_spans'),[])
        result=self.run_line('あついお茶をさましてからのみます。')
        self.assertTrue(result['corrected'].startswith('あつい'))

    def test_derived_adjective_nouns_reach_written_spelling(self):
        import reading_segments as R,app
        for reading,face in (('おもさ','重さ'),('たかさ','高さ'),('ながさ','長さ')):
            with self.subTest(reading=reading):
                self.assertIn(face,R.native_nominal_spelling_faces(reading))
        self.assertNotIn('重さ',R.native_nominal_spelling_faces('おも'))
        for source,expected in (('おもさをはかる','重さを量る'),('たかさをはかる','高さを測る')):
            r=app.correct_line(source,self.a.store,input_method='kana',dict_index=self.a.dict_index,decisions=self.a.decisions)
            self.assertEqual(r['corrected'],expected)
            self.assertFalse(r['odd_spans'])

    def test_unjudged_adjective_sense_and_bare_stem_do_not_gain_spelling(self):
        import kana_spelling as K
        for source,forbidden in (('あついおちゃをさましてからのみます。','厚い'),('がくせいでうす。','薄')):
            r=K.project(source,self.a.store,self.a.dict_index,self.a.decisions)
            self.assertNotIn(forbidden,r[0] if r else source)

    def test_mark_clusters_and_unknown_nouns_have_different_host_evidence(self):
        import reading_segments as R
        self.assertNotIn((0,3),R.native_adnominal_modifier_ranges('かたい゛゜に取り掛かる'))
        self.assertIn((0,5),R.native_adnominal_modifier_ranges('かんたんなぽねです。'))

    def test_potential_auxiliary_stays_bound_in_spelling(self):
        from ime_spelling import _reinterprets_function_attachment
        text='かみにかいておけます。'
        self.assertTrue(_reinterprets_function_attachment(text,6,8,'置け'))
        self.assertFalse(_reinterprets_function_attachment('箱におけます。',2,4,'置け'))

    @classmethod
    def setUpClass(cls):
        from tests_analysis_async import initial
        cls.a=initial();cls.a.context_vec=None
    @classmethod
    def tearDownClass(cls):
        from last_choice import set_active
        set_active(None)
    def run_line(self,text):
        import app
        return app.correct_line(text,self.a.store,dict_index=self.a.dict_index,
                                decisions=self.a.decisions,context_vec=None,input_method='kana')

    def test_complete_words_counts_focus_and_greetings_keep_their_meaning(self):
        pairs=[('ありがとうと言いました。','ありがとうと言いました。'),
               ('ありがとうございます','ありがとうございます'),('こんにちはという声がしました。','こんにちはという声がしました。'),
               ('やりがい','やりがい'),('およぎがいがあります。','およぎがいがあります。'),
               ('これはひなたです','これは日向です'),('けいたいそ','けいたいそ'),
               ('お待ちくださいませ','お待ちくださいませ'),
               ('ほんをにさつかいます。','本をにさつかいます。'),('りんごをみっつかいます。','リンゴをみっつかいます。'),
               ('さんさつめをよみます。','さんさつめをよみます。'),
               ('ほんをねんまつかいます。','本をねんまつかいます。'),('ほんをげつまつかいます。','本をげつまつかいます。'),
               ('かいてはみます。','かいてはみます。'),('かんがえてはけっします。','かんがえてはけっします。'),
               ('かいてはけしなます。','かいては消します。'),
               ('としょかんでかりたほんをかえします。','としょかんでかりたほんをかえします。'),
               ('おきやくさまにおちゃをだします。','お客様にお茶を出します。'),
               ('大きさをかえます。','大きさを変えます。')]
        for source,expected in pairs:
            with self.subTest(source=source):
                r=self.run_line(source);assert_reviewed_source_spelling(self, r['corrected'], expected)
                self.assertEqual(r.get('odd_spans'),[])

    def test_native_projection_changes_spelling_only(self):
        for source,output in [('ゆうせんしてほせい','優先して補正'),('ほかのぎょうとおなじ','他の行と同じ'),
                              ('😀4ばい','😀4倍'),('しゅうりょうが','終了が')]:
            self.assertTrue(M.native_spelling_only(source,output),(source,output))
        for source,output in [('用船して補正','優先して補正'),('1-2+3','2'),('つたえた','伝えない'),
                              ('もんじにゅうりょく','字入力'),('ゆうせん','優勢')]:
            self.assertFalse(M.native_spelling_only(source,output),(source,output))

    def test_original_kana_and_repaired_kana_use_their_own_readings(self):
        # 48-APK: 用船 is a valid unchanged action, not a typo of 優先.
        pairs=[('ようせんしてほせい','優先して補正'),('ゆうせんしてほせい','優先して補正'),
               ('きりがないようにも','キリがないようにも'),('にゅうりょくちゅう','入力中'),
               ('つたえたことで','伝えたことで'),('つたえふたことで','伝えたことで'),('のひっています','残っています'),
               ('のこっています','残っています'),('などにしたばあい','などにした場合'),
               ('4ばい','4倍'),('しゅうりょうが','終了が'),('もーしょん','モーション'),
               ('ほかのぎょうとおなじ','他の行と同じ'),('さしこみで、','差し込みで、')]
        for source,expected in pairs:
            with self.subTest(source=source):
                r=self.run_line(source+'\t');assert_reviewed_source_spelling(self,r['corrected'],expected+'\t')
                self.assertEqual(r.get('odd_spans'),[])

    def test_shared_prefix_usage_retains_choice_unknowns_and_common_gate(self):
        import corrector as C,kango_tier as K
        source='さいへんしゅうしたぶんしょう'
        r=self.run_line(source)
        self.assertEqual(r['corrected'],'再編集した文章')
        self.assertEqual(r['odd_spans'],[])
        self.assertEqual(r['analysis_status'],'complete')
        with patch.object(C,'_check_replacement',return_value=(None,'test_reject')):
            self.assertEqual(self.run_line(source)['corrected'],source)
        with patch('last_choice.surface_for_reading',side_effect=lambda rd:
                   '再編修' if rd=='さいへんしゅう' else None):
            self.assertEqual(self.run_line(source)['corrected'],'再編修した文章')
        for text in ('再編輯した文章','「さいへんしゅうしたぶんしょう」と入力しました。'):
            self.assertEqual(self.run_line(text)['corrected'],text)
        old=K.usage_tier_for_reading
        for tiers in ({'編集':1,'編修':1,'編輯':1},
                      {'編集':None,'編修':None,'編輯':None}):
            with patch.object(K,'usage_tier_for_reading',side_effect=lambda word,rd:
                              tiers[word] if word in tiers else old(word,rd)):
                self.assertNotIn('再編集',self.run_line(source)['corrected'])

    def test_restored_sahen_compound_keeps_whole_reading_without_native_row(self):
        for face,reading in (('再入力','さいにゅうりょく'),('再編集','さいへんしゅう')):
            with self.subTest(face=face):
                native=M.dictionary_inflections(face)
                self.assertFalse(native)
                self.assertEqual(M.native_sahen_compound_reading(face),reading)
                self.assertEqual(len(M.tokenize(face)),1)
                self.assertTrue(M.native_spelling_only(reading,face))
                self.assertTrue(M.native_spelling_only(reading+'した',face+'した'))
                self.assertFalse(M.native_spelling_only(reading[2:],face))
                self.assertFalse(M.native_spelling_only(reading+'した',face+'します'))
                self.assertEqual(M.dictionary_inflections(face),native)
        for face in ('各入力','再ぷねら','再食べ','再入力ぷねら'):
            with self.subTest(face=face):
                self.assertFalse(M.native_sahen_compound_reading(face))

    def test_restored_prefix_relative_requires_each_original_piece(self):
        from reading_segments import native_prefix_sahen_relative_parts,native_context_ranges
        for source,head,end,face in (
                ('さいにゅうりょくしたもじ',8,10,'再入力'),
                ('さいへんしゅうしたぶんしょう',7,9,'再編集')):
            with self.subTest(source=source):
                parts=native_prefix_sahen_relative_parts(source)
                self.assertTrue(any(a==head and b==end and face in faces
                                    for a,b,stem,faces in parts))
                self.assertIn((0,len(source)),native_context_ranges(source))
        for source in ('さいぷねらしたもじ','かくにゅうりょくしたもじ',
                       'さいにゅうりょくすたもじ','さいにゅうりょくしもじ',
                       'さいにゅうりょくしたぷねら','さいへんしゅうしたぷねら',
                       'さいにゅぅりょくしたもじ'):
            with self.subTest(source=source):
                self.assertFalse(native_prefix_sahen_relative_parts(source))
        # A one-kana reading can be a real complete noun. This proves
        # only the grammatical range, not its sense or a Shift repair.
        from reading_segments import native_nominal_phrase_faces
        self.assertIn('木',native_nominal_phrase_faces('き'))
        self.assertTrue(native_prefix_sahen_relative_parts('さいにゅうりょくしたき'))

    def test_restored_prefix_action_retains_literal_suru_and_final_gate(self):
        import corrector as C
        for source,expected in (
                ('さいにゅうりょくしたもじ','再入力した文字'),
                ('さいにゅぅりょくしたもじ','再入力した文字'),
                ('さいへんしゅうしたぶんしょう','再編集した文章')):
            with self.subTest(source=source):
                result=self.run_line(source)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result['odd_spans'])
                self.assertEqual(result['analysis_status'],'complete')
        source='さいにゅぅりょくしたもじ'
        with patch.object(C,'_check_replacement',return_value=(None,'forced_common_gate')):
            self.assertEqual(self.run_line(source)['corrected'],source)
        for source in ('「さいにゅぅりょくしたもじ」という文字列','各入力を確認します。'):
            self.assertEqual(self.run_line(source)['corrected'],source)

    def test_prefix_small_vowel_shares_whole_noun_and_final_key_validation(self):
        import corrector as C
        from small_vowel_repair import proposed_keys
        source='ごにゅぅりょくしたきー'
        self.assertIn('誤入力',R.native_attested_prefix_noun_faces('ごにゅうりょく'))
        self.assertNotIn('誤入力',R.native_nominal_spelling_faces('ごにゅうりょく'))
        check=C._check_replacement;seen=[]
        def reject(line,replacement,*args,**kw):
            seen.append((line,replacement))
            return None,'forced_common_gate'
        with patch.object(C,'_check_replacement',side_effect=reject):
            result=self.run_line(source)
        self.assertTrue(seen)
        self.assertEqual(result['corrected'],source)
        for text in ('さいぷねぅしたきー','ごにゅぅりょくしたぷねら',
                     'ゅからよへ変更します。','りゆうり','きゅぅっと'):
            with self.subTest(text=text):
                self.assertFalse(proposed_keys(text,self.a.store,self.a.dict_index,self.a.decisions))
        for text in ('「ごにゅぅりょくしたきー」という文字列',
                     '「ごにゅぅりょくしたきー」という入力'):
            with self.subTest(text=text):
                result=self.run_line(text)
                self.assertEqual(result['corrected'],text)
                self.assertFalse(result['odd_spans'])

    def test_small_vowel_same_key_needs_whole_word_evidence(self):
        from small_vowel_repair import proposed_keys

        source = 'ごにゅぅりょくしたきー'
        self.assertEqual(proposed_keys(source, self.a.store,
                         self.a.dict_index, self.a.decisions),
                         ((3,4,'う','かな入力'),))
        result = self.run_line(source + '\t')
        self.assertEqual(result['corrected'], '誤入力したキー\t')
        self.assertEqual(result.get('odd_spans'), [])
        self.assertEqual(result.get('original_spans'), [(0, 7), (9, 11)])
        self.assertEqual(result.get('spans'), [(0, 3), (5, 7)])
        for untouched in ('きゅぅん', 'きゅぅっと', 'にゅぅす',
                          'ごにゅぅりょくしたき'):
            with self.subTest(untouched=untouched):
                self.assertEqual(proposed_keys(untouched, self.a.store,
                                 self.a.dict_index, self.a.decisions), ())
        result = self.run_line(source + '\t別の入力欄')
        self.assertEqual(result['corrected'], '誤入力したキー\t別の入力欄')

    def test_ime_first_words_keep_source_meaning_and_expressive_voice(self):
        import sys
        if sys.platform!='win32':self.skipTest('Windows Japanese IME')
        from ime_language import JapaneseIME
        with JapaneseIME() as ime:
            if not ime.available:self.skipTest('Japanese IME unavailable')
        for source,expected in (
                ('じょうほうをきょうゆうします','情報を共有します'),
                ('しごとをしゅうりょうします','仕事を終了します'),
                ('がめんをきりかえます','画面を切り替えます'),
                ('こどもにえほんをよみます','子供に絵本を読みます'),
                ('ほんをとしょかんにかえします','本を図書館に返します'),
                ('本を図書館にかぇします','本を図書館に返します'),
                ('じょぅほうをきょうゆうします','情報を共有します'),
                ('しごとをしゅぅりょうします','仕事を終了します'),
                ('がめんをきりかぇます','画面を切り替えます'),
                ('こどもにぇほんをよみます','子供に絵本を読みます'),
                ('ほんをとしょかんにかぇします','本を図書館に返します'),
                ('ないようをかくにんします','内容を確認します')):
            with self.subTest(source=source):
                result=self.run_line(source+'\t')
                assert_reviewed_source_spelling(self,result['corrected'],expected+'\t')
                self.assertEqual(result.get('odd_spans'),[])
        for source in ('本を図書館に還します','猫がふぅっと息を吐く。',
                       '思わずふぅと息をついた','きゅぅん',
                       'ぶんしょうをにゅうりょくしないようをかくにんします。'):
            with self.subTest(keep=source):
                self.assertEqual(self.run_line(source)['corrected'],source)

    def test_closed_ime_first_keeps_original_grammar_and_meaning(self):
        import sys
        if sys.platform!='win32':self.skipTest('Windows Japanese IME')
        from ime_language import JapaneseIME
        with JapaneseIME() as ime:
            if not ime.available:self.skipTest('Japanese IME unavailable')
            for source,expected in (
                    ('しゅうりょうします','終了します'),
                    ('きょうゆうします','共有します'),
                    ('ほっかいどうにいきます','北海道に行きます'),
                    ('しょうひんをかいます','商品を買います'),
                    ('てぃっしゅをとります','ティッシュを取ります'),
                    ('でぃすぷれいをかくにんします','ディスプレイを確認します'),
                    ('ほんをとしょかんにかえします','本を図書館に返します')):
                with self.subTest(source=source):
                    result=self.run_line(source+'\t')
                    self.assertEqual(result['corrected'],expected+'\t')
                    self.assertEqual(result.get('odd_spans'),[])
            for source in ('しようひんをかいます','きようゆうします'):
                with self.subTest(missed_shift=source):
                    self.assertNotEqual(self.run_line(source+'\t')['corrected'],
                                        ime.convert(source)+'\t')
        for source in (
                'ぶんしょうをにゅうりょくしたますないようをかくにんします。',
                'がぞうのほぞんしてないようをかくにんします。'):
            with self.subTest(malformed=source):
                result=self.run_line(source+'\t')
                self.assertEqual(result['corrected'],source+'\t')
                self.assertTrue(result.get('odd_spans'))

    def test_original_continuative_clause_is_not_a_negative_attachment(self):
        # 48-APK: 入力し + 内容を確認 is a valid source-only continuation.
        source='ぶんしょうをにゅうりょくしないようをかくにんします'
        for ending in ('。', '\t'):
            with self.subTest(ending=ending):
                result=self.run_line(source+ending)
                self.assertEqual(result['corrected'],source+ending)
                self.assertEqual(result.get('odd_spans'),[])

    def test_shift_field_finishes_and_keeps_complete_source_words(self):
        import sys
        if sys.platform!='win32':self.skipTest('Windows Japanese IME')
        from ime_language import JapaneseIME
        with JapaneseIME() as ime:
            if not ime.available:self.skipTest('Japanese IME unavailable')
        for source,expected in (
                ('ちよつとまちます','ちょっと待ちます'),
                ('ていつしゆです','ティッシュです'),
                ('ていっしゅをとります','ティッシュを取ります'),
                ('でいすぷれいをかくにんします','ディスプレイを確認します'),
                ('しやしんをせんたくします','写真を選択します'),
                ('ほつかいどうにいきます','北海道に行きます'),
                ('きようゆうします','きようゆうします'),
                ('しようひんをかいます','しようひんをかいます'),
                ('ちよです','ちよです'),
                ('ちよはほんをよみます','ちよはほんを読みます')):
            with self.subTest(source=source):
                result=self.run_line(source+'\t')
                self.assertEqual(result['corrected'],expected+'\t')
                self.assertEqual(result.get('odd_spans'),[])
        source='ちよつとかえまそ'
        result=self.run_line(source+'\t')
        self.assertEqual(result['corrected'],source+'\t')
        self.assertTrue(result.get('odd_spans'))
        combined=self.run_line(source+'\tきょうゆうします\t')
        self.assertEqual(combined['corrected'],source+'\t共有します\t')
        self.assertTrue(combined.get('odd_spans'))

    def test_adverb_relative_source_seams_require_complete_sahen_noun(self):
        import kana_spelling as K
        for source in ('よくけんとうした方法','よくけんとうしたほうほう'):
            self.assertIn(2,R.native_adverbial_reading_cuts(source))
            proof=R.native_adverbial_sahen_relative_parts(source)
            self.assertEqual(proof[:3],(2,6,8))
            self.assertEqual(proof[3][-1][0],'方法')
            original=(R.native_written_adnominal_parts(source) if source.endswith('方法') else
                      R.native_adnominal_reading_parts(source,allow_predicative=True))
            self.assertEqual(original,proof[3])
            nouns=set();links={}
            units=K._lexical_units(source,M.tokenize(source),nouns,links)
            self.assertIn((2,6),units)
            self.assertIn((8,len(source)),nouns)
            self.assertEqual(links[(2,6)],8)
            self.assertFalse(any(a<edge<b for a,b in units for edge in (2,6,8)))
        for source in ('よくけんとうして方法','よくけんとうしますです方法',
                       'よくけんとうした商品','よくけんとうしたぷねら',
                       'よくけんとうした方法です','よくけんとうした\t方法',
                       '内容をよくけんとうした方法','ぷねらけんとうした方法',
                       'よくさいけんとうした方法'):
            self.assertFalse(R.native_adverbial_sahen_relative_parts(source),source)

    def test_adverb_relative_source_proofs_cannot_be_borrowed(self):
        import semantic_roles as S
        source='よくけんとうした方法';original=R.native_adverbial_sahen_relative_parts
        self.assertTrue(original(source))
        for name,value in (('native_adverbial_reading_cuts',()),
                           ('native_attributive_predicate_end',False),
                           ('_native_written_nominal_faces',()),
                           ('completed_sahen_reading',False),
                           ('native_relative_action',('健闘',('を',)))):
            with patch.object(R,name,return_value=value):self.assertFalse(original(source),name)
        with patch.object(M,'dictionary_inflections',return_value=()):
            self.assertFalse(original(source))
        with patch.object(S,'relative_action_support',return_value=False):
            self.assertFalse(original(source))
        real=R._native_written_nominal_faces
        with patch.object(R,'_native_written_nominal_faces',side_effect=lambda value:
                ('方法','ぷねら') if value=='方法' else real(value)):
            self.assertFalse(original(source))
        real=R.completed_sahen_reading
        with patch.object(R,'completed_sahen_reading',side_effect=lambda value,*a,**kw:
                '健闘' if kw.get('relative_faces') is not None else real(value,*a,**kw)):
            self.assertFalse(original(source))

    def test_adverb_relative_candidate_keeps_original_range_and_own_meaning(self):
        import kana_spelling as K
        source='よくけんとうした方法'
        proof=K._sahen_relative_spelling_evidence(source,2,6,'検討')
        self.assertEqual(proof,dict(predicate='検討',noun_start=8,noun_faces=('方法',),
                                   shared_roles=(('information',),)))
        self.assertEqual(R.native_relative_action(source[:8]),('健闘',()))
        written='よく検討した'
        self.assertEqual(R.native_written_relative_action(written),('検討',()))
        self.assertEqual(K._relative_object_spelling_evidence(written,'方法')['predicate'],'検討')
        original=R.native_written_relative_action.__wrapped__
        with patch.object(R,'native_adverbial_reading_cuts',return_value=()):
            self.assertFalse(original(written))
            self.assertIsNone(K._relative_object_spelling_evidence(written,'方法'))
        for text in ('ぷねら検討した','よく検討して','よく検討しますです',
                     'よく\t検討した'):
            self.assertFalse(R.native_written_relative_action(text),text)
        for noun in ('商品','ぷねら'):
            self.assertIsNone(K._relative_object_spelling_evidence(written,noun))
        self.assertIsNone(K._relative_object_spelling_evidence('よく内容を検討した','方法'))
        for face in ('健闘','見当','拳闘'):
            self.assertIsNone(K._sahen_relative_spelling_evidence(source,2,6,face))
        for start,end in ((0,6),(1,6),(2,5),(3,6)):
            self.assertIsNone(K._sahen_relative_spelling_evidence(source,start,end,'検討'))
        with patch.object(R,'native_adverbial_sahen_relative_parts',return_value=()):
            self.assertIsNone(K._sahen_relative_spelling_evidence(source,2,6,'検討'))
            units=K._lexical_units(source,M.tokenize(source),set(),{})
            self.assertNotIn((2,6),units)
        with patch.object(K,'_relative_object_spelling_evidence',return_value={
                'predicate':'健闘','case':'を','shared_roles':['information']}):
            self.assertIsNone(K._sahen_relative_spelling_evidence(source,2,6,'検討'))

    def test_adverb_relative_finishes_through_common_gate(self):
        import corrector as C
        for source in ('よくけんとうした方法','よくけんとうしたほうほう'):
            result=self.run_line(source)
            self.assertEqual(result['corrected'],'よく検討した方法')
            self.assertFalse(result['odd_spans'])
            self.assertEqual(result['analysis_status'],'complete')
            self.assertIn((2,6),result['original_spans'])
            with patch.object(C,'_check_replacement',return_value=(None,'test_reject')):
                denied=self.run_line(source)
                self.assertEqual(denied['corrected'],source)
                self.assertEqual(denied['analysis_status'],'complete')
        for source in ('よく検討した方法','よく健闘した選手',
                       '入力は「よくけんとうした方法」です。',
                       'よくけんとうした方法という文字列です。'):
            self.assertEqual(self.run_line(source)['corrected'],source)

    def test_written_relative_sahen_candidate_keeps_its_own_meaning(self):
        import kana_spelling as K
        source='けんとうした方法'
        proof=K._sahen_relative_spelling_evidence(source,0,4,'検討')
        self.assertEqual(proof['predicate'],'検討')
        self.assertEqual(proof['noun_start'],6)
        self.assertEqual(proof['noun_faces'],('方法',))
        self.assertEqual(proof['shared_roles'],(('information',),))
        self.assertEqual(R.native_relative_action(source[:6]),('健闘',()))
        for face in ('健闘','見当','拳闘'):
            self.assertIsNone(K._sahen_relative_spelling_evidence(source,0,4,face))
        for value in ('けんとうして方法','けんとうしますです方法','けんとうした商品',
                      'けんとうしたぷねら','けんとうした方法です','けんとうした\t方法',
                      '内容をけんとうした方法','さいけんとうした方法'):
            self.assertIsNone(K._sahen_relative_spelling_evidence(value,0,4,'検討'),value)

    def test_written_relative_sahen_requires_all_original_proofs(self):
        import kana_spelling as K,semantic_roles as S
        source='けんとうした方法'
        for name,value in (('_native_written_nominal_faces',()),
                           ('native_attributive_predicate_end',False),
                           ('completed_sahen_reading',False)):
            with patch.object(R,name,return_value=value):
                self.assertIsNone(K._sahen_relative_spelling_evidence(source,0,4,'検討'),name)
        real=R._native_written_nominal_faces
        def extra(text,*args,**kwargs):
            return ('方法','ぷねら') if text=='方法' else real(text,*args,**kwargs)
        with patch.object(R,'_native_written_nominal_faces',side_effect=extra):
            self.assertIsNone(K._sahen_relative_spelling_evidence(source,0,4,'検討'))
        with patch.object(S,'candidate_evidence',return_value=None):
            self.assertIsNone(K._sahen_relative_spelling_evidence(source,0,4,'検討'))
        with patch.object(K,'_relative_object_spelling_evidence',return_value={
                'predicate':'健闘','case':'を','shared_roles':['information']}):
            self.assertIsNone(K._sahen_relative_spelling_evidence(source,0,4,'検討'))
        with patch.object(M,'dictionary_inflections',return_value=()):
            self.assertIsNone(K._sahen_relative_spelling_evidence(source,0,4,'検討'))

    def test_written_relative_sahen_original_grammar_uses_conditioned_head(self):
        source='けんとうした方法'
        original=R.native_written_adnominal_parts.__wrapped__
        parts=original(source)
        self.assertEqual(parts[-1][0],'方法')
        self.assertEqual(parts[-1][4],'ほうほう')
        self.assertEqual(''.join(row[4] for row in parts[:-1]),source[:6])
        self.assertEqual(R.native_relative_action(source[:6]),('健闘',()))
        real=R.completed_sahen_reading
        def deny(text,*args,**kwargs):
            return False if kwargs.get('relative_faces') is not None else real(text,*args,**kwargs)
        with patch.object(R,'completed_sahen_reading',side_effect=deny):
            self.assertFalse(original(source))
        def wrong(text,*args,**kwargs):
            return '健闘' if kwargs.get('relative_faces') is not None else real(text,*args,**kwargs)
        with patch.object(R,'completed_sahen_reading',side_effect=wrong):
            self.assertFalse(original(source))
        with patch.object(R,'native_relative_action',return_value=('健闘',('を',))):
            self.assertFalse(original(source))
        with patch.object(R,'native_attributive_predicate_end',return_value=False):
            self.assertFalse(original(source))
        with patch.object(M,'dictionary_inflections',return_value=()):
            self.assertFalse(original(source))
        for value in ('けんとうして方法','けんとうしますです方法','けんとうした商品',
                      'けんとうしたぷねら','けんとうした方法です','けんとうした\t方法',
                      '内容をけんとうした方法','さいけんとうした方法'):
            self.assertFalse(original(value),value)

    def test_written_relative_sahen_finishes_through_common_gate(self):
        import kana_spelling as K,corrector as C
        for source,expected in (('けんとうした方法','検討した方法'),('けんとうした計画','検討した計画')):
            result=self.run_line(source)
            self.assertEqual(result['corrected'],expected)
            self.assertFalse(result['odd_spans'])
            self.assertEqual(result['analysis_status'],'complete')
        source='けんとうした方法'
        with patch.object(K,'_sahen_relative_spelling_evidence',return_value=None):
            self.assertEqual(self.run_line(source)['corrected'],source)
        with patch.object(C,'_check_replacement',return_value=(None,'test_reject')):
            self.assertEqual(self.run_line(source)['corrected'],source)
        for text in ('検討した方法','健闘した選手','さいけんとうした方法',
                     '入力は「けんとうした方法」です。','けんとうした方法という文字列です。'):
            self.assertEqual(self.run_line(text)['corrected'],text)

    def test_sahen_relative_source_grammar_binds_conditioned_action(self):
        text='けんとうしたほうほう'
        source_parts=R.native_adnominal_reading_parts.__wrapped__
        parts=source_parts(text,allow_predicative=True)
        self.assertEqual(parts[-1][0],'方法')
        self.assertEqual(''.join(p[4] for p in parts),text)
        self.assertEqual(R.native_relative_action(text[:6]),('健闘',()))
        real=R.completed_sahen_reading
        def deny(reading,*args,**kwargs):
            return False if kwargs.get('relative_faces') is not None else real(reading,*args,**kwargs)
        R.native_adnominal_reading_parts.cache_clear()
        try:
            with patch.object(R,'completed_sahen_reading',side_effect=deny):
                self.assertFalse(source_parts(text,allow_predicative=True))
        finally:R.native_adnominal_reading_parts.cache_clear()
        def other_head(reading,*args,**kwargs):
            return '健闘' if kwargs.get('relative_faces') is not None else real(reading,*args,**kwargs)
        try:
            with patch.object(R,'completed_sahen_reading',side_effect=other_head):
                self.assertFalse(source_parts(text,allow_predicative=True))
        finally:R.native_adnominal_reading_parts.cache_clear()
        for source in ('けんとうしてほうほう','けんとうしますですほうほう',
                       'けんとうしたぷねら','けんとうしたしょうひん',
                       'ないようをけんとうしたほうほう','けんとうした\tほうほう'):
            self.assertFalse(source_parts(source,allow_predicative=True),source)

    def test_sahen_relative_candidate_owns_original_noun_meaning(self):
        import kana_spelling as K
        text='けんとうしたほうほう'
        proof=K._sahen_relative_spelling_evidence(text,0,4,'検討')
        self.assertEqual(proof['predicate'],'検討')
        self.assertEqual(proof['noun_start'],6)
        self.assertEqual(proof['noun_faces'],('方法',))
        self.assertEqual(proof['shared_roles'],(('information',),))
        self.assertEqual(R.completed_sahen_reading(text[:6],allow_nonpolite=True,
                         return_action=True,finite_only=True),'健闘')
        for face in ('健闘','見当','拳闘'):
            self.assertIsNone(K._sahen_relative_spelling_evidence(text,0,4,face),face)
        # The original first-head and negative-attachment contracts retain
        # their identity binding; only this emitted candidate has the proof.
        self.assertIsNone(K._relative_object_spelling_evidence('けんとうした','方法'))
        for start,end in ((1,4),(0,3),(0,5)):
            self.assertIsNone(K._sahen_relative_spelling_evidence(text,start,end,'検討'))
        for value in ('けんとうしてほうほう','けんとうしますですほうほう',
                      'けんとうしたぷねら','けんとうしたしょうひん',
                      'けんとうしたほうほうです','けんとうした\tほうほう',
                      'けんとうしないようにします。','けんとうした',
                      'ないようをけんとうしたほうほう','さいけんとうしたほうほう'):
            self.assertIsNone(K._sahen_relative_spelling_evidence(value,0,4,'検討'),value)

    def test_sahen_relative_candidate_requires_every_source_and_meaning_proof(self):
        import kana_spelling as K,semantic_roles as S
        text='けんとうしたほうほう'
        for name,value in (('native_nominal_phrase_faces',()),
                           ('native_attributive_predicate_end',False),
                           ('completed_sahen_reading',False)):
            with patch.object(R,name,return_value=value):
                self.assertIsNone(K._sahen_relative_spelling_evidence(text,0,4,'検討'),name)
        real=R.native_nominal_phrase_faces
        def extra(reading,*args,**kwargs):
            return ('方法','ぷねら') if reading=='ほうほう' else real(reading,*args,**kwargs)
        with patch.object(R,'native_nominal_phrase_faces',side_effect=extra):
            self.assertIsNone(K._sahen_relative_spelling_evidence(text,0,4,'検討'))
        with patch.object(S,'candidate_evidence',return_value=None):
            self.assertIsNone(K._sahen_relative_spelling_evidence(text,0,4,'検討'))
        with patch.object(K,'_relative_object_spelling_evidence',return_value={
                'predicate':'健闘','case':'を','shared_roles':['information']}):
            self.assertIsNone(K._sahen_relative_spelling_evidence(text,0,4,'検討'))
        with patch.object(M,'dictionary_inflections',return_value=()):
            self.assertIsNone(K._sahen_relative_spelling_evidence(text,0,4,'検討'))

    def test_sahen_relative_candidate_finishes_through_common_gate(self):
        import kana_spelling as K,corrector as C
        source='けんとうしたほうほう'
        result=self.run_line(source)
        self.assertEqual(result['corrected'],'検討した方法')
        self.assertFalse(result['odd_spans'])
        self.assertEqual(result['analysis_status'],'complete')
        with patch.object(K,'_sahen_relative_spelling_evidence',return_value=None):
            self.assertEqual(self.run_line(source)['corrected'],source)
        with patch.object(C,'_check_replacement',return_value=(None,'test_reject')):
            self.assertEqual(self.run_line(source)['corrected'],source)
        for text in ('検討した方法','健闘した選手','さいけんとうしたほうほう',
                     'けんとうしないようにします。','入力は「けんとうしたほうほう」です。',
                     'けんとうしたほうほうという文字列です。'):
            self.assertEqual(self.run_line(text)['corrected'],text)

    def test_embedded_relative_subject_keeps_both_own_argument_relations(self):
        import kana_spelling as K,semantic_roles as S
        source='せんせいがせつめいしたないようを確認します'
        proof=K._relative_subject_spelling_evidence(source,0,4,'先生')
        self.assertEqual(proof['predicate'],'説明')
        self.assertEqual(proof['case'],'が');self.assertIn('person',proof['shared_roles'])
        for face in ('先制','宣誓','専制','せんせい','ぷねら'):
            self.assertIsNone(K._relative_subject_spelling_evidence(source,0,4,face),face)
        with patch.object(R,'native_object_predicate_proof',return_value=False):
            self.assertIsNone(K._relative_subject_spelling_evidence(source,0,4,'先生'))
        with patch.object(S,'candidate_nominal_spelling_evidence',return_value=None):
            self.assertIsNone(K._relative_subject_spelling_evidence(source,0,4,'先生'))
        actual=S.candidate_nominal_spelling_evidence
        with patch.object(S,'candidate_nominal_spelling_evidence',side_effect=lambda *a,**k:
                dict(actual(*a,**k),predicate='保存') if actual(*a,**k) else None):
            self.assertIsNone(K._relative_subject_spelling_evidence(source,0,4,'先生'))
        original=R.native_argument_relative_nominal_parts
        with patch.object(R,'native_argument_relative_nominal_parts',side_effect=lambda text:
                (11,('内容','ぷねら')) if text==source[:15] else original(text)):
            self.assertIsNone(K._relative_subject_spelling_evidence(source,0,4,'先生'))
        with patch.object(S,'proved_action_case_support',return_value=False):
            self.assertIsNone(K._relative_subject_spelling_evidence(source,0,4,'先生'))

    def test_embedded_relative_subject_requires_actual_outer_case(self):
        import copy,kana_spelling as K
        source='せんせいがせつめいしたないようを確認します';tokens=M.tokenize(source)
        index=next(i for i,t in enumerate(tokens) if t.surface=='を');actual=M.tokenize
        for field,value in (('reading','お'),('has_reading',False),('start',14),('end',17),
                            ('pos','名詞'),('pos_sub','接続助詞'),('base_form','お'),
                            ('surface','お'),('infl_form','基本形')):
            changed=copy.deepcopy(tokens);setattr(changed[index],field,value)
            with patch.object(M,'tokenize',side_effect=lambda text:
                    changed if text==source else actual(text)):
                self.assertIsNone(K._relative_subject_spelling_evidence(source,0,4,'先生'),field)
        dictionary=M.dictionary_inflections
        with patch.object(M,'dictionary_inflections',side_effect=lambda face:
                () if face=='を' else dictionary(face)):
            self.assertIsNone(K._relative_subject_spelling_evidence(source,0,4,'先生'))

    def test_embedded_relative_subject_seam_requires_complete_source(self):
        import kana_spelling as K
        source='せんせいがせつめいしたないようを確認します';members=set()
        units=K._lexical_units(source,M.tokenize(source),members)
        self.assertIn((0,4),units);self.assertIn((0,4),members)
        self.assertFalse(any(a<4<b or a<5<b for a,b in units))
        for text in ('せんせいが説明して内容を確認します',
                     'せんせいが説明しますです内容を確認します',
                     'せんせいが内容を説明した方法を確認します',
                     'せんせいが整理した内容を確認します',
                     'せんせいが説明したぷねらを確認します',
                     'せんせいが説明した内容を確認して',
                     'せんせいが説明した内容を確認しますです',
                     'せんせいが説明した内容を泳ぎます',
                     'せんせいが説明した内容\tを確認します'):
            self.assertIsNone(K._relative_subject_spelling_evidence(text,0,4,'先生'),text)
        self.assertIsNone(K._relative_subject_spelling_evidence(source,1,4,'先生'))

    def test_embedded_relative_subject_app_uses_common_gate(self):
        import corrector as C
        source='せんせいがせつめいしたないようを確認します。';calls=[];actual=C._check_replacement
        def seen(line,replacement,*args,**kwargs):
            ret=actual(line,replacement,*args,**kwargs);calls.append((replacement,ret));return ret
        with patch.object(C,'_check_replacement',side_effect=seen):result=self.run_line(source)
        self.assertEqual(result['corrected'],'先生が説明した内容を確認します。')
        self.assertIn((0,4),result['original_spans']);self.assertFalse(result['odd_spans'])
        self.assertEqual(result['analysis_status'],'complete')
        self.assertTrue(any(rep[2]=='先生' and ret[0] is not None for rep,ret in calls))
        def reject_subject(line,replacement,*args,**kwargs):
            return (None,'test_reject_subject') if replacement[2]=='先生' else actual(line,replacement,*args,**kwargs)
        with patch.object(C,'_check_replacement',side_effect=reject_subject):result=self.run_line(source)
        self.assertEqual(result['corrected'],'せんせいが説明した内容を確認します。')
        self.assertEqual(result['analysis_status'],'complete')
        self.assertEqual(self.run_line('せんせいがほうこくした内容を確認します。')['corrected'],
                         '先生が報告した内容を確認します。')
        for text in ('入力は「せんせいが説明した内容を確認します」です。',
                     'せんせいが説明した内容を確認しますという文字列です。'):
            self.assertEqual(self.run_line(text)['corrected'],text)

    def test_relative_subject_spelling_keeps_own_positive_case_meaning(self):
        import kana_spelling as K,semantic_roles as S
        for text,action in (('せんせいがせつめいしたほうほう','説明'),
                            ('せんせいがほうこくしたないよう','報告')):
            proof=K._relative_subject_spelling_evidence(text,0,4,'先生')
            self.assertEqual(proof['subject'],'先生');self.assertEqual(proof['case'],'が')
            self.assertEqual(proof['predicate'],action);self.assertIn('person',proof['shared_roles'])
            for face in ('先制','宣誓','専制','せんせい','ぷねら'):
                self.assertIsNone(K._relative_subject_spelling_evidence(text,0,4,face),face)
        source='せんせいがせつめいしたほうほう'
        with patch.object(R,'native_argument_relative_nominal_parts',return_value=()):
            self.assertIsNone(K._relative_subject_spelling_evidence(source,0,4,'先生'))
        with patch.object(R,'native_relative_action',return_value=('整理',('が',))):
            self.assertIsNone(K._relative_subject_spelling_evidence(source,0,4,'先生'))
        with patch.object(R,'native_relative_action',return_value=('説明',())):
            self.assertIsNone(K._relative_subject_spelling_evidence(source,0,4,'先生'))
        with patch.object(S,'proved_action_case_support',return_value=False):
            self.assertIsNone(K._relative_subject_spelling_evidence(source,0,4,'先生'))
        with patch.object(R,'native_nominal_phrase_faces',return_value=()):
            self.assertIsNone(K._relative_subject_spelling_evidence(source,0,4,'先生'))
        self.assertIsNone(K._relative_subject_spelling_evidence(source,1,4,'先生'))
        self.assertIsNone(K._relative_subject_spelling_evidence(source,0,3,'先生'))

    def test_relative_subject_case_uses_actual_original_token_and_dictionary(self):
        import copy,kana_spelling as K
        source='せんせいがせつめいしたほうほう';tokens=M.tokenize(source)
        original=R.native_argument_relative_nominal_parts(source)
        relative=R.native_relative_action(source[:original[0]])
        for field,value in (('reading','か'),('has_reading',False),('start',3),('end',6),
                            ('pos','名詞'),('pos_sub','接続助詞'),('base_form','か'),
                            ('surface','か'),('infl_form','基本形')):
            changed=copy.deepcopy(tokens);setattr(changed[1],field,value)
            self.assertEqual(tokens[1].surface,'が')
            with patch.object(R,'native_argument_relative_nominal_parts',return_value=original),\
                 patch.object(R,'native_relative_action',return_value=relative),\
                 patch.object(M,'tokenize',return_value=changed):
                self.assertIsNone(K._relative_subject_spelling_evidence(source,0,4,'先生'),field)
        actual=M.dictionary_inflections
        for omitted in ('が','先生'):
            with patch.object(M,'dictionary_inflections',side_effect=lambda face:
                    () if face==omitted else actual(face)):
                self.assertIsNone(K._relative_subject_spelling_evidence(source,0,4,'先生'),omitted)

    def test_relative_subject_original_seam_does_not_swallow_case(self):
        import kana_spelling as K
        source='せんせいがせつめいしたほうほう';members=set()
        units=K._lexical_units(source,M.tokenize(source),members)
        self.assertIn((0,4),units);self.assertIn((0,4),members)
        self.assertFalse(any(a<4<b or a<5<b for a,b in units))
        with patch.object(K,'_relative_subject_spelling_evidence',return_value=None):
            old=K._lexical_units(source,M.tokenize(source),set())
        self.assertIn((0,5),old)
        for text in ('せんせいが説明して','せんせいが説明しますです内容',
                     'せんせいが内容を説明した方法','せんせいが整理した内容',
                     'せんせいが説明したぷねら','せんせいが説明した\t内容'):
            self.assertIsNone(K._relative_subject_spelling_evidence(text,0,4,'先生'),text)
        self.assertIsNone(K._relative_subject_spelling_evidence('ぷねらが説明した内容',0,3,'先生'))

    def test_relative_subject_final_spelling_passes_common_gate(self):
        import corrector as C
        for source,expected in (('せんせいがせつめいしたほうほう','先生が説明した方法'),
                                ('せんせいがほうこくしたないよう','先生が報告した内容')):
            calls=[];original=C._check_replacement
            def checked(*args,**kwargs):
                result=original(*args,**kwargs);calls.append((args,kwargs,result));return result
            with patch.object(C,'_check_replacement',side_effect=checked):result=self.run_line(source)
            self.assertEqual(result['corrected'],expected)
            self.assertIn((0,4),result['original_spans']);self.assertFalse(result['odd_spans'])
            self.assertEqual(result['analysis_status'],'complete')
            self.assertTrue(any(len(args)>1 and args[1][2]=='先生' and value[0] is not None for args,kw,value in calls))
        with patch.object(C,'_check_replacement',return_value=(None,'test_reject')):
            result=self.run_line('せんせいがせつめいしたほうほう')
            self.assertEqual(result['corrected'],'せんせいがせつめいしたほうほう')
            self.assertEqual(result['analysis_status'],'complete')
        for text in ('先生が説明した内容','先制が大切です。',
                     '入力は「せんせいが説明した内容」です。',
                     'せんせいが説明した内容という文字列です。'):
            self.assertEqual(self.run_line(text)['corrected'],text)

    def test_argument_relative_tail_keeps_same_head_and_occupied_cases(self):
        import kana_spelling as K,semantic_roles as S
        for head in ('先生が説明した','せんせいがせつめいした'):
            source=(R.native_written_relative_action(head) if '先生' in head else
                    R.native_relative_action(head))
            self.assertEqual(source,('説明',('が',)))
            proof=R.native_argument_relative_object_evidence(head,'内容')
            self.assertEqual(proof['predicate'],'説明')
            self.assertEqual(proof['case'],'を');self.assertEqual(proof['shared_roles'],['information'])
            self.assertEqual(K._relative_object_spelling_evidence(head,'内容'),proof)
        for head in ('先生が内容を説明した','ぷねらが説明した','問題が説明した',
                     '先生が説明して','先生が説明しますです','先生が説明し',
                     '先生が説明した\t','説明した'):
            self.assertIsNone(R.native_argument_relative_object_evidence(head,'内容'),head)
        self.assertIsNone(R.native_argument_relative_object_evidence('先生が説明した','ぷねら'))
        with patch.object(S,'candidate_evidence',return_value=None):
            self.assertIsNone(R.native_argument_relative_object_evidence('先生が説明した','内容'))
        with patch.object(S,'candidate_evidence',return_value={
                'predicate':'確認','case':'を','shared_roles':['information']}):
            self.assertIsNone(R.native_argument_relative_object_evidence('先生が説明した','内容'))
        with patch.object(R,'native_written_relative_action',return_value=()):
            self.assertIsNone(R.native_argument_relative_object_evidence('先生が説明した','内容'))
        with patch.object(R,'_native_completed_action_suffix',return_value=''):
            self.assertIsNone(R.native_argument_relative_object_evidence('せんせいがせつめいした','内容'))
        with patch.object(M,'dictionary_inflections',return_value=()):
            self.assertIsNone(R.native_argument_relative_object_evidence('先生が説明した','内容'))

        with patch.object(R,'native_attributive_predicate_end',return_value=False):
            self.assertIsNone(R.native_argument_relative_object_evidence('先生が説明した','内容'))
        from copy import copy
        actual=M.tokenize
        for key,value in (('start',2),('end',6),('reading','かくにん'),('has_reading',False)):
            changed=[copy(t) for t in actual('先生が説明した')]
            token=next(t for t in changed if t.surface=='説明');setattr(token,key,value)
            with patch.object(M,'tokenize',side_effect=lambda text:
                    changed if text=='先生が説明した' else actual(text)):
                self.assertIsNone(R.native_argument_relative_object_evidence('先生が説明した','内容'),key)

    def test_argument_relative_source_range_requires_every_original_noun(self):
        source='先生が説明したないよう'
        self.assertEqual(R.native_argument_relative_nominal_parts(source),(7,('内容',)))
        self.assertIn((0,len(source)),R.native_context_ranges(source))
        with patch.object(R,'native_argument_relative_object_evidence',return_value=None):
            self.assertFalse(R.native_argument_relative_nominal_parts(source))
        original=R.native_nominal_phrase_faces
        with patch.object(R,'native_nominal_phrase_faces',side_effect=lambda text:
                ('内容','ぷねら') if text=='ないよう' else original(text)):
            self.assertFalse(R.native_argument_relative_nominal_parts(source))
        with patch.object(R,'native_nominal_phrase_faces',return_value=()):
            self.assertFalse(R.native_argument_relative_nominal_parts(source))
        for text in ('先生が説明したぷねら','先生が内容を説明したないよう',
                     'ぷねらが説明したないよう','問題が説明したないよう',
                     '先生が説明してないよう','先生が説明しますですないよう',
                     '先生が説明した\tないよう'):
            self.assertFalse(R.native_argument_relative_nominal_parts(text),text)

    def test_argument_relative_noun_keeps_true_negation_and_whole_source(self):
        import kana_spelling as K,ime_spelling as I
        source='先生が説明したないよう'
        self.assertFalse(I._crosses_negative_attachment(source,7,11))
        with patch.object(K,'_relative_object_spelling_evidence',return_value=None):
            self.assertTrue(I._crosses_negative_attachment(source,7,11))
        for text,start in (('先生が説明しないよう',6),('先生が説明してないよう',7),
                           ('先生が内容を説明したないよう',10),
                           ('問題が説明したないよう',7),('先生が説明した\tないよう',8)):
            self.assertTrue(I._crosses_negative_attachment(text,start,len(text)),text)
        self.assertTrue(I._crosses_negative_attachment(source+'です',7,11))

    def test_argument_relative_written_noun_finishes_through_common_gate(self):
        import corrector as C
        for source,expected in (('先生が説明したないよう','先生が説明した内容'),
                                ('先生が説明したほうほう','先生が説明した方法')):
            result=self.run_line(source)
            self.assertEqual(result['corrected'],expected)
            self.assertEqual(result['original_spans'],[(7,11)])
            self.assertFalse(result['odd_spans']);self.assertEqual(result['analysis_status'],'complete')
        with patch.object(C,'_check_replacement',return_value=(None,'test_reject')):
            result=self.run_line('先生が説明したないよう')
            self.assertEqual(result['corrected'],'先生が説明したないよう')
            self.assertEqual(result['analysis_status'],'complete')
        for text in ('先生が説明した内容','先生が説明しないようにします。',
                     '先生が内容を説明したないよう','問題が説明したないよう',
                     '入力は「先生が説明したないよう」です。',
                     '先生が説明したないようという文字列です。'):
            self.assertEqual(self.run_line(text)['corrected'],text)

    def test_relative_suru_meaning_uses_same_complete_original_predicate(self):
        import kana_spelling as K,semantic_roles as S
        for head in ('確認した','かくにんした','検討した'):
            proof=K._relative_object_spelling_evidence(head,'内容')
            self.assertTrue(proof and proof['shared_roles'],head)
            relative=R.native_relative_action(head) if head=='かくにんした' else R.native_written_relative_action(head)
            self.assertEqual(proof['predicate'],relative[0])
            self.assertIsNone(S.candidate_evidence('内容',relative[0],''))
        for head,noun in (('けんとうした','内容'),('さいけんとうした','内容'),
                          ('内容を確認した','内容'),('確認して','内容'),
                          ('確認しますです','内容'),('確認した','ぷねら')):
            self.assertIsNone(K._relative_object_spelling_evidence(head,noun),(head,noun))
        with patch.object(R,'native_written_relative_action',return_value=()):
            self.assertIsNone(K._relative_object_spelling_evidence('確認した','内容'))
        with patch.object(S,'candidate_evidence',return_value=None):
            self.assertIsNone(K._relative_object_spelling_evidence('確認した','内容'))
        with patch.object(S,'candidate_evidence',side_effect=[None,{'predicate':'別の動作','shared_roles':['information']}]):
            self.assertIsNone(K._relative_object_spelling_evidence('確認した','内容'))

    def test_relative_whole_noun_keeps_true_negative_and_source_proofs(self):
        import kana_spelling as K,ime_spelling as I
        source='確認したないよう'
        self.assertEqual(R.native_nominal_phrase_faces(source[4:]),('内容',))
        self.assertFalse(I._crosses_negative_attachment(source,4,8))
        with patch.object(K,'_relative_object_spelling_evidence',return_value=None):
            self.assertTrue(I._crosses_negative_attachment(source,4,8))
        with patch.object(R,'native_nominal_phrase_faces',return_value=()):
            self.assertTrue(I._crosses_negative_attachment(source,4,8))
        native_faces=R.native_nominal_phrase_faces
        with patch.object(R,'native_nominal_phrase_faces',side_effect=lambda text:
                ('内容','ぷねら') if text==source[4:] else native_faces(text)):
            self.assertTrue(I._crosses_negative_attachment(source,4,8))
        for text,start in (('確認しないよう',3),('確認してないよう',4),
                           ('内容を確認したないよう',7),('さいけんとうしたないよう',8),
                           ('けんとうしたないよう',6),('食べたないよう',3),
                           ('確認した\tないよう',5),('ないよう',0)):
            self.assertTrue(I._crosses_negative_attachment(text,start,len(text)),text)
        self.assertTrue(I._crosses_negative_attachment(source+'です',4,8))

    def test_relative_suru_noun_finishes_through_same_common_gate(self):
        import corrector as C,kana_spelling as K
        for source,expected in (('確認したないよう','確認した内容'),
                                ('かくにんしたないよう','確認した内容')):
            result=self.run_line(source)
            self.assertEqual(result['corrected'],expected)
            self.assertFalse(result['odd_spans']);self.assertEqual(result['analysis_status'],'complete')
        self.assertEqual(self.run_line('確認したないよう')['original_spans'],[(4,8)])
        for text in ('確認しないようにします。','確認してないようです。',
                     '内容を確認したないよう','さいけんとうしたないよう',
                     '入力は「確認したないよう」です。','確認したないようという文字列です。'):
            self.assertEqual(self.run_line(text)['corrected'],text)
        with patch.object(C,'_check_replacement',return_value=(None,'test_reject')):
            self.assertEqual(self.run_line('確認したないよう')['corrected'],'確認したないよう')
        with patch.object(K,'_relative_object_spelling_evidence',return_value=None):
            self.assertEqual(self.run_line('確認したないよう')['corrected'],'確認したないよう')

    def test_proved_relative_verb_keeps_its_whole_nominal_spelling(self):
        import kana_spelling as P
        for source,expected in (('とれるしゅだん','取れる手段'),
                                ('取れるしゅだん','取れる手段'),
                                ('つかえるほうほう','使える方法'),
                                ('使えるほうほう','使える方法')):
            with self.subTest(source=source):
                nominal=set();P._lexical_units(source,M.tokenize(source),nominal)
                self.assertTrue(nominal)
                result=self.run_line(source)
                self.assertEqual(result['corrected'],expected)
                self.assertEqual(result['odd_spans'],[])
                self.assertEqual(result['analysis_status'],'complete')
        result=self.run_line('取れるしゅだん\t無関係な答え')
        self.assertEqual(result['corrected'],'取れる手段\t無関係な答え')
        self.assertEqual(result['original_spans'],[(3,7)])

    def test_relative_spelling_requires_the_same_source_relation_and_gate(self):
        import kana_spelling as P,corrector as C
        for source in ('取れるぷねら','使えるぴむね','食べるしゅだん'):
            with self.subTest(source=source):
                nominal=set();P._lexical_units(source,M.tokenize(source),nominal)
                self.assertNotIn((3,len(source)),nominal)
        for source in ('取れるし、使えます。','「とれるしゅだん」と入力します。',
                       '「取れるしゅだん」と入力します。'):
            self.assertEqual(self.run_line(source)['corrected'],source)
        with patch.object(C,'_check_replacement',return_value=(None,'test_reject')):
            self.assertEqual(self.run_line('取れるしゅだん')['corrected'],'取れるしゅだん')

    def test_relative_potential_usage_keeps_occupied_case_and_explicit_choice(self):
        import kana_spelling as P,reading_segments as R
        relative=R.native_written_relative_action('資料を取れる')
        self.assertIsNotNone(relative)
        self.assertIn('を',relative[1])
        self.assertIsNone(P._relative_object_spelling_evidence('資料を取れる','手段'))
        with patch('last_choice.surface_for_reading',side_effect=lambda rd:'採れる' if rd=='とれる' else None):
            self.assertEqual(self.run_line('とれる手段')['corrected'],'採れる手段')

    def test_attested_compound_and_relative_noun_keep_independent_evidence(self):
        for source,expected in (
                ('ごにゅうりょくしたきー','誤入力したキー'),
                ('ごへんかんしたきー','誤変換したキー'),
                ('入力したきー','入力したキー'),
                ('入力するきー','入力するキー'),
                ('入力しているきー','入力しているキー'),
                ('保存したきー','保存したキー')):
            with self.subTest(source=source):
                result=self.run_line(source+'\t')
                self.assertEqual(result['corrected'],expected+'\t')
                self.assertEqual(result.get('odd_spans'),[])
        for source in ('入力したき','ご連絡した件','ご入力したキー','誤入力したキー'):
            with self.subTest(source=source):
                self.assertEqual(self.run_line(source)['corrected'],source)
        result=self.run_line('ごにゅうりょくしたきー\t無関係な答え')
        self.assertEqual(result['corrected'],'誤入力したキー\t無関係な答え')
        self.assertEqual(result.get('original_spans'),[(0,7),(9,11)])

    def test_unrelated_answer_column_cannot_supply_the_output(self):
        for annotation in ('用船','有線','無関係な文章','999999'):
            text='ゆうせんしてほせい\t'+annotation
            r=self.run_line(text)
            self.assertEqual(r['corrected'].split('\t')[0],'優先して補正')
        r=self.run_line('4ばい ⇒ 4ばい\t100倍')
        self.assertEqual(r['corrected'],'4倍 ⇒ 4倍\t100倍')

    def test_function_words_native_word_boundaries_and_explicit_choices_survive(self):
        for text in ('必要になりました。','かもしれません。','ではないでしょうか。',
                     'その後、向かいます。','なかなか進みません。','そういうことです。',
                     'ものをそのまま残す','もともとはとてもよいです。','きちんと片付けます。',
                     'うとうとしています。','やきもきしています。','たいてい大丈夫です。',
                     'よいはとてもよいです。','あとでそのままをおくります。',
                     '「もーしろょん」と入力します。','ほせいがきかない','薬がききます。','ほぞ'):
            with self.subTest(text=text):
                expected=text  # User preference: standalone もの stays kana.
                assert_reviewed_source_spelling(self, self.run_line(text)['corrected'], expected)
        assert_reviewed_source_spelling(self,self.run_line('おんがくをききます。')['corrected'],'音楽を聴きます。')
        self.assertEqual(self.run_line('しゃしんをえらんでほぞんします。')['corrected'],'写真を選んで保存します。')
        self.assertEqual(self.run_line('すべてのもの')['corrected'],'すべてのもの')
        from contextual_repair import key_repairs
        self.assertFalse(any(r.operation=='adjacent_intrusion' and r.reading=='もじにゅうりょく'
                             for r in key_repairs('もんじにゅうりょく')))
        from kana_spelling import finish
        import corrector as E
        tok=E.make_tokenizer(self.a.store)
        text='ゆうせんしてほせい'
        with patch('last_choice.surface_for_reading',side_effect=lambda rd:rd):
            self.assertEqual(finish(text,dict(corrected=text),self.a.store,tok,self.a.dict_index,self.a.decisions)['corrected'],text)
        with patch.object(E,'_check_replacement',return_value=(None,'blocked')):
            self.assertEqual(finish(text,dict(corrected=text),self.a.store,tok,self.a.dict_index,self.a.decisions)['corrected'],text)


    def test_user_reviewed_complete_spellings_and_retained_nonadjacent_key(self):
        # User-specified 2026-10-04 outputs; held examples 16/17 excluded.
        # Expected text is checked after the engine result, never supplied to it.
        import app
        from tests_analysis_async import initial
        a=initial();before=a.store.revision()
        cases=[('あたらしいしょるいをあつめいてかぞえます。', '新しい書類を集めて数えます。'), ('ぶんしょうをせんたくしてさくじょ', '文章を選択して削除'), ('まちがえたもじをけしてかきなおします。', '間違えた文字を消して書き直します。'), ('かいてじょうほうをほぞかします。', '書いて情報を保存します。'), ('わたしたちはほんをよみます。', '私達は本を読みます。'), ('あかいさらをしろれいたなにおきます。', '赤い皿をしろれいたなに置きます。'), ('ともだちとごはんをたべます。', '友達とご飯を食べます。'), ('ともだちににもつをはこんでもらいました。', '友達に荷物を運んでもらいました。'), ('ちゃわんにごはんをいれます。', '茶碗にご飯を入れます。'), ('なべにさかなをいれます。', '鍋に魚を入れます。'), ('まこつなを確認しました。', '小松菜を確認しました。'), ('手間をかけました。', '手間を掛けました。'), ('にもつをおわたしいたします。', '荷物をお渡しいたします。'), ('しょっきをあらってたなにもどします。', '食器を洗って棚に戻します。'), ('しょっきをあらってはたなにもどします。', '食器を洗っては棚に戻します。'), ('ふでをあらいます。', '筆を洗います。'), ('ぶらしをつかいます。', 'ブラシを使います。'), ('ぞうきんをほします。', '雑巾を干します。'), ('じしょをひらく。', '辞書を開く。'), ('さくいんをとじます。', '索引を閉じます。')]
        for source,expected in cases:
            with self.subTest(source=source):
                result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions)
                self.assertEqual(result['corrected'],expected)
                self.assertEqual(result['analysis_status'],'complete')
                if 'しろれい' in source:
                    self.assertTrue(result['odd_spans'])
                    self.assertNotIn('棚',result['corrected'])
                else:self.assertFalse(result['odd_spans'])
        self.assertEqual(a.store.revision(),before)

    def test_partial_spelling_cannot_split_unknown_owner_or_change_verb_reading(self):
        import semantic_owner_spelling as O,contextual_repair as Q
        unknown='赤い皿をしろれいたなにおきます'
        self.assertFalse(O._owner_boundary(unknown,8,10,'棚'))
        self.assertFalse(O.frames(unknown))
        self.assertTrue(O._owner_boundary('食器を洗ってたなに戻します',6,8,'棚'))
        self.assertTrue(Q.independently_spelled_object_verb(unknown,11,13,'置き'))
        self.assertFalse(Q.independently_spelled_object_verb(unknown,11,13,'起き'))
        self.assertFalse(Q.independently_spelled_object_verb(unknown,11,13,'置いて'))



# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch
import app,corrector,morphology as M,oddness
from tests_analysis_async import initial


@unittest.skipUnless(M.HAS_JANOME,'requires native Janome dictionary')
class UnclosedNativeSpellingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state=initial();cls.state.context_vec=None
    def line(self,source):
        s=self.state
        return app.correct_line(source,s.store,input_method='kana',dict_index=s.dict_index,
            decisions=s.decisions,context_vec=None)
    def test_source_action_sequence_proof_reaches_partial_spelling_and_purple(self):
        import reading_segments as R,ime_candidates
        with patch('ime_language._factory',None),patch.object(
                ime_candidates.SearchCandidates,'__enter__',lambda item:item):
            for source,expected in (('かくにんして送信しまし','確認して送信しまし'),
                    ('かいじょして削除します','解除して削除します')):
                with self.subTest(source=source):
                    self.assertIn((0,len(source)),R.native_context_ranges(source))
                    result=self.line(source)
                    self.assertEqual(result['corrected'],expected)
                    self.assertEqual(result['odd_spans'],[])
            for source in ('かくにんしてぷねらしまし','かくにんして送信しますまし',
                    'ぷねらして送信しまし','かくにんして送信し'):
                with self.subTest(source=source):
                    self.assertNotIn((0,len(source)),R.native_context_ranges(source))
                    self.assertFalse(R.completed_native_action_note(source))
            source='かくにんして送信しまし\tぷねら'
            self.assertFalse(any(a<=source.index('ぷねら')<b for a,b in R.native_context_ranges(source)))

    def test_action_sequence_reuses_the_actual_following_predicate(self):
        import reading_segments as R
        for source in ('補正しまし','ほせいしまし','補正します','ほせいします'):
            with self.subTest(source=source):
                self.assertEqual(R.native_source_action_heads(source),('補正',))
                self.assertEqual(R._native_action_note_heads('ゆうせんして'+source,
                    allow_predicate=True),('優先',))
        # Source-only open evidence must not claim a completed note or clause.
        self.assertFalse(R.native_written_relative_action('補正しまし',allow_finite=True))
        self.assertFalse(R.completed_native_action_note('ゆうせんしてほせいしまし'))
        for source in ('補正し','ほせいし','補正しますまし','ほせいしましま','ぷねらしまし'):
            with self.subTest(source=source):
                self.assertEqual(R.native_source_action_heads(source),())

    def test_mixed_action_spelling_still_needs_the_common_final_check(self):
        import kana_spelling as K,ime_candidates
        state=self.state
        with patch('ime_language._factory',None),patch.object(
                ime_candidates.SearchCandidates,'__enter__',lambda item:item):
            for source,expected in (
                    ('ゆうせんして補正しまし','優先して補正しまし'),
                    ('ゆうせんしてほせいしまし','優先して補正しまし'),
                    ('ゆうせんして補正します','優先して補正します')):
                with self.subTest(source=source):
                    result=self.line(source)
                    self.assertEqual(result['corrected'],expected)
                    self.assertEqual(result['odd_spans'],[])
            source='ゆうせんして補正しまし'
            with patch.object(corrector,'_check_replacement',return_value=(None,'blocked')):
                self.assertIsNone(K.project(source,state.store,state.dict_index,state.decisions))
            for source in ('優先して補正しまし','「ゆうせんして補正しまし」という文字列をコピーします。'):
                self.assertEqual(self.line(source)['corrected'],source)

    def test_open_object_spelling_uses_the_same_source_tail_and_meaning(self):
        import contextual_repair as Q,reading_segments as R
        state=self.state;tok=corrector.make_tokenizer(state.store)
        for source,expected in (('資料をせいりしまし','資料を整理しまし'),
                ('図面をしゅうせいしまし','図面を修正しまし'),
                ('動画をへんしゅうしまし','動画を編集しまし')):
            with self.subTest(source=source):
                end=source.index('しまし');face=expected[3:-3]
                self.assertTrue(Q.independently_spelled_object_verb(source,3,end,face))
                self.assertFalse(R.native_object_predicate_proof(expected,3,(source[:2],)))
                for start,stop,surface in ((3,end,face),(0,len(source),expected)):
                    checked,reason=corrector._check_replacement(source,(start,stop,surface,'かな入力'),
                        state.store,tok,state.dict_index,state.decisions,conv_taken=((start,stop),),spelling=True)
                    self.assertIsNotNone(checked,reason)
                self.assertFalse(Q._object_predicate_candidate_fits(source,expected,3,(source[:2],)))
                self.assertTrue(Q._object_predicate_candidate_fits(source,expected,3,(source[:2],),spelling=True))

    def test_open_spelling_does_not_certify_other_tails_or_unknown_arguments(self):
        import contextual_repair as Q
        for source,changed in (('資料をせいりし','資料を整理し'),
                ('資料をせいりしましま','資料を整理しましま'),
                ('資料をせいりしましん','資料を整理しましん'),
                ('資料をせいりしまし','資料を整理しました'),
                ('資料をせいりしまし','資料を生理しまし'),
                ('資料をせいりしまし','資料を送信しまし'),
                ('石をそうしんしまし','石を送信しまし'),
                ('ぷねらをせいりしまし','ぷねらを整理しまし')):
            with self.subTest(source=source,changed=changed):
                cut=source.index('を')+1
                self.assertFalse(Q._same_reading_open_object_spelling(source,changed,cut,(source[:cut-1],)))

    def test_open_object_heads_reach_the_application_without_reading_the_answer(self):
        import kana_spelling as K,ime_candidates
        with patch('ime_language._factory',None),patch.object(
                ime_candidates.SearchCandidates,'__enter__',lambda item:item):
            for source,expected in (('資料をせいりしまし','資料を整理しまし'),
                    ('図面をしゅうせいしまし','図面を修正しまし'),
                    ('動画をへんしゅうしまし','動画を編集しまし')):
                with self.subTest(source=source):
                    result=self.line(source)
                    self.assertEqual(result['corrected'],expected)
                    self.assertEqual(result['odd_spans'],[])
                    self.assertEqual(result['analysis_status'],'complete')
            source='動画をへんしゅうしまし'
            with patch.object(corrector,'_check_replacement',return_value=(None,'blocked')):
                self.assertIsNone(K.project(source,self.state.store,self.state.dict_index,self.state.decisions))
            with patch('last_choice.surface_for_reading',side_effect=lambda reading:reading):
                self.assertIsNone(K.project(source,self.state.store,self.state.dict_index,self.state.decisions))
            for source in ('資料を整理しまし','図面を修正しまし','動画を編集しまし',
                    '「動画をへんしゅうしまし」という文字列をコピーします。'):
                self.assertEqual(self.line(source)['corrected'],source)

    def test_open_sahen_spelling_keeps_the_actual_unfinished_tail(self):
        import kana_spelling as K,ime_candidates
        state=self.state
        with patch('ime_language._factory',None),patch.object(
                ime_candidates.SearchCandidates,'__enter__',lambda item:item):
            result=self.line('ほせいしまし')
            self.assertEqual(result['corrected'],'補正しまし')
            self.assertEqual(result['odd_spans'],[])
            for source in ('ほせいしましま','ほせいしましん','ほせいしま'):
                with self.subTest(source=source):
                    self.assertIsNone(K.project(source,state.store,state.dict_index,state.decisions))
            source='「ほせいしまし」という文字列をコピーします。'
            self.assertEqual(self.line(source)['corrected'],source)

    def test_focus_particle_keeps_nominal_spelling_separate(self):
        import ime_candidates,kana_spelling as K
        with patch('ime_language._factory',None),patch.object(
                ime_candidates.SearchCandidates,'__enter__',lambda item:item):
            for source,expected in (('このほんだけを読めます。','この本だけを読めます。'),
                    ('そのしりょうなどを読みます。','その資料などを読みます。')):
                with self.subTest(source=source):
                    result=self.line(source)
                    self.assertEqual(result['corrected'],expected)
                    self.assertEqual(result['odd_spans'],[])
                    self.assertEqual(result['analysis_status'],'complete')
                    with patch('corrector._check_replacement',return_value=(None,'test_rejection')):
                        self.assertIsNone(K.project(source,self.state.store,self.state.dict_index,self.state.decisions))
            for source in ('ぷねらだけを読みます。','本だけを読めます。',
                    '「このほんだけを読めます。」という文字列'):
                self.assertEqual(self.line(source)['corrected'],source)

    def test_action_boundary_recovers_suru_hidden_in_best_parse(self):
        import kana_spelling as K,ime_candidates
        state=self.state
        with patch('ime_language._factory',None),patch.object(
                ime_candidates.SearchCandidates,'__enter__',lambda item:item):
            for source,expected in (('動画をさいせいしまし','動画を再生しまし'),
                    ('文章をほんやくしまし','文章を翻訳しまし')):
                with self.subTest(source=source):
                    result=self.line(source)
                    self.assertEqual(result['corrected'],expected)
                    self.assertEqual(result['odd_spans'],[])
                    with patch('corrector._check_replacement',return_value=(None,'test_rejection')):
                        self.assertIsNone(K.project(source,state.store,state.dict_index,state.decisions))
            for text in ('動画を再生しまし','文章を翻訳しまし','本訳詩の資料です。',
                    '「文章をほんやくしまし」という文字列をコピーします。'):
                self.assertEqual(self.line(text)['corrected'],text)
            for text in ('ぷねらしまし','ほんやくしましん','ほんやくしませんた',
                    '岩をほんやくしまし','文章をほんやくし'):
                self.assertIsNone(K.project(text,state.store,state.dict_index,state.decisions))

    def test_native_suru_tail_prevents_a_generated_prefix_noun_crossing(self):
        import kana_spelling as K,ime_candidates
        state=self.state
        with patch('ime_language._factory',None),patch.object(
                ime_candidates.SearchCandidates,'__enter__',lambda item:item):
            source='部品をこうかんしまし'
            result=self.line(source)
            self.assertEqual(result['corrected'],'部品を交換しまし')
            self.assertEqual(result['odd_spans'],[])
            # A surviving lexical candidate still needs the same final gate.
            with patch('corrector._check_replacement',return_value=(None,'test_rejection')):
                self.assertIsNone(K.project(source,state.store,state.dict_index,state.decisions))
            for text in ('副製紙工場の資料です。','後監視の資料です。','部品を交換しました。',
                    '「部品をこうかんしまし」という文字列をコピーします。'):
                self.assertEqual(self.line(text)['corrected'],text)
            for text in ('ぷねらしまし','こうかんしましん','こうかんしませんた'):
                self.assertIsNone(K.project(text,state.store,state.dict_index,state.decisions))

    def test_reopened_case_keeps_each_coordinated_nominal_boundary(self):
        import kana_spelling as K,ime_candidates
        for source,spans in (('ともだちとごはんをたべます。',((0,4),(5,8))),
                ('ぬのとかみをこまかくきります。',((0,2),(3,5))),
                ('かみとぬのをこまかくきります。',((0,2),(3,5)))):
            with self.subTest(source=source):
                members=set();units=K._lexical_units(source,M.tokenize(source),members)
                self.assertTrue(set(spans)<=members)
                self.assertNotIn((0,spans[-1][1]),units)
        with patch('ime_language._factory',None),patch.object(
                ime_candidates.SearchCandidates,'__enter__',lambda item:item):
            for source,expected in (
                    ('ともだちとごはんをたべます。','友達とご飯を食べます。'),
                    ('ぬのとかみをこまかくきくります。','布と紙をこまかく切ります。'),
                    ('かみとぬのをこまかくきくります。','紙と布をこまかく切ります。')):
                result=self.line(source)
                self.assertEqual(result['corrected'],expected)
                self.assertEqual(result['odd_spans'],[])
            for source in ('友達とご飯を食べます。','布と髪を切ります。','神と仏を信じます。',
                    '「ともだちとごはんをたべます。」という文字列をコピーします。'):
                self.assertEqual(self.line(source)['corrected'],source)

    def test_reopened_noun_case_does_not_hide_a_native_verb_link(self):
        import kana_spelling as K,ime_candidates
        with patch('ime_language._factory',None),patch.object(
                ime_candidates.SearchCandidates,'__enter__',lambda item:item):
            for source,expected in (
                    ('かおりをかいでちしきをえます。','香りを嗅いで知識をえます。'),
                    ('においをかいでもみます。','匂いを嗅いでもみます。'),
                    ('香りをかいでちしきをえます。','香りを嗅いで知識をえます。'),
                    ('匂いをかいでもみます。','匂いを嗅いでもみます。')):
                with self.subTest(source=source):
                    members=set();K._lexical_units(source,M.tokenize(source),members)
                    start=source.index('かいで')
                    self.assertNotIn((start,start+2),members)
                    result=self.line(source)
                    self.assertEqual(result['corrected'],expected)
                    self.assertEqual(result['odd_spans'],[])
            for source in ('貝で飾ります。','海で遊びます。','匂いを嗅いでもみます。',
                    '「かおりをかいでちしきをえます。」という文字列をコピーします。'):
                self.assertEqual(self.line(source)['corrected'],source)

    def test_source_case_and_meaning_recover_a_kana_nominal_before_de(self):
        import kana_spelling as K,ime_candidates
        with patch('ime_language._factory',None),patch.object(
                ime_candidates.SearchCandidates,'__enter__',lambda item:item):
            for source,expected in (
                    ('めーるで送ります。','メールで送ります。'),
                    ('会議の資料をめーるで送ります。','会議の資料をメールで送ります。')):
                with self.subTest(source=source):
                    result=self.line(source)
                    self.assertEqual(result['corrected'],expected)
                    self.assertEqual(result['odd_spans'],[])
            # A nominal reading alone cannot certify an unrelated copular
            # or unknown continuation as that noun's instrumental case.
            for source in ('めーるで寝ます。','めーるでぷねら'):
                members=set()
                K._lexical_units(source,M.tokenize(source),members)
                self.assertNotIn((0,3),members,source)
            self.assertEqual(self.line('めーるでした。')['corrected'],'メールでした。')
            for source in ('そのままで送ります。','それで送ります。',
                    '「めーるで送ります。」という文字列をコピーします。'):
                self.assertEqual(self.line(source)['corrected'],source)

    def test_image_inputs_are_independent_and_finish_in_written_form(self):
        for source in ('入力茶う','にゅうりょくちゃう','にゅうりょくちゅう'):
            with self.subTest(source=source):
                result=self.line(source)
                self.assertEqual(result['corrected'],'入力中')
                self.assertEqual(result['odd_spans'],[])
    def test_source_line_end_does_not_become_a_fragment_boundary(self):
        source='入力茶う';parts=corrector.make_tokenizer(self.state.store)(source)
        a,b=parts[-2:]
        self.assertFalse(oddness.closed_nominal_volitional_mismatch(source,a,b))
        self.assertTrue(oddness.closed_nominal_volitional_mismatch(source,a,b,allow_line_end=True))
    def test_native_spelling_does_not_require_an_answer_field(self):
        for source,expected in (('ゆうせんしてほせい','優先して補正'),
                ('4ばい','4倍'),('もじにゅうりょく','文字入力'),('ほぞんちゅう','保存中')):
            with self.subTest(source=source):
                r=self.line(source);self.assertEqual(r['corrected'],expected)
                self.assertEqual(r['odd_spans'],[])
    def test_later_noun_is_not_split_after_an_earlier_spelling(self):
        for source,expected in (
                ('ないようをかくにんしてがぞうをほぞんします。','内容を確認して画像を保存します。'),
                ('かくにんしてがぞうをほぞんします。','確認して画像を保存します。')):
            with self.subTest(source=source):
                r=self.line(source);self.assertEqual(r['corrected'],expected)
                self.assertEqual(r['odd_spans'],[])
    def test_written_object_and_following_clause_each_supply_their_own_proof(self):
        for text,expected in (
                ('内容をかくにんしてがぞうをほぞんします。','内容を確認して画像を保存します。'),
                ('資料をせいりしてがぞうをほぞんします。','資料を整理して画像を保存します。')):
            with self.subTest(text=text):
                r=self.line(text);self.assertEqual(r['corrected'],expected)
                self.assertEqual(r['odd_spans'],[])
    def test_first_clause_cannot_certify_an_unfinished_or_conflicting_tail(self):
        import reading_segments as R
        for text in ('内容をかくにんしてがぞう','内容をかくにんしてぷねらします',
                     '内容をかくにんしてがぞうのほぞんします',
                     '日程を送電してがぞうをほぞんします'):
            with self.subTest(text=text):
                self.assertNotIn((0,len(text)),R.native_context_ranges(text))
    def test_explicit_kana_choice_and_literal_example_are_kept(self):
        text='にゅうりょくちゅう'
        with patch('last_choice.surface_for_reading',side_effect=lambda rd:rd):
            self.assertEqual(self.line(text)['corrected'],text)
        text='文字列「にゅうりょくちゅう」'
        self.assertEqual(self.line(text)['corrected'],text)
    def test_first_ime_partial_word_does_not_supply_bare_source_meaning(self):
        text='かんりょうちゅう'
        r=self.line(text);self.assertEqual(r['corrected'],text)
        self.assertEqual(r['odd_spans'],[])
    def test_native_colloquial_form_and_unresolved_source_keep_their_state(self):
        for text in ('入力ちゃう。','入力しちゃう。','お茶を飲もう。','会社に行こう。'):
            with self.subTest(text=text):
                r=self.line(text);self.assertEqual(r['corrected'],text)
                self.assertEqual(r['odd_spans'],[])
        text='ぷねらちゅう';r=self.line(text)
        self.assertEqual(r['corrected'],text);self.assertTrue(r['odd_spans'])

    def test_native_grammar_does_not_become_a_content_homophone(self):
        for text in ('増すことで解決','自然であること','ページを閉じまい',
                     '画像を保存するまい','こさせます','はわはわ',
                     'みんな下がれい。','下がれい'):
            with self.subTest(text=text):
                r=self.line(text);self.assertEqual(r['corrected'],text)
                self.assertEqual(r['odd_spans'],[])
    def test_actual_following_activity_ranks_the_same_reading_sense(self):
        for source,expected in (('すいこうしててんさく','推敲して添削'),
                ('こうせいしててんさく','校正して添削'),
                ('遂行して添削','遂行して添削'),('構成して添削','構成して添削')):
            with self.subTest(source=source):
                r=self.line(source);self.assertEqual(r['corrected'],expected)
                self.assertEqual(r['odd_spans'],[])

    def test_whole_native_action_finishes_before_a_following_clause(self):
        for source,expected in (
                ('設定をへんこうして画面を開きます。','設定を変更して画面を開きます。'),
                ('せっていをへんこうしてしりょうをほぞんします。','設定を変更して資料を保存します。'),
                ('へんこうして画面を開きます。','変更して画面を開きます。')):
            with self.subTest(source=source):
                r=self.line(source);self.assertEqual(r['corrected'],expected)
                self.assertEqual(r['odd_spans'],[])
    def test_real_conjunction_and_literal_action_remain_their_own_words(self):
        for source in ('こうして画面を開きます。','設定をこうして画面を開きます。',
                       'そうして資料を保存します。','そして画面を開きます。',
                       '文字列「へんこうして」'):
            with self.subTest(source=source):
                r=self.line(source);self.assertEqual(r['corrected'],source)
                self.assertEqual(r['odd_spans'],[])

    def test_action_and_following_object_finish_even_when_the_source_split_crosses_them(self):
        for source,expected in (
                ('しりょうをせいりしてよていをかくにんします。','資料を整理して予定を確認します。'),
                ('資料をせいりしてよていを確認します。','資料を整理して予定を確認します。'),
                ('がぞうをほぞんしてないようをかくにんします。','画像を保存して内容を確認します。')):
            with self.subTest(source=source):
                r=self.line(source);self.assertEqual(r['corrected'],expected)
                self.assertEqual(r['odd_spans'],[])
    def test_lexical_seam_does_not_certify_an_unknown_source_tail(self):
        source='資料をせいりしてぷねらを確認します。'
        # 2026-10-04: independently proved ordinary spelling can finish;
        # the unknown argument remains verbatim and keeps its anomaly.
        r=self.line(source);self.assertEqual(r['corrected'],'資料を整理してぷねらを確認します。')
        self.assertTrue(r['odd_spans'])
        for source in ('もんだいがかいけつし','文字列「せいりしてよてい」'):
            with self.subTest(source=source):
                r=self.line(source);self.assertEqual(r['corrected'],source)
                self.assertEqual(r['odd_spans'],[])

    def test_action_head_beats_longer_noun_only_with_source_argument(self):
        cases=(
            ('文章をせんたくして削除','文章を選択して削除'),
            ('衣服をせんたくして干します。','衣服を洗濯して干します。'),
            ('資料をせんたくして保存します。','資料を選択して保存します。'),
            ('せんたくしてかんそう','せんたくしてかんそう'),
            ('候補をせんたくして決めます。','候補をせんたくして決めます。'),
        )
        for source,expected in cases:
            with self.subTest(source=source):
                r=self.line(source)
                self.assertEqual(r['corrected'],expected)
                self.assertEqual(r['odd_spans'],[])

    def test_explicit_action_spelling_still_beats_automatic_role(self):
        def remembered(reading):return '洗濯' if reading=='せんたく' else None
        with patch('last_choice.surface_for_reading',side_effect=remembered):
            r=self.line('文章をせんたくして削除')
        self.assertEqual(r['corrected'],'文章を洗濯して削除')

    def test_proved_action_link_does_not_protect_a_crossing_conjunction(self):
        cases=(
            ('入力してかくにん','入力して確認'),
            ('にゅうりょくしてかくにん','入力して確認'),
            ('実行してかくにん','実行して確認'),
            ('文章を入力してかくにん','文章を入力して確認'),
            ('保存してから','保存してから'),
            ('「てか」を確認','「てか」を確認'),
            ('入力してかえる','入力してかえる'),
            ('入力してかう','入力して買う'),
        )
        for source,expected in cases:
            with self.subTest(source=source):
                r=self.line(source)
                self.assertEqual(r['corrected'],expected)
                self.assertEqual(r['odd_spans'],[])

    def test_unfinished_native_sahen_is_not_split_into_another_verb(self):
        source='もんだいがかいけつし'
        r=self.line(source);self.assertEqual(r['corrected'],source)
        self.assertEqual(r['odd_spans'],[])

    def test_written_object_and_native_kana_action_note_keep_the_source_reading(self):
        cases=(
            ('文章をにゅうりょくしてかくにんしてほぞん',
             '文章を入力して確認して保存'),
            ('資料をにゅうりょくしてかくにん','資料を入力して確認'),
            ('文章をそうじしてかんそう','文章をそうじしてかんそう'),
            ('文章をにゅうりょくして確認します。',
             '文章を入力して確認します。'),
        )
        for source,expected in cases:
            with self.subTest(source=source):
                r=self.line(source)
                self.assertEqual(r['corrected'],expected)
                if source==cases[0][0]:
                    self.assertEqual(r['odd_spans'],[])
                    self.assertEqual(r['original_spans'],[(3,9),(11,15),(17,20)])

    def test_written_object_and_native_finite_action_keep_source_reading(self):
        for text,expected in (
                ('文章をにゅうりょくして確認します。','文章を入力して確認します。'),
                ('文章をにゅうりょくして確定します。','文章を入力して確定します。'),
                ('文章をにゅうりょくしてほぞんします。','文章を入力して保存します。'),
                # Ordinary quotation is correctable; explicit spelling
                # mentions retain the existing literal_examples protection.
                ('「文章をにゅうりょくして確認します。」',
                 '「文章を入力して確認します。」'),
                ('文字列「文章をにゅうりょくして確認します。」',
                 '文字列「文章をにゅうりょくして確認します。」')):
            with self.subTest(text=text):
                r=self.line(text)
                self.assertEqual(r['corrected'],expected)
                if text.startswith('文章を'):
                    self.assertEqual(r['odd_spans'],[])

    def test_native_source_spelling_respects_whole_line_rejection(self):
        for source,finished in (
                ('文章をにゅうりょくして確認します。','文章を入力して確認します。'),
                ('文章をにゅうりょくしてかくにんしてほぞん',
                 '文章を入力して確認して保存')):
            with self.subTest(source=source):
                state=initial();state.context_vec=None
                state.decisions.reject(source,finished)
                r=app.correct_line(source,state.store,input_method='kana',
                    dict_index=state.dict_index,decisions=state.decisions,
                    context_vec=None)
                self.assertEqual(r['corrected'],source)

if __name__=='__main__':unittest.main()