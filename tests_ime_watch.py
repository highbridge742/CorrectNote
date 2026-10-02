# -*- coding: utf-8 -*-
"""IMM string boundaries and failures must not fabricate reading evidence."""
import ctypes as C
import unittest
from unittest.mock import patch
import ime_watch as I


class FakeIMM:
    def __init__(self,data=b'',size=None,got=None):
        self.data=data;self.size=len(data) if size is None else size
        self.got=len(data) if got is None else got;self.releases=[]
    def ImmGetContext(self,hwnd):return 0x123456789
    def ImmReleaseContext(self,hwnd,himc):self.releases.append((hwnd,himc));return 1
    def ImmGetCompositionStringW(self,himc,index,buffer,size):
        if buffer is None:return self.size
        C.memmove(buffer,self.data,min(size,len(self.data)))
        return self.got


class IMMReadingTests(unittest.TestCase):
    def test_complete_nonterminated_string_keeps_all_characters(self):
        for text in ('確認','ｶｸﾆﾝ','😀確認'):
            with self.subTest(text=text):
                self.assertEqual(I._composition_string(FakeIMM(text.encode('utf-16-le')),1,8),text)

    def test_partial_or_grown_buffer_is_not_a_shorter_reading(self):
        for size,got in ((4,2),(4,6),(4,-1),(4,0),(3,3)):
            with self.subTest(size=size,got=got):
                self.assertEqual(I._composition_string(FakeIMM('確認'.encode('utf-16-le'),size,got),1,8),'')

    def test_unpaired_surrogate_is_not_silently_deleted(self):
        self.assertEqual(I._composition_string(FakeIMM(b'\x3d\xd8\x41\x00'),1,8),'')

    def test_negative_native_status_is_unknown_not_inactive(self):
        for status in (-1,-2):
            fake=FakeIMM(size=status)
            with patch.object(I,'HAS_SUPPORT',True),patch.object(I,'_imm32',return_value=fake):
                self.assertIsNone(I.composition_active(3))
            self.assertEqual(fake.releases,[(3,0x123456789)])

    def test_inactive_and_active_are_distinct(self):
        for size,expected in ((0,False),(4,True)):
            with patch.object(I,'HAS_SUPPORT',True),patch.object(I,'_imm32',return_value=FakeIMM(size=size)):
                self.assertIs(I.composition_active(3),expected)

    def test_context_is_released_after_read_failure(self):
        fake=FakeIMM()
        fake.ImmGetCompositionStringW=lambda *args: (_ for _ in ()).throw(OSError('lost context'))
        with patch.object(I,'HAS_SUPPORT',True),patch.object(I,'_imm32',return_value=fake):
            result=I.read_composition(3)
        self.assertEqual(set(result),{name for name,index in I.COMPOSITION_FIELDS})
        self.assertTrue(all(value=='' for value in result.values()))
        self.assertEqual(fake.releases,[(3,0x123456789)])

    @unittest.skipUnless(I.HAS_SUPPORT,'Windows IMM signatures')
    def test_native_handle_return_type_is_pointer_sized(self):
        imm=I._imm32()
        self.assertEqual(C.sizeof(imm.ImmGetContext.restype),C.sizeof(C.c_void_p))
        self.assertEqual(C.sizeof(imm.ImmCreateContext.restype),C.sizeof(C.c_void_p))
        self.assertEqual(C.sizeof(imm.ImmGetCompositionStringW.restype),4)


class IMMResultClauseTests(unittest.TestCase):
    def array(self,*offsets):
        import struct
        return struct.pack('<'+'I'*len(offsets),*offsets)

    def test_native_utf16_units_are_decoded_before_python_slicing(self):
        left=I._composition_clauses(FakeIMM(self.array(0,2,4)),1,I.GCS_RESULTCLAUSE,'😀確認')
        right=I._composition_clauses(FakeIMM(self.array(0,3,7)),1,I.GCS_RESULTREADCLAUSE,'えがおかくにん')
        self.assertEqual(left,(0,1,3));self.assertEqual(right,(0,3,7))
        self.assertEqual(I.result_clause_pairs('😀確認','えがおかくにん',left,right),
                         (('😀','えがお'),('確認','かくにん')))

    def test_invalid_native_arrays_do_not_supply_guessed_boundaries(self):
        for data in (b'',b'abc',self.array(1,4),self.array(0,1,4),
                     self.array(0,2,2,4),self.array(0,4,2),self.array(0,3),
                     self.array(*range(66))):
            self.assertEqual(I._composition_clauses(FakeIMM(data),1,4096,'😀確認'),())
        data=self.array(0,2,4)
        for got in (-1,0,8,16):
            self.assertEqual(I._composition_clauses(FakeIMM(data,got=got),1,4096,'😀確認'),())
        self.assertFalse(I.result_clause_pairs('確認資料','かくにんしりょう',(0,2,4),(0,8)))
        self.assertFalse(I.result_clause_pairs('確認','かくにん',(1,2),(0,4)))
        # A split between a halfwidth base and its dakuten cannot invent
        # different normalized phonetic pieces.
        self.assertFalse(I.result_clause_pairs('二字','ﾊﾟ',(0,1,2),(0,1,2)))

    def test_optional_arrays_use_same_context_and_never_discard_result_pair(self):
        import struct
        values={I.GCS_RESULTSTR:'確認資料'.encode('utf-16-le'),
                I.GCS_RESULTREADSTR:'ｶｸﾆﾝｼﾘｮｳ'.encode('utf-16-le'),
                I.GCS_RESULTCLAUSE:self.array(0,2,4),
                I.GCS_RESULTREADCLAUSE:self.array(0,4,8)}
        class Multi(FakeIMM):
            def __init__(self):super().__init__();self.queries=[]
            def ImmGetCompositionStringW(self,himc,index,buffer,size):
                self.queries.append(index);data=values.get(index,b'')
                if buffer is None:return len(data)
                C.memmove(buffer,data,min(size,len(data)));return len(data)
        fake=Multi()
        with patch.object(I,'HAS_SUPPORT',True),patch.object(I,'_imm32',return_value=fake):
            plain=I.read_composition(3)
            self.assertNotIn('result_clauses',plain)
            self.assertNotIn(I.GCS_RESULTCLAUSE,fake.queries)
            detailed=I.read_composition(3,result_clauses=True)
            self.assertEqual(detailed['result_clauses'],(('確認','ｶｸﾆﾝ'),('資料','ｼﾘｮｳ')))
            values[I.GCS_RESULTREADCLAUSE]=b'bad'
            missing=I.read_composition(3,result_clauses=True)
            self.assertFalse(missing['result_clauses'])
            self.assertEqual(missing['result'],'確認資料')
            self.assertEqual(missing['result_reading'],'ｶｸﾆﾝｼﾘｮｳ')
        self.assertEqual(fake.releases,[(3,0x123456789)]*3)


if __name__=='__main__':unittest.main()
