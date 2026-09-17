# -*- coding: utf-8 -*-
"""Normal kana cooking shares the same native food/action proof."""
import unittest
import morphology as M
import semantic_roles as S
import reading_segments as R


@unittest.skipUnless(M.dictionary_inflections('煮る'),'requires native dictionary')
class CookingRoleTests(unittest.TestCase):
    def test_heat_actions_share_food_and_ingredient_roles(self):
        for noun,verb in (('野菜','煮る'),('肉','煮込む'),('卵','茹でる'),('魚','蒸す'),
                          ('じゃがいも','蒸かす'),('野菜','炒める'),('魚','揚げる')):
            self.assertTrue(S.support(noun,verb),(noun,verb))
        for noun,verb in (('資料','煮る'),('議員','茹でる'),('野菜','似る')):
            self.assertFalse(S.support(noun,verb),(noun,verb))
        self.assertIn('ingredient',S.native_verb_roles('に','連用形','に',tail='ます'))
        self.assertNotIn('ingredient',S.native_verb_roles('似','連用形','に',tail='ます'))

    def test_natural_kana_keeps_text_and_has_no_purple(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('やさいをにます。','にくをにこみます。','たまごをゆでます。',
                     'さかなをむします。','じゃがいもをふかします。','やさいをいためます。',
                     'さかなをあげます。','野菜を煮ます。','資料を読みます。'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],text)
            self.assertEqual(result.get('odd_spans'),[],text)

    def test_completed_clause_needs_the_actual_case_and_complete_inflection(self):
        self.assertTrue(R.completed_native_reading_clause('やさいをにます',require_object_fit=True))
        for text in ('やさいをに','やさいをにるます','ぷねらをにます','しりょうをにます'):
            self.assertFalse(R.completed_native_reading_clause(text,require_object_fit=True),text)

    def test_vessels_have_the_shared_destination_role(self):
        for noun in ('鍋','フライパン','皿','茶碗','コップ','カップ','瓶','壺','ボウル'):
            self.assertTrue(S.case_action_support(noun,'に','入れる'),noun)
        self.assertFalse(S.case_action_support('水','に','読む'))
        self.assertFalse(S.case_action_support('資料','に','入れる'))

    def test_fresh_dictionary_keeps_original_contents_of_vessels(self):
        import app
        import reading_segments as R
        from tests_analysis_async import initial
        from janome_import import import_from_janome
        a=initial();import_from_janome(a.store)
        for text in ('なべにみずをいれてわかします。','なべにみずをいれます。',
                     'こっぷにみずをいれます。','ちゃわんにごはんをいれます。',
                     'なべにさかなをいれます。'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=a.context_vec,decisions=a.decisions)
            self.assertEqual(result['corrected'],text)
            self.assertEqual(result.get('odd_spans'),[],text)
        for text in ('なべにみずをいれますです','ぷねらにみずをいれます'):
            self.assertFalse(R.intact_native_reading(text),text)



if __name__=='__main__':unittest.main()
