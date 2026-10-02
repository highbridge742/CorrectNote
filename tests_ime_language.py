"""Native reading evidence keeps the input and Unicode coordinate contract."""
import unittest
from unittest.mock import patch
import ime_language as L


class MorphologyContractTests(unittest.TestCase):
    def test_utf16_positions_exclude_half_a_surrogate_pair(self):
        self.assertEqual(L._utf16_positions('😀確認𠮷'),{0:0,2:1,3:2,4:3,6:4})
        with self.assertRaises(ValueError):L._utf16_positions('\ud800')

    def test_direct_conversion_keeps_supplied_reading(self):
        ime=L.JapaneseIME();words=((0,2,0,3,100,3),)
        with patch.object(ime,'_morph',return_value=('明日','あした',words)) as morph:
            self.assertEqual(ime.convert_words('あした'),('明日',words))
        morph.assert_called_once_with('あした',0x10000)

    def test_normalized_input_is_not_claimed_as_original_reading(self):
        ime=L.JapaneseIME()
        with patch.object(ime,'_morph',return_value=('😀確認','にやりかくにん',())):
            self.assertIsNone(ime.convert_words('😀かくにん'))

    def test_reverse_descriptors_are_source_aligned(self):
        ime=L.JapaneseIME()
        with patch.object(ime,'_morph',return_value=('にやりかくにん','😀確認',((0,3,0,1,905,3),(3,7,1,3,101,3)))):
            self.assertEqual(ime.reverse_words('😀確認'),('にやりかくにん',((0,1,0,3,905,3),(1,3,3,7,101,3))))

    def test_unavailable_and_mismatched_reverse_are_not_evidence(self):
        ime=L.JapaneseIME()
        self.assertIsNone(ime.convert_words('かくにん'))
        with patch.object(ime,'_morph',return_value=('よみ','別表記',())):
            self.assertIsNone(ime.reverse_words('原文'))


class MorphologyBufferTests(unittest.TestCase):
    def block(self):
        import ctypes as C
        output='😀確認'.encode('utf-16-le');reading='にやりかくにん'.encode('utf-16-le')
        size=C.sizeof(L._MORRSLT)+len(output)+len(reading)+2*C.sizeof(L._WDD)
        allocation=C.create_string_buffer(size);address=C.addressof(allocation)
        row=L._MORRSLT.from_buffer(allocation);row.size=size
        row.output=address+C.sizeof(L._MORRSLT);row.output_len=len(output)//2
        row.reading=row.output+len(output);row.reading_len=len(reading)//2
        C.memmove(row.output,output,len(output));C.memmove(row.reading,reading,len(reading))
        row.words=C.cast(row.reading+len(reading),C.POINTER(L._WDD));row.word_count=2
        for index,coordinates in enumerate(((0,0,2,3),(2,3,2,4))):
            word=row.words[index]
            word.display_pos,word.reading_pos,word.display_len,word.reading_len=coordinates
            word.pos=100;word.flags=0xffff
        return allocation,address,row
    def test_packed_unicode_block_and_reserved_bits(self):
        allocation,address,row=self.block()
        result=L._decode_morph_result(address,4)
        self.assertEqual(result,('😀確認','にやりかくにん',((0,1,0,3,100,63),(1,3,3,7,100,63))))
    def test_out_of_block_members_are_rejected_before_dereference(self):
        import ctypes as C
        for member in ('output','reading','words'):
            for offset in (-1,1,10000):
                with self.subTest(member=member,offset=offset):
                    allocation,address,row=self.block()
                    pointer=address+row.size+offset
                    setattr(row,member,C.cast(pointer,C.POINTER(L._WDD)) if member=='words' else pointer)
                    self.assertIsNone(L._decode_morph_result(address,4))
    def test_small_header_and_invalid_word_ranges(self):
        import ctypes as C
        allocation,address,row=self.block();row.size=C.sizeof(L._MORRSLT)-1
        self.assertIsNone(L._decode_morph_result(address,4))
        allocation,address,row=self.block();row.words[1].display_pos=1
        self.assertIsNone(L._decode_morph_result(address,4))
        allocation,address,row=self.block();row.word_count=1000
        self.assertIsNone(L._decode_morph_result(address,4))


