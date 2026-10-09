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


class NativeMorphCacheContractTests(unittest.TestCase):
    def ime(self,retained=True):
        from threading import get_ident
        obj=L.JapaneseIME();obj.available=True;obj._owner=get_ident();obj._retained=retained
        return obj

    def query(self,answers):
        calls=[];answers=iter(answers);buffers=[]
        def method(pointer,index,*signature):
            self.assertEqual(index,5)
            def native(language,request,mode,units,source,unused,output):
                calls.append((request,source));answer=next(answers)
                if answer is None:return -1
                allocation,address,row=MorphologyBufferTests().block();buffers.append(allocation)
                if answer=='invalid':row.size=0
                output._obj.value=address
                return 0
            return native
        return calls,buffers,method

    def test_success_shares_decoded_values_but_request_and_input_remain_distinct(self):
        obj=self.ime();calls,buffers,method=self.query(('ok','ok','ok'))
        with patch.object(L,'_method',side_effect=method),patch.object(L._ole32,'CoTaskMemFree') as free:
            value=obj._morph('😀確認',0x30000)
            self.assertEqual(value,('😀確認','にやりかくにん',((0,1,0,3,100,63),(1,3,3,7,100,63))))
            self.assertEqual(obj._morph('😀確認',0x30000),value)
            obj._morph('😀確認',0x10000);obj._morph('😀調査',0x30000)
            self.assertEqual(free.call_count,3)
        self.assertEqual(calls,[(0x30000,'😀確認'),(0x10000,'😀確認'),(0x30000,'😀調査')])
        obj.close();self.assertFalse(obj._morph_cache)

    def test_failure_and_invalid_buffer_are_retried_and_never_retained(self):
        obj=self.ime();calls,buffers,method=self.query((None,'invalid','ok'))
        with patch.object(L,'_method',side_effect=method),patch.object(L._ole32,'CoTaskMemFree') as free:
            for unused in range(2):
                self.assertIsNone(obj._morph('😀確認',0x30000));self.assertFalse(obj._morph_cache)
            self.assertIsNotNone(obj._morph('😀確認',0x30000))
            self.assertEqual(free.call_count,2)
        self.assertEqual(len(calls),3);obj.close()

    def test_scope_owner_availability_and_cancellation_are_checked_even_on_hit(self):
        from threading import get_ident
        from analysis_context import SupersededAnalysis
        obj=self.ime();calls,buffers,method=self.query(('ok','ok','ok'))
        with patch.object(L,'_method',side_effect=method),patch.object(L._ole32,'CoTaskMemFree'):
            value=obj._morph('😀確認',0x30000)
            obj.available=False;self.assertIsNone(obj._morph('😀確認',0x30000));obj.available=True
            obj._owner=-1;self.assertIsNone(obj._morph('😀確認',0x30000));obj._owner=get_ident()
            with patch('analysis_context.check_current_request',side_effect=SupersededAnalysis):
                with self.assertRaises(SupersededAnalysis):obj._morph('😀確認',0x30000)
            obj._retained=False
            self.assertEqual(obj._morph('😀確認',0x30000),value)
            self.assertEqual(obj._morph('😀確認',0x30000),value)
        self.assertEqual(len(calls),3);obj.close()
        self.assertFalse(obj._morph_cache);self.assertIsNone(obj._morph('😀確認',0x30000))

    def test_real_queries_share_within_row_and_release_after_scope_failure(self):
        import ime_session as P
        from analysis_context import SupersededAnalysis
        # A fresh native query can return different flags from an earlier
        # allocation. Compare every documented field with that query's own
        # buffer; cache reuse must still return the exact original tuple.
        import ctypes as C
        native_answers=[];native_method=L._method
        def observe(pointer,index,*signature):
            query=native_method(pointer,index,*signature)
            if index!=5:return query
            def call(*args):
                hr=query(*args)
                if hr==0 and args[-1]._obj.value:
                    row=C.cast(args[-1]._obj,C.POINTER(L._MORRSLT)).contents
                    output=C.wstring_at(row.output,row.output_len)
                    # This fixture has only BMP characters, so native UTF-16
                    # offsets are also Python character offsets.
                    self.assertEqual(len(output.encode('utf-16-le'))//2,len(output))
                    words=tuple((w.display_pos,w.display_pos+w.display_len,
                        w.reading_pos,w.reading_pos+w.reading_len,w.pos,w.flags&0x3f)
                        for w in row.words[:row.word_count])
                    native_answers.append((output,words))
                return hr
            return call
        with patch.object(L,'_method',side_effect=observe) as method:
            with self.assertRaises(SupersededAnalysis):
                with P.resource_scope():
                    with L.JapaneseIME() as first:
                        if not first.available:self.skipTest(first.error)
                        value=first.convert_words('しりょうをかくにんします');self.assertIsNotNone(value)
                        self.assertEqual(value,native_answers[-1])
                    with L.JapaneseIME() as second:
                        self.assertIs(first,second)
                        self.assertEqual(second.convert_words('しりょうをかくにんします'),value)
                    self.assertEqual(sum(call.args[1]==5 for call in method.call_args_list),1)
                    raise SupersededAnalysis()
            self.assertFalse(first.available);self.assertFalse(first._morph_cache)
            with P.resource_scope():
                with L.JapaneseIME() as later:
                    self.assertIsNot(first,later)
                    current=later.convert_words('しりょうをかくにんします')
                    self.assertEqual(current,native_answers[-1])
                    self.assertEqual(len(native_answers),2)
                    self.assertEqual(later.convert_words('しりょうをかくにんします'),current)
            self.assertEqual(sum(call.args[1]==5 for call in method.call_args_list),2)
            self.assertFalse(later.available);self.assertFalse(later._morph_cache)

    def test_new_scope_preserves_stable_or_changed_native_flags(self):
        import ime_session as P
        from analysis_context import SupersededAnalysis
        # Both answers are owned synthetic native buffers. Stable answers
        # retain the previous cross-scope full-tuple equality contract; a
        # changed answer must remain changed, including every defined flag.
        for next_flags in (42,10):
            with self.subTest(next_flags=next_flags):
                buffers=[];queries=[];closed=[];flags=iter((42,next_flags))
                def factory(output):output._obj.value=1;return 0
                def method(pointer,index,*signature):
                    def call(*args):
                        if index==0:args[-1]._obj.value=2
                        elif index==4:closed.append(pointer.value)
                        elif index==5:
                            allocation,address,row=MorphologyBufferTests().block()
                            current_flags=next(flags)
                            for word in row.words[:row.word_count]:word.flags=current_flags
                            buffers.append(allocation);queries.append(args[4])
                            args[-1]._obj.value=address
                        return 0
                    return call
                def expected(current_flags):
                    return ('😀確認',((0,1,0,3,100,current_flags),(1,3,3,7,100,current_flags)))
                with patch.object(L,'_factory',side_effect=factory), \
                        patch.object(L,'_method',side_effect=method), \
                        patch.object(L,'_release') as release, \
                        patch.object(L._ole32,'CoInitializeEx',return_value=0), \
                        patch.object(L._ole32,'CoUninitialize') as uninit, \
                        patch.object(L._ole32,'CoTaskMemFree') as free:
                    with self.assertRaises(SupersededAnalysis):
                        with P.resource_scope():
                            with L.JapaneseIME() as first:
                                self.assertTrue(first.available)
                                value=first.convert_words('にやりかくにん')
                                self.assertEqual(value,expected(42))
                            with L.JapaneseIME() as second:
                                self.assertIs(second,first)
                                self.assertEqual(second.convert_words('にやりかくにん'),value)
                            self.assertEqual(len(queries),1)
                            raise SupersededAnalysis()
                    self.assertFalse(first.available);self.assertFalse(first._morph_cache)
                    with P.resource_scope():
                        with L.JapaneseIME() as later:
                            self.assertIsNot(later,first)
                            current=later.convert_words('にやりかくにん')
                            self.assertEqual(current,expected(next_flags))
                            self.assertEqual(later.convert_words('にやりかくにん'),current)
                            if next_flags==42:self.assertEqual(current,value)
                            else:self.assertNotEqual(current,value)
                    self.assertFalse(later.available);self.assertFalse(later._morph_cache)
                    self.assertEqual(queries,['にやりかくにん']*2)
                    self.assertEqual(len(closed),2)
                    self.assertEqual(free.call_count,2);self.assertEqual(uninit.call_count,2)
                    self.assertEqual(release.call_count,4)

if __name__=='__main__':unittest.main()
