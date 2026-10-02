# -*- coding: utf-8 -*-
"""Accepted reading repairs gain native written forms, without wider rewriting."""
import unittest
from unittest.mock import patch

class RepairedSpellingFrameTests(unittest.TestCase):
    def test_trimmed_edit_recovers_only_the_surviving_lexical_frame(self):
        import corrector as E
        from repaired_spelling import retained_frames
        source='しゅうありょうが'
        legacy=dict(corrected='しゅうりょうが',original_spans=[(0,7)],spans=[(0,6)])
        self.assertEqual(retained_frames(source,legacy,[(3,4,'')],[],E),[(0,7,'しゅうりょう','')])
        self.assertEqual(retained_frames(source,legacy,[],[],E),[])
        self.assertEqual(retained_frames(source,legacy,[(3,4,'')],[(0,3,'別')],E),[(3,4,'','')])
        self.assertEqual(retained_frames(source,legacy,[(3,4,'い')],[],E),[(3,4,'い','')])

class RepairedSpellingNativeTests(unittest.TestCase):
    def test_initial_states_finish_accepted_repairs_and_original_readings(self):
        import app
        from tests_analysis_async import initial
        from janome_import import import_from_janome
        from last_choice import set_active
        for phase in ('seed','fresh'):
            a=initial();a.context_vec=None
            if phase=='fresh':import_from_janome(a.store)
            revision=a.store.revision()
            def run(text):return app.correct_line(text,a.store,dict_index=a.dict_index,decisions=a.decisions)
            try:
                for text,expected in (
                    # 48-APK: preserve valid 用船; the open field stays literal.
                    ('ようせんしてほせい','ようせんしてほせい'),
                    ('のひっています','残っています'),
                    ('しゅうありょうが','終了が'),
                    ('4ぱ゛位','4倍'),
                    ('ようせんしてほせい\t⇒ゆうせんしてほせい\t優先して補正','用船して補正\t⇒優先して補正\t優先して補正'),
                    ('のひっています\t⇒のこっています\t残っています','残っています\t⇒残っています\t残っています'),
                    ('しゅうありょうが\t⇒しゅうりょうが\t終了が','終了が\t⇒終了が\t終了が'),
                    ('4ぱ゛位\t4ばい\t4倍','4倍\t4倍\t4倍'),
                    ('子どもに絵本を読んであうげます。','子どもに絵本を読んであげます。'),
                    ('こどもにえほんをよんであうげます。','子供に絵本を読んであげます。'),
                    ('いんすと゛る','いんすどる'),
                    ('しゅう゛い','しゅゔい' if phase=='seed' else '周波'),
                    ('か゛そる','がそる'),
                ):
                    with self.subTest(phase=phase,text=text):
                        result=run(text)
                        self.assertEqual(result['corrected'],expected)
                        self.assertEqual(result.get('odd_spans'),[])
                        self.assertNotIn('_repair_surfaces',result)
                # 48-APC: original intended kana also receive normal spelling.
                for text,expected in (('ゆうせんしてほせい','優先して補正'),('のこっています','残っています'),
                                      ('しゅうりょうが','終了が'),('4ばい','4倍'),
                                      ('もんじにゅうりょく','もんじ入力'),('差し込み゛手、','差し込みで、'),('さしこみ゛て、','差し込みで、')):
                    with self.subTest(phase=phase,spelling=text):self.assertEqual(run(text+'\t')['corrected'],expected+'\t')
                for text in ('したあと','残っています','終了が','4倍','故人の遺した作品',
                             '保存してください','「のひっています」と入力します。','してみて','ほせいがきかない','今日は😀晴れです。'):
                    with self.subTest(phase=phase,keep=text):self.assertEqual(run(text)['corrected'],text)
                a.decisions.protect('のひっています')
                self.assertEqual(run('のひっています')['corrected'],'のひっています')
                self.assertEqual(a.store.revision(),revision)
            finally:set_active(None)

    def test_case_particle_without_a_host_does_not_spell_the_verb(self):
        import app
        from tests_analysis_async import initial
        state=initial();state.context_vec=None
        for source,expected in (('か゛そる','がそる'),):
            with self.subTest(source=source):
                result=app.correct_line(source,state.store,input_method='kana',
                    dict_index=state.dict_index,decisions=state.decisions,
                    context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))

    def test_unfinished_legacy_fragments_do_not_acquire_partial_kanji(self):
        import corrector as E
        from repaired_spelling import finish
        from tests_analysis_async import initial
        from last_choice import set_active
        a=initial();tok=E.make_tokenizer(a.store)
        cases=(('「とうけけつ」と書きました。','「とうけつけ」と書きました。',(2,6,'うけつけ','')),
               ('じっょうがありました。','じしょうがありました。',(0,3,'じしょ','')),
               ('昨日かふぶんを見ました。','昨日かたぶんを見ました。',(3,6,'たぶん','')),
               ('じっょしうがありました。','じしょしうがありました。',(0,3,'じしょ','')))
        try:
            for source,approved,frame in cases:
                with self.subTest(source=source):
                    result=finish(source,dict(corrected=approved,_repair_surfaces=[frame]),a.store,tok,a.dict_index,a.decisions)
                    self.assertEqual(result['corrected'],approved)
        finally:set_active(None)

    def test_explicit_kana_choice_and_final_rejection_are_preserved(self):
        import corrector as E
        from repaired_spelling import finish
        from tests_analysis_async import initial
        from last_choice import set_active
        a=initial();tok=E.make_tokenizer(a.store)
        def result():return dict(corrected='ゆうせんしてほせい',_repair_surfaces=[(0,4,'ゆうせん','kana_action_note')])
        try:
            with patch('last_choice.surface_for_reading',return_value='ゆうせん'):
                self.assertEqual(finish('ようせんしてほせい',result(),a.store,tok,a.dict_index,a.decisions)['corrected'],'ゆうせんしてほせい')
            with patch.object(E,'_check_replacement',return_value=(None,'blocked')):
                self.assertEqual(finish('ようせんしてほせい',result(),a.store,tok,a.dict_index,a.decisions)['corrected'],'ゆうせんしてほせい')
        finally:set_active(None)

if __name__=='__main__':unittest.main()
