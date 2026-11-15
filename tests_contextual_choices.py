# -*- coding: utf-8 -*-
import unittest,sys
from types import SimpleNamespace
from unittest.mock import patch
import app,candidates
from decisions import DecisionStore
from tests_analysis_async import initial
import tests_particle_candidates as particle_tests


# 2026-11-14 補正担当（うに 10:44Z「2.よいです」）: 文章をきうしします。は 1.17.0 の時点でもう 送信します を出していなかった
# （今は紫）。選び直しの仕組みを見る試験は、補正の答えに頼らず、この作った答え（tests_contextual_reselection と同じ形）で見る。
KIUSHI_SOURCE='文章をきうしします。'
def kiushi_result():
    return dict(original=KIUSHI_SOURCE,corrected='文章をきいてします。',details=[],analysis_status='complete',
        contextual_choices=dict(version=1,source=KIUSHI_SOURCE,input_method='kana',candidates=[
            dict(start=3,end=9,base='きうしします',surface=s,reading='そうしんします')
            for s in ('送信します','そうしんします')]))


def _choice_span(r,expected):
    """答えの選び直しの行のうち、expected の頭の語を出す行の範囲（今の選び直しの単位は 語＋し のように短い）"""
    for c in (r.get('contextual_choices') or {}).get('candidates') or ():
        if c['surface'] and expected.startswith(c['surface'][:2]):
            return c['start'],c['end'],c['surface']
    return None


class ContextualChoiceContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.state=initial()

    def result(self,text,decisions=None):
        s=self.state
        return app.correct_line(text,s.store,input_method='kana',dict_index=s.dict_index,
            decisions=decisions or DecisionStore(),context_vec=None)

    def test_completed_analysis_retains_a_valid_alternative_without_changing_winner(self):
        text=KIUSHI_SOURCE;r=kiushi_result()
        self.assertEqual(r['corrected'],'文章をきいてします。')
        self.assertEqual(r['analysis_status'],'complete')
        self.assertNotIn('contextual_diagnostics',r)
        choices=candidates.contextual_choice_candidates(r,text,3,9)
        self.assertIn('送信します',[c['surface'] for c in choices])
        for c in choices:
            a,b=c['original_span'];self.assertEqual(text[a:b],c['base'])

    def test_known_successes_and_same_display_exclusion(self):
        # いうろ→登録 は 1.17.0 でも直らない（い と と は今の配列で隣でない）ので、直る 文書をせぞします。に替えた（2026-11-14）
        for text,expected in (('文書をせぞします。','保存します'),
                              ('資料をあんさしました。','印刷しました')):
            with self.subTest(text=text):
                r=self.result(text);self.assertEqual(r['corrected'],text[:3]+expected+'。')
                span=_choice_span(r,expected);self.assertTrue(span)
                a,b,surface=span
                source=candidates.contextual_choice_candidates(r,text,a,b)
                self.assertIn(surface,[c['surface'] for c in source])
                shown=r['corrected'];d=len(shown)-len(text)
                other=candidates.contextual_choice_candidates(r,shown,a,b+d)
                self.assertNotIn(surface,[c['surface'] for c in other])

    def test_unsupported_meaning_does_not_bypass_source_validation(self):
        r=self.result('情報をきうししてください。')
        # 今の答えは選び直しの行を持たないこともある（無ければ 更新 も出ない）（2026-11-14）
        self.assertNotIn('更新してください',[c['surface'] for c in (r.get('contextual_choices') or {}).get('candidates') or ()])

    def test_protection_and_partial_pair_rejection_are_respected(self):
        text='文章をきうしします。';d=DecisionStore();d.protect('きうし')
        self.assertFalse(self.result(text,d).get('contextual_choices'))
        d=DecisionStore()
        for face in ('送信','そうしん'):d.reject('きうし',face)
        r=self.result(text,d)
        self.assertFalse(any(c['surface'] in ('送信します','そうしんします')
            for c in r.get('contextual_choices',{}).get('candidates',())))

    def test_unknown_labels_and_normal_lines_do_not_gain_proposals(self):
        for text in ('ぷねたん','かんたんなぽねです。','情報を更新してください。'):
            with self.subTest(text=text):
                r=self.result(text);self.assertEqual(r['corrected'],text)
                self.assertFalse(r.get('contextual_choices'))

    def test_projection_rejects_stale_text_and_crossing_ranges(self):
        text='文章をきうしします。';r=self.result(text)
        self.assertFalse(candidates.contextual_choice_candidates(r,'別文をきうしします。',3,9))
        self.assertFalse(candidates.contextual_choice_candidates(r,text,0,9))
        self.assertFalse(candidates.contextual_choice_candidates(r,text,2,5))
        self.assertFalse(candidates.contextual_choice_candidates(r,text,-1,4))

    def test_independent_length_changes_use_display_coordinates(self):
        original='文書をせぞします。\t資料をあんさしました。'
        r=self.result(original);shown=r['corrected']
        self.assertEqual(shown,'文書を保存します。\t資料を印刷しました。')
        # 選び直しの単位は 語＋し（あんさし→印刷し）。表の位置の範囲もその単位で見る（2026-11-14）
        start=shown.rindex('を')+1;end=start+len('印刷し')
        # 表に出ている 印刷し と同じ候補は選び直しのメニューに出ない（同じ表示は除く）ので、写した位置そのものを見る
        found=[c for c in candidates._project_contextual_choices(r,shown) if c['base']=='あんさし']
        self.assertTrue(found)
        self.assertTrue(all(c['choice_span']==(start,end) and shown[start:end]==c['surface'] for c in found))
        self.assertEqual([c['original_span'] for c in found],[(start,start+len('あんさし'))])

    def test_original_choice_reaches_actual_rendered_units(self):
        import units,corrector
        from last_choice import LastChoiceStore
        import last_choice
        # 最後の選択は 11-08 から既定で使わない（CN_LEARNED_HISTORY=1 と同じにして、仕組みだけを見る）
        patcher=patch.object(last_choice,'LEARNED_OFF',False);patcher.start();self.addCleanup(patcher.stop)
        choices=LastChoiceStore();text=KIUSHI_SOURCE;r=kiushi_result()
        tokenize=corrector.make_tokenizer(self.state.store)
        self.assertEqual(units.build_line_units(r,tokenize,choices)[0],'文章をきいてします。')
        choices.record('きうしします','送信します')
        shown,built=units.build_line_units(r,tokenize,choices)
        self.assertEqual(shown,'文章を送信します。')
        selected=next(u for u in built if u['kind']=='chosen')
        self.assertEqual((selected['base'],selected['text']),('きうしします','送信します'))
        choices.forget_unit('きうしします')
        self.assertEqual(units.build_line_units(r,tokenize,choices)[0],'文章をきいてします。')

    def test_unproved_or_rejected_choices_are_not_projected(self):
        import units,corrector
        from last_choice import LastChoiceStore
        choices=LastChoiceStore();choices.record('きうしします','更新します')
        tokenize=corrector.make_tokenizer(self.state.store)
        r=self.result('文章をきうしします。')
        self.assertEqual(units.build_line_units(r,tokenize,choices)[0],r['corrected'])
        choices.record('きうしします','送信します')
        d=DecisionStore()
        for face in ('送信','そうしん'):d.reject('きうし',face)
        r=self.result('文章をきうしします。',d)
        self.assertEqual(units.build_line_units(r,tokenize,choices)[0],r['corrected'])

    def test_cache_roundtrip_keeps_choices_without_aliasing(self):
        import analysis_cache
        # きうし の補正の答えは選び直しの行を持たないので、作った答えで見る（2026-11-14）
        source=KIUSHI_SOURCE;r=kiushi_result()
        packed=analysis_cache._pack(r);restored=analysis_cache._unpack(packed)
        self.assertEqual(restored['contextual_choices'],r['contextual_choices'])
        self.assertIn('送信します',[c['surface'] for c in candidates.contextual_choice_candidates(restored,source,3,9)])
        restored['contextual_choices']['candidates'].clear()
        self.assertTrue(r['contextual_choices']['candidates'])
        self.assertTrue(analysis_cache._unpack(packed)['contextual_choices']['candidates'])