class NativeMorphologyTests(unittest.TestCase):
    def test_first_words_match_conversion_without_inverse_reading(self):
        with L.JapaneseIME() as ime:
            if not ime.available:self.skipTest(ime.error)
            for reading in ('あしたかくにんします','こんにちのわだいです','こんねんのもくひょうです','にっぽんのぶんかです'):
                with self.subTest(reading=reading):
                    result=ime.convert_words(reading)
                    self.assertIsNotNone(result)
                    self.assertEqual(result[0],ime.convert(reading))
                    self.assertEqual(result[1][-1][3],len(reading))

    def test_reverse_emoji_does_not_shift_following_word_coordinates(self):
        with L.JapaneseIME() as ime:
            if not ime.available:self.skipTest(ime.error)
            result=ime.reverse_words('😀確認')
            self.assertIsNotNone(result)
            self.assertEqual(result[1][0][:2],(0,1))
            self.assertEqual(result[1][-1][:2],(1,3))




class NativeTextCacheContractTests(unittest.TestCase):
    def ime(self,retained=True):
        from threading import get_ident
        obj=L.JapaneseIME();obj.available=True;obj._owner=get_ident();obj._retained=retained
        return obj

    def calls(self,answers):
        import ctypes as C
        calls=[];answers=iter(answers)
        def method(pointer,index,*signature):
            def query(language,source,start,end,output):
                calls.append((index,C.wstring_at(source)));answer=next(answers)
                if answer is None:return -1
                output._obj.value=L._oleaut32.SysAllocString(answer)
                return 0
            return query
        return calls,method

    def test_method_and_input_are_distinct_and_failure_is_retried(self):
        obj=self.ime();calls,method=self.calls((None,'資料','しりょう','確認'))
        with patch.object(L,'_method',side_effect=method):
            self.assertIsNone(obj.convert('しりょう'))
            self.assertEqual(obj.convert('しりょう'),'資料')
            self.assertEqual(obj.convert('しりょう'),'資料')
            self.assertEqual(obj.phonetic('しりょう'),'しりょう')
            self.assertEqual(obj.convert('かくにん'),'確認')
        self.assertEqual(calls,[(8,'しりょう'),(8,'しりょう'),(7,'しりょう'),(8,'かくにん')])
        obj.close()

    def test_empty_success_is_supported_and_close_discards_cached_strings(self):
        obj=self.ime();calls,method=self.calls(('',))
        with patch.object(L,'_method',side_effect=method):
            self.assertEqual(obj.convert('しりょう'),'')
            self.assertEqual(obj.convert('しりょう'),'')
        self.assertEqual(len(calls),1)
        obj.close();self.assertFalse(obj._text_cache)
        self.assertIsNone(obj.convert('しりょう'))

    def test_unavailable_foreign_and_unscoped_queries_do_not_borrow_hits(self):
        from threading import get_ident
        obj=self.ime();calls,method=self.calls(('資料','資料','資料'))
        with patch.object(L,'_method',side_effect=method):
            self.assertEqual(obj.convert('しりょう'),'資料')
            obj.available=False;self.assertIsNone(obj.convert('しりょう'));obj.available=True
            obj._owner=-1;self.assertIsNone(obj.convert('しりょう'));obj._owner=get_ident()
            obj._retained=False
            self.assertEqual(obj.convert('しりょう'),'資料')
            self.assertEqual(obj.convert('しりょう'),'資料')
        self.assertEqual(len(calls),3);obj.close()

    def test_real_correction_scope_reuses_then_next_scope_reopens(self):
        import ime_session as P
        with patch.object(L,'_method',wraps=L._method) as method:
            with P.resource_scope():
                with L.JapaneseIME() as first:
                    if not first.available:self.skipTest(first.error)
                    result=first.convert('しりょう');self.assertIsNotNone(result)
                with L.JapaneseIME() as second:
                    self.assertIs(second,first);self.assertEqual(second.convert('しりょう'),result)
                self.assertEqual(sum(call.args[1]==8 for call in method.call_args_list),1)
            self.assertFalse(first.available);self.assertFalse(first._text_cache)
            with P.resource_scope():
                with L.JapaneseIME() as later:
                    self.assertIsNot(later,first);self.assertIsNotNone(later.convert('しりょう'))
            self.assertEqual(sum(call.args[1]==8 for call in method.call_args_list),2)

if __name__=='__main__':unittest.main()
