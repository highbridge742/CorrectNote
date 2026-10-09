"""Preserve the existing scalar mapping and non-str iterable contract."""
import unittest
import morphology
import loanword
import kana_text


def previous(text):
    out=[]
    for ch in text:
        if '\u30a1'<=ch<='\u30f6':out.append(chr(ord(ch)-0x60))
        else:out.append(ch)
    return ''.join(out)


def outcome(function,factory):
    try:
        value=function(factory())
        return ('return',type(value),value)
    except Exception as error:
        return ('raise',type(error),str(error))


class KatakanaConversionTests(unittest.TestCase):
    def test_all_unicode_scalars_and_surrogates_keep_previous_values(self):
        for start in range(0,0x110000,4096):
            text=''.join(chr(code) for code in range(start,min(start+4096,0x110000)))
            expected=previous(text)
            self.assertEqual(morphology.katakana_to_hiragana(text),expected,hex(start))
            self.assertEqual(loanword.katakana_to_hiragana(text),expected,hex(start))

    def test_no_width_normalization_mark_composition_or_extra_range(self):
        text='ヴヵヶヷヸヹヺー・ヽヾｶｷｸｹｺカ\u3099カ\u309bハ\u309a😀𠮷\x00\n'
        expected='ゔゕゖヷヸヹヺー・ヽヾｶｷｸｹｺか\u3099か\u309bは\u309a😀𠮷\x00\n'
        for function in (morphology.katakana_to_hiragana,loanword.katakana_to_hiragana):
            self.assertEqual(function(text),expected)
            self.assertEqual(function(''),'')

    def test_iterables_subclasses_and_errors_keep_existing_contract(self):
        class Iterated(str):
            def __iter__(self):return iter(('カ','ABC','ｷ'))
            def translate(self,table):raise AssertionError('Subclass must keep iteration')
        class Broken:
            def __iter__(self):raise RuntimeError('synthetic iteration failure')
        factories=(lambda:None,lambda:12,lambda:b'abc',lambda:bytearray(b'abc'),
                   lambda:[],lambda:['カ','キ','ABC',''],lambda:('カ','ｷ'),
                   lambda:(ch for ch in ('カ','キ','A')),lambda:['カナ'],
                   lambda:['A',12],lambda:Iterated('ignored'),lambda:Broken())
        for factory in factories:
            expected=outcome(previous,factory)
            for function in (morphology.katakana_to_hiragana,loanword.katakana_to_hiragana):
                self.assertEqual(outcome(function,factory),expected)

    def test_public_modules_share_only_the_pure_converter(self):
        self.assertIs(morphology.katakana_to_hiragana,kana_text.katakana_to_hiragana)
        self.assertIs(loanword.katakana_to_hiragana,kana_text.katakana_to_hiragana)
        self.assertEqual(len(kana_text._HIRAGANA_TRANSLATION),86)


if __name__=='__main__':unittest.main()
