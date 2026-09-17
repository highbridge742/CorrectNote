"""Preserve genuine context without treating an IME parse as infallible."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import contextual_repair as R


def parts(*items):
    out=[];edge=0
    for item in items:
        surface,reading,pos=item[:3]
        form=item[3] if len(item)>3 else ''
        known=item[4] if len(item)>4 else True
        out.append((surface,pos,reading,edge,edge+len(surface),known,form))
        edge+=len(surface)
    return out


def forms(surface):
    return {'た':(('助動詞,*,*,*','基本形','た','た'),),
            '聞く':(('動詞,自立,*,*','基本形','聞く','きく'),)}.get(surface,())


class RepairBoundaryTests(unittest.TestCase):
    def test_completed_modifier_is_context_for_the_later_broken_word(self):
        line='保存した画゜像を確認'
        tokens=parts(('保存','ほぞん','名詞:サ変接続'),('し','し','動詞:自立','連用形'),
            ('た','た','助動詞','基本形'),('画','が','名詞:一般'),('゜','゜','記号:一般'),
            ('像','ぞう','名詞:一般'),('を','を','助詞:格助詞'),('確認','かくにん','名詞:サ変接続'))
        with patch('oddness.is_odd_run',return_value=[('画','゜',4,6)]), \
             patch('mark_usage.unattached_positions',return_value=(5,)), \
             patch('morphology.dictionary_inflections',side_effect=forms):
            rows=R.targets_for_line(line,lambda _:tokens,None,None)
        self.assertEqual(rows[0].text,'画゜像')
        self.assertEqual(rows[0].start,4)
        self.assertEqual(rows[0].context,line)

    def test_finite_ime_misconversion_still_has_the_original_wider_fallback(self):
        line='聞く人しました'
        tokens=parts(('聞く','きく','動詞:自立','基本形'),('人','ひと','名詞:一般'),
            ('し','し','動詞:自立','連用形'),('まし','まし','助動詞','連用形'),('た','た','助動詞','基本形'))
        with patch('oddness.is_odd_run',return_value=[('人','し',2,4)]), \
             patch('mark_usage.unattached_positions',return_value=()), \
             patch('morphology.dictionary_inflections',side_effect=forms):
            rows=R.targets_for_line(line,lambda _:tokens,None,None)
        self.assertIn('聞く人',[r.text for r in rows])

    def test_misparsed_first_kana_is_an_alternative_not_a_deleted_particle(self):
        line='保存したがぞ゜ウを確認'
        tokens=parts(('保存','ほぞん','名詞:サ変接続'),('し','し','動詞:自立','連用形'),
            ('た','た','助動詞','基本形'),('が','が','助詞:接続助詞'),('ぞ','ぞ','助詞:終助詞'),
            ('゜','゜','記号:一般'),('ウ','う','名詞:一般'),('を','を','助詞:格助詞'),('確認','かくにん','名詞:サ変接続'))
        with patch('oddness.is_odd_run',return_value=[('ぞ','゜',5,7)]), \
             patch('mark_usage.unattached_positions',return_value=(6,)), \
             patch('morphology.dictionary_inflections',side_effect=forms):
            rows=R.targets_for_line(line,lambda _:tokens,None,None)
        self.assertEqual([(r.start,r.end,r.text) for r in rows[:2]],[(4,8,'がぞ゜ウ'),(5,8,'ぞ゜ウ')])

    def test_unknown_marked_kana_does_not_swallow_the_known_predicate(self):
        line='もじ゛つを見ます'
        tokens=parts(('もじ゛つを','もじ゛つを','名詞:一般','',False),
                     ('見','み','動詞:自立','連用形'),('ます','ます','助動詞','基本形'))
        with patch('oddness.is_odd_run',return_value=[('じ','゛',1,3)]), \
             patch('mark_usage.unattached_positions',return_value=(2,)):
            rows=R.targets_for_line(line,lambda _:tokens,None,None)
        self.assertEqual([(r.text,r.following) for r in rows],[('もじ゛つ','を見ます')])

    def test_dictionary_absence_does_not_prove_a_completed_modifier(self):
        token=parts(('聞く','きく','動詞:自立','基本形'))[0]
        with patch('morphology.dictionary_inflections',return_value=None):
            self.assertFalse(R._completed_predicate_token(token))
        self.assertFalse(R._completed_predicate_token(token[:6]))

    def test_suru_attachment_cannot_be_evaded_by_relabelling_it_as_conjunction(self):
        original='旧明井します';surface='救命しよう'
        target=R.RepairTarget(original,0,3,0,len(original),(('井','し',2,4),),True,'します')
        candidate=parts(('救命','きゅうめい','名詞:サ変接続'),
            ('しよ','しよ','動詞:自立','未然ウ接続'),('う','う','助動詞','基本形'))
        native_original=parts(('旧明井','きゅうめいい','名詞:一般'),('し','し','動詞:自立','連用形'),('ます','ます','助動詞','基本形'))
        changed=candidate+[('し','助詞:接続助詞','し',5,6,True,''),('ます','助動詞','ます',6,8,True,'基本形')]
        def tokenize(text):
            return {original:native_original,surface:candidate,surface+'します':changed}.get(text,parts((text,text,'名詞:一般')))
        engine=SimpleNamespace(_check_replacement=lambda source,change,*args,**kwargs:(change,None))
        with patch('oddness.is_odd_run',return_value=[]):
            self.assertEqual(R.validate(target,surface,engine,tokenize,None,None,expected_reading='きゅうめいしよう'),(False,'suru_slot'))

    def test_anomaly_is_required_before_any_modifier_or_particle_alternative(self):
        with patch('oddness.is_odd_run',return_value=[]):
            self.assertEqual(R.targets_for_line('保存した画像',lambda _:[],None,None),[])


    def test_formal_noun_alternative_only_proposes_a_repair_boundary(self):
        import pos_grammar as P
        token=parts(('ため','ため','名詞:一般'))[0]
        entry=(('名詞,非自立,副詞可能,*','*','ため','ため'),)
        with patch.object(P,'_load_tables',return_value=({}, {'ため'}, {})), \
             patch('morphology.dictionary_inflections',return_value=entry):
            self.assertFalse(P.is_functional_noun(token))
            self.assertTrue(P.is_functional_noun(token,dictionary_alternative=True))
            self.assertFalse(P.is_functional_noun(parts(('ため息','ためいき','名詞:サ変接続'))[0],dictionary_alternative=True))

    def test_formal_noun_alternative_requires_the_actual_reading(self):
        import pos_grammar as P
        token=parts(('ため','ため','名詞:一般'))[0]
        with patch.object(P,'_load_tables',return_value=({}, {'ため'}, {})), \
             patch('morphology.dictionary_inflections',return_value=(('名詞,非自立,一般,*','*','ため','べつ'),)):
            self.assertFalse(P.is_functional_noun(token,dictionary_alternative=True))

    def test_quote_case_accepts_a_native_finite_predicate_but_object_case_does_not(self):
        surface='解決した'
        candidate=parts(('解決','かいけつ','名詞:サ変接続'),('し','し','動詞:自立','連用形'),('た','た','助動詞','基本形'))
        engine=SimpleNamespace(_check_replacement=lambda source,change,*args,**kwargs:(change,None))
        for particle,pos,expected in (('と','助詞:格助詞:引用',True),('を','助詞:格助詞:一般',False)):
            original='旧字'+particle
            original_tokens=parts(('旧字','きゅうじ','名詞:一般'),(particle,particle,pos))
            changed=candidate+[(particle,pos,particle,4,5,True,'')]
            def tokenize(value):
                return {original:original_tokens,surface:candidate,surface+particle:changed}.get(value,parts((value,value,'名詞:一般')))
            target=R.RepairTarget(original,0,2,0,len(original),(('旧','字',0,2),),True,particle)
            with patch('oddness.is_odd_run',return_value=[]),patch('morphology.dictionary_inflections',side_effect=forms):
                ok,_=R.validate(target,surface,engine,tokenize,None,None,expected_reading='かいけつした')
            self.assertEqual(ok,expected,particle)

    def test_final_particle_is_not_the_start_of_a_new_modified_noun(self):
        line='経つぜ蹴ます'
        tokens=parts(('経つ','たつ','動詞:自立','基本形'),('ぜ','ぜ','助詞:終助詞'),
            ('蹴','け','動詞:自立','体言接続特殊２'),('ます','ます','助動詞','基本形'))
        entry=(('動詞,自立,*,*','基本形','経つ','たつ'),)
        with patch('oddness.is_odd_run',return_value=[('蹴','ます',3,6)]), \
             patch('mark_usage.unattached_positions',return_value=()), \
             patch('morphology.dictionary_inflections',return_value=entry):
            rows=R.targets_for_line(line,lambda _:tokens,None,None)
        self.assertTrue(rows)
        self.assertTrue(all(not r.text.startswith('ぜ') for r in rows))


    def modifier_slot(self,kind='predicate',native=True):
        import oddness as O
        prefix='小さい';candidate='動く';tail=''
        if kind=='nominal_tail':tail='玩具'
        if kind=='nominal_head':candidate='学び'
        if kind=='case':candidate='でかく'
        original=prefix+'誤語'+tail;changed=prefix+candidate+tail
        orig=parts((prefix,'ちいさい','形容詞:自立','基本形'),('誤語','ごご','名詞:一般'))
        if kind=='case':
            actual=parts((prefix,'ちいさい','形容詞:自立','基本形'),
                ('で','で','助詞:格助詞:一般'),('かく','かく','名詞:一般'))
            isolated=parts((candidate,'でかく','形容詞:自立','連用テ接続'))
        else:
            actual=parts((prefix,'ちいさい','形容詞:自立','基本形'),
                (candidate,'うごく' if candidate=='動く' else 'まなび','動詞:自立',
                 '基本形' if candidate=='動く' else '連用形'))
            isolated=[]
        if tail:actual+=parts((tail,'がんぐ','名詞:一般'))
        if tail:actual[-1]=actual[-1][:3]+(len(prefix+candidate),len(changed))+actual[-1][5:]
        def tokenize(text):
            if text==original:return orig
            if text==changed:return actual
            if text==candidate:return isolated
            return []
        entries={prefix:(('形容詞,自立,*,*','基本形',prefix,'ちいさい'),) if native else (),
                 '玩具':(('名詞,一般,*,*','*','玩具','がんぐ'),),
                 '学び':(('名詞,一般,*,*','*','学び','まなび'),)}
        with patch('morphology.dictionary_inflections',side_effect=lambda text:entries.get(text,())):
            return O.preserves_completed_modifier(original,len(prefix),changed,len(prefix),
                                                   len(prefix+candidate),tokenize)

    def test_preserved_native_finite_modifier_does_not_attach_to_new_predicate(self):
        self.assertFalse(self.modifier_slot())

    def test_multiple_modifiers_can_share_a_later_native_noun(self):
        self.assertTrue(self.modifier_slot('nominal_tail'))

    def test_original_finite_form_without_native_proof_does_not_fix_the_boundary(self):
        self.assertTrue(self.modifier_slot(native=False))

    def test_candidate_pos_is_obtained_in_context_not_from_isolated_adjective(self):
        self.assertTrue(self.modifier_slot('case'))

    def test_candidate_with_native_nominal_homograph_can_receive_a_modifier(self):
        self.assertTrue(self.modifier_slot('nominal_head'))


if __name__=='__main__':unittest.main()
