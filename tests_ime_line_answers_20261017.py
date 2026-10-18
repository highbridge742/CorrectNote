# -*- coding: utf-8 -*-
"""Native IME answers kept per typed line across corrections (2026-10-17, speed).

Nothing is kept unless the analysis worker opened ime_session.line_answers_scope.
Inside it, the next correction of the same line (typed further or edited in
place) reuses the answers for text that is still there. Written text read back
for the first time names readings the user just committed; their stored forward
answers are asked again, because the native IME learns from commits.
"""
from contextlib import contextmanager
from threading import get_ident
from unittest.mock import patch
import ctypes as C
import unittest
import ime_session as P
import ime_language as L
import ime_candidates as S
from analysis_work import current_input
from tests_ime_language import MorphologyBufferTests
import tests_search_candidate_cache as F


@contextmanager
def text_native(answers,calls):
    """Fake IFELanguage string methods (7 phonetic, 8 convert) and BSTRs,
    so the same test runs where oleaut32 is unavailable."""
    answers=iter(answers);buffers=[];lengths={}
    def allocate(value):
        buffer=C.create_unicode_buffer(value);buffers.append(buffer)
        # SysStringLen counts wchar_t units: UTF-16 units on Windows (an emoji
        # is two), Python characters where wchar_t is 32 bits.
        units=len(value) if C.sizeof(C.c_wchar)==4 else len(value.encode('utf-16-le'))//2
        address=C.addressof(buffer);lengths[address]=units;return address
    def method(pointer,index,*signature):
        def query(language,source,start,end,output):
            calls.append((index,C.wstring_at(source)));answer=next(answers)
            if answer is None:return -1
            output._obj.value=allocate(answer)
            return 0
        return query
    with patch.object(L,'_method',side_effect=method), \
         patch.object(L._oleaut32,'SysAllocString',side_effect=allocate), \
         patch.object(L._oleaut32,'SysStringLen',side_effect=lambda p:lengths[p.value if hasattr(p,'value') else p]), \
         patch.object(L._oleaut32,'SysFreeString'):
        yield


@contextmanager
def morph_native(calls):
    """Fake GetJMorphResult: every answer is the fixture block 😀確認/にやりかくにん."""
    buffers=[]
    def method(pointer,index,*signature):
        def native(language,request,mode,units,source,unused,output):
            calls.append((request,source))
            allocation,address,row=MorphologyBufferTests().block();buffers.append(allocation)
            output._obj.value=address
            return 0
        return native
    with patch.object(L,'_method',side_effect=method),patch.object(L._ole32,'CoTaskMemFree'):yield


def owned_ime():
    obj=L.JapaneseIME();obj.available=True;obj._owner=get_ident();obj._retained=True
    return obj


class SameTypingTests(unittest.TestCase):
    def test_typed_further_or_edited_in_place_is_the_same_line(self):
        same=P._same_typing
        self.assertTrue(same('資料を','資料を確認'))
        self.assertTrue(same('資料を確認','資料を'))
        self.assertTrue(same('今日は雨','今日も雨'))
        self.assertTrue(same('資料を確認する','資料をもう確認する'))
        self.assertTrue(same('資料','資料'))

    def test_another_text_is_another_line(self):
        same=P._same_typing
        self.assertFalse(same('資料を確認','明日の会議'))
        self.assertFalse(same('資料を確認','確'))
        self.assertFalse(same('あいうえお','かきくけこ'))


class LineAnswerStoreTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNone(P._LINE_STORES)

    def test_nothing_is_kept_unless_the_worker_enables_it(self):
        calls=[]
        with text_native(('資料','資料'),calls):
            for unused in range(2):
                with current_input('資料を確認'),P.resource_scope():
                    with owned_ime() as ime:
                        P.retain(ime)
                        self.assertEqual(ime.convert('しりょう'),'資料')
                        self.assertEqual(ime.convert('しりょう'),'資料')
        self.assertEqual(calls,[(8,'しりょう')]*2)
        self.assertIsNone(P.line_answers())

    def test_same_line_typed_further_reuses_text_answers(self):
        calls=[]
        with P.line_answers_scope(),text_native(('資料','資料','資料'),calls):
            with current_input('資料を'),P.resource_scope():
                with owned_ime() as ime:
                    P.retain(ime);self.assertEqual(ime.convert('しりょう'),'資料')
            with current_input('資料を確認'),P.resource_scope():
                with owned_ime() as ime:
                    P.retain(ime);self.assertEqual(ime.convert('しりょう'),'資料')
                    # A new string of the same line is a native query once.
                    self.assertEqual(ime.phonetic('資料'),'資料')
            self.assertEqual(calls,[(8,'しりょう'),(7,'資料')])
            with current_input('明日の会議'),P.resource_scope():
                with owned_ime() as ime:
                    P.retain(ime);self.assertEqual(ime.convert('しりょう'),'資料')
            self.assertEqual(calls,[(8,'しりょう'),(7,'資料'),(8,'しりょう')])
        self.assertIsNone(P._LINE_STORES)

    def test_no_current_line_or_unowned_query_keeps_nothing(self):
        calls=[]
        with P.line_answers_scope(),text_native(('資料',)*4,calls):
            for unused in range(2):
                with P.resource_scope():
                    with owned_ime() as ime:
                        P.retain(ime);self.assertEqual(ime.convert('しりょう'),'資料')
            self.assertEqual(len(calls),2)
            with current_input('資料を'):
                ime=owned_ime();ime._retained=False
                self.assertEqual(ime.convert('しりょう'),'資料')
                self.assertEqual(ime.convert('しりょう'),'資料')
                ime._owner=None
            self.assertEqual(len(calls),4)
            self.assertEqual(P._LINE_STORES,[])

    def test_empty_success_is_kept_too(self):
        calls=[]
        with P.line_answers_scope(),text_native(('',),calls):
            for line in ('資料を','資料を確認'):
                with current_input(line),P.resource_scope():
                    with owned_ime() as ime:
                        P.retain(ime);self.assertEqual(ime.convert('しりょう'),'')
        self.assertEqual(calls,[(8,'しりょう')])

    def test_morph_answers_are_kept_and_a_first_inverse_drops_forward_answers_of_its_readings(self):
        text_calls=[];morph_calls=[]
        with P.line_answers_scope():
            with current_input('😀確認を'),P.resource_scope():
                with owned_ime() as ime:
                    P.retain(ime)
                    with text_native(('😀確認','確認','資料'),text_calls):
                        self.assertEqual(ime.convert('にやりかくにん'),'😀確認')
                        self.assertEqual(ime.convert('かくにん'),'確認')
                        self.assertEqual(ime.convert('しりょう'),'資料')
                    with morph_native(morph_calls):
                        forward=ime._morph('にやりかくにん',0x10000)
                        self.assertIsNotNone(forward)
            store=P._LINE_STORES[0]
            self.assertEqual(sorted(k for k in store.answers if k[0]=='text'),
                             [('text',8,'かくにん'),('text',8,'しりょう'),('text',8,'にやりかくにん')])
            with current_input('😀確認を😀確認'),P.resource_scope():
                with owned_ime() as ime:
                    P.retain(ime)
                    with morph_native(morph_calls):
                        # Forward words of the same line: no native query.
                        self.assertEqual(ime._morph('にやりかくにん',0x10000),forward)
                        self.assertEqual(morph_calls,[(0x10000,'にやりかくにん')])
                        # Written text read back for the first time names the
                        # readings にやりかくにん (whole) and にやり・かくにん (words).
                        inverse=ime._morph('😀確認',0x30000)
                        self.assertEqual(inverse[1],'にやりかくにん')
                    self.assertEqual(sorted(k for k in store.answers if k[0]=='text'),
                                     [('text',8,'しりょう')])
                    self.assertNotIn(('morph',0x10000,'にやりかくにん'),store.answers)
                    self.assertIn(('morph',0x30000,'😀確認'),store.answers)
                    with text_native(('😀確認',),text_calls):
                        self.assertEqual(ime.convert('にやりかくにん'),'😀確認')
                        self.assertEqual(ime.convert('しりょう'),'資料')
            self.assertEqual(text_calls,[(8,'にやりかくにん'),(8,'かくにん'),(8,'しりょう'),(8,'にやりかくにん')])
            with current_input('😀確認を😀確認した'),P.resource_scope():
                with owned_ime() as ime:
                    P.retain(ime)
                    with morph_native(morph_calls):
                        # The same written text read back again is not new.
                        self.assertEqual(ime._morph('😀確認',0x30000),inverse)
                    self.assertEqual(morph_calls,[(0x10000,'にやりかくにん'),(0x30000,'😀確認')])
                    with text_native((),text_calls):
                        self.assertEqual(ime.convert('にやりかくにん'),'😀確認')

    def test_candidate_lists_are_kept_per_line(self):
        fixture=F.SearchCandidateCacheTests()
        with P.line_answers_scope():
            with fixture.native([dict(values=['話します','離します']),dict(values=['別'])]) as native:
                for line in ('はなします','はなしますと'):
                    with current_input(line),P.resource_scope():
                        obj=fixture.resource();P.retain(obj)
                        self.assertEqual(obj.candidates('はなします'),('話します','離します'))
                self.assertEqual(native['queries'],['はなします'])
                with current_input('別の行です'),P.resource_scope():
                    obj=fixture.resource();P.retain(obj)
                    self.assertEqual(obj.candidates('はなします'),('別',))
                self.assertEqual(native['queries'],['はなします','はなします'])
                self.assertCountEqual(native['freed'],native['allocated'])

    def test_incomplete_candidate_listing_is_not_kept(self):
        fixture=F.SearchCandidateCacheTests()
        with P.line_answers_scope():
            with fixture.native([dict(values=['話します','離します'],item_hr=1),dict(values=['話します'])]) as native:
                for line in ('はなします','はなしますと'):
                    with current_input(line),P.resource_scope():
                        obj=fixture.resource();P.retain(obj)
                        obj.candidates('はなします')
                self.assertEqual(native['queries'],['はなします','はなします'])

    def test_a_few_recent_lines_are_kept_apart_and_expire_when_idle(self):
        calls=[]
        lines=['一行目の文','二行目の文章','三行目です','四行目ですね','五行目になる']
        with P.line_answers_scope(),text_native(('資料',)*20,calls):
            for line in lines:
                with current_input(line),P.resource_scope():
                    with owned_ime() as ime:
                        P.retain(ime);ime.convert('しりょう')
            self.assertEqual(len(P._LINE_STORES),P.LINE_STORES_MAX)
            self.assertEqual([store.line for store in P._LINE_STORES],lines[-P.LINE_STORES_MAX:])
            # Background rows interleave with the typed row without losing it.
            with current_input('五行目になるが'),P.resource_scope():
                with owned_ime() as ime:
                    P.retain(ime);ime.convert('しりょう')
            self.assertEqual(len(calls),len(lines))
            self.assertEqual(P._LINE_STORES[-1].line,'五行目になるが')
            later=P._LINE_STORES[-1].used+P.LINE_IDLE+1
            with patch.object(P,'monotonic',return_value=later):
                with current_input('五行目になるが'),P.resource_scope():
                    with owned_ime() as ime:
                        P.retain(ime);ime.convert('しりょう')
            self.assertEqual(len(calls),len(lines)+1)
            self.assertEqual(len(P._LINE_STORES),1)

    def test_a_full_line_store_starts_over(self):
        store=P.LineAnswers('行')
        with patch.object(P,'LINE_ANSWERS_MAX',3):
            for index in range(3):store.put(('text',8,str(index)),index)
            self.assertEqual(len(store.answers),3)
            store.put(('text',8,'x'),1)
            self.assertEqual(list(store.answers),[('text',8,'x')])


if __name__=='__main__':unittest.main()