@unittest.skipUnless(sys.platform=='win32','Windows native UI')
class ContextualChoiceTkTests(unittest.TestCase):
    def setUp(self):
        particle_tests.ParticleChoiceTkTests.setUp(self)
        from tests_analysis_async import initial
        self.runtime=initial();a=self.a
        a.store=self.runtime.store;a.dict_index=self.runtime.dict_index;a.decisions=DecisionStore()
        self.source=KIUSHI_SOURCE
        self.result=kiushi_result()
        a.line_results=[self.result];a._quick_results=[self.result]
    tearDown=particle_tests.ParticleChoiceTkTests.tearDown

    def setup_pane(self,pane):
        a=self.a;shown=self.result['corrected'] if pane=='result' else self.source
        widget={'editor':a.editor,'result':a.result_view,'quick':a._quick_text}[pane]
        widget.delete('1.0','end');widget.insert('1.0',shown)
        unit=app.make_range_unit(shown,[],3,len(shown)-1)
        return widget,unit,shown

    def test_three_menus_offer_same_original_phrase_and_apply_explicit_choice(self):
        a=self.a
        for pane in ('editor','result','quick'):
            with self.subTest(pane=pane):
                widget,unit,shown=self.setup_pane(pane)
                a.line_units=[[unit]];a._quick_units=[[unit]]
                a.choices.record.reset_mock();a._make_dropdown.reset_mock()
                ordinary=[dict(surface='送信します',reading='そうしんします',kind='typo')]
                with patch.object(app,'build_range_candidates',return_value=ordinary),patch.object(app,'symbol_candidates',return_value=[]):
                    if pane=='editor':items=a._editor_dropdown_items(1,unit,[unit])
                    elif pane=='result':
                        a._open_dropdown(SimpleNamespace(x_root=0,y_root=0),1,unit)
                        items=a._make_dropdown.call_args.args[0]
                    else:
                        a._open_quick_dropdown(SimpleNamespace(x_root=0,y_root=0),1,unit)
                        items=a._make_dropdown.call_args.args[0]
                matching=[cb for label,cb in items if label.strip()=='送信します']
                self.assertEqual(len(matching),1)
                callback=matching[0]
                a.choices.record.assert_not_called();callback()
                if pane=='result' and not app.CorrectNoteApp._choices_take_effect(a):
                    # 2026-11-14 うに「F5再変換で…候補から選んだが、何も変わらなかった」の直し: 選びを覚えない間
                    # （last_choice.LEARNED_OFF）は、補正欄で選んだ語を本文へ書き込む（覚えるだけでは何も変わらない）
                    a.choices.record.assert_not_called()
                    self.assertEqual(a.editor.get('1.0','end-1c'),'文章を送信します。')
                    continue
                self.assertEqual(a.choices.record.call_args.args[:2],('きうしします','送信します'))
                if pane!='result':self.assertEqual(widget.get('1.0','end-1c'),'文章を送信します。')
                else:a._render_corrected.assert_called_once()

    def test_changed_context_or_new_rejection_cancels_stale_choice(self):
        a=self.a
        for pane in ('editor','result','quick'):
            for change in ('context','reject','protect','method'):
                with self.subTest(pane=pane,change=change):
                    a.settings['input_method']='kana'
                    a.decisions=DecisionStore()
                    widget,unit,shown=self.setup_pane(pane)
                    cand=next(c for c in a._contextual_choice_candidates(1,unit,widget,[unit]) if c['surface']=='送信します')
                    if change=='context':
                        widget.delete('1.0','1.2');widget.insert('1.0','別文')
                    elif change=='reject':a.decisions.reject('きうし','送信')
                    elif change=='protect':a.decisions.protect('きうし')
                    else:a.settings['input_method']='romaji'
                    before=widget.get('1.0','end-1c');a.choices.record.reset_mock()
                    choose={'editor':lambda:a._editor_choose_word(1,unit,cand),
                        'result':lambda:a._choose_word(unit,cand,1),
                        'quick':lambda:a._quick_choose_word(1,unit,cand)}[pane]
                    choose();self.assertEqual(widget.get('1.0','end-1c'),before)
                    a.choices.record.assert_not_called()

if __name__=='__main__':unittest.main()
