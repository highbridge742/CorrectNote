"""直した行で、補助の いる・おく を漢字（て居・て置）で新しく書かない（2026-10-30・補正担当）"""
import unittest
import inspect
import contextual_repair as CR


class KanjiAuxVerbTests(unittest.TestCase):
    def test_validate_rejects_new_kanji_aux(self):
        src = inspect.getsource(CR.validate)
        self.assertIn("'kanji_auxiliary_verb'", src)

    def test_joint_filter_present(self):
        src = inspect.getsource(CR)
        self.assertIn("_aux=('て居','で居','て置','で置','て仕舞','で仕舞','た居','し居','だ居')", src)


if __name__ == '__main__':
    unittest.main()
