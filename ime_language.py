# -*- coding: utf-8 -*-
"""Read-only Microsoft Japanese IME first conversion and phonetic reading.

Uses the documented IFELanguage interface through the installed IFECommon
factory. No key events, commits, SetResult, or dictionary writes occur.
"""
import ctypes as C

from ime_candidates import GUID, HRESULT, _guid, _method, _ole32, _oleaut32, _release

_imeapi_path = r'C:\Windows\System32\IME\IMEJP\IMJPAPI.DLL'
try:
    _imeapi = C.WinDLL(_imeapi_path)
    _factory = _imeapi.CreateIFECommonInstance
    _factory.argtypes = (C.POINTER(C.c_void_p),)
    _factory.restype = HRESULT
except (OSError, AttributeError):
    _imeapi = None
    _factory = None

_oleaut32.SysStringLen.argtypes = (C.c_void_p,)
_oleaut32.SysStringLen.restype = C.c_uint
_ole32.CoTaskMemFree.argtypes = (C.c_void_p,)
_ole32.CoTaskMemFree.restype = None


class _WDD(C.Structure):
    _pack_ = 1
    _fields_ = (('display_pos', C.c_ushort), ('reading_pos', C.c_ushort),
                ('display_len', C.c_ushort), ('reading_len', C.c_ushort),
                ('reserved_number', C.c_uint32), ('pos', C.c_ushort),
                ('flags', C.c_ushort), ('reserved_pointer', C.c_void_p))


class _MORRSLT(C.Structure):
    _pack_ = 1
    _fields_ = (('size', C.c_uint32), ('output', C.c_void_p),
                ('output_len', C.c_ushort), ('reading', C.c_void_p),
                ('reading_len', C.c_ushort), ('input_positions', C.c_void_p),
                ('output_words', C.c_void_p), ('reading_words', C.c_void_p),
                ('mono_ruby', C.c_void_p), ('words', C.POINTER(_WDD)),
                ('word_count', C.c_int), ('private', C.c_void_p))


_LANGUAGE_ID = _guid('019f7152-e6db-11d0-83c3-00c04fddb82e')


from ime_readings import utf16_positions as _utf16_positions


def _decode_morph_result(address,source_units):
    """Decode only the strings and descriptors inside the SDK-owned block.

    MORRSLT.dwSize covers every returned member (msime.h). Reserved WDD
    bits are not evidence. Offsets stay in UTF-16 until both string maps
    prove that each endpoint is a complete Python character boundary.
    """
    if not address:return None
    size=C.c_uint32.from_address(address).value
    header=C.sizeof(_MORRSLT)
    if size<header:return None
    row=C.cast(address,C.POINTER(_MORRSLT)).contents
    def bounded(pointer,length):
        return bool(pointer and 0<=length<=size-header
                    and address+header<=pointer<=address+size-length)
    word_address=C.cast(row.words,C.c_void_p).value
    if (not 1<=row.word_count<=source_units*4
            or not bounded(row.output,row.output_len*2)
            or not bounded(row.reading,row.reading_len*2)
            or not bounded(word_address,row.word_count*C.sizeof(_WDD))):return None
    output=C.string_at(row.output,row.output_len*2).decode('utf-16-le')
    reading=C.string_at(row.reading,row.reading_len*2).decode('utf-16-le')
    output_positions=_utf16_positions(output);reading_positions=_utf16_positions(reading)
    words=[]
    for index in range(row.word_count):
        word=row.words[index]
        coordinates=(output_positions.get(word.display_pos),
            output_positions.get(word.display_pos+word.display_len),
            reading_positions.get(word.reading_pos),
            reading_positions.get(word.reading_pos+word.reading_len))
        if any(value is None for value in coordinates):return None
        words.append(coordinates+(word.pos,word.flags & 0x3f))
    if (words[0][0]!=0 or words[0][2]!=0
            or words[-1][1]!=len(output) or words[-1][3]!=len(reading)
            or any(a[1]!=b[0] or a[3]!=b[2] for a,b in zip(words,words[1:]))):return None
    return output,reading,tuple(words)


def _source_aligned_spaces(result, source):
    """Restore a width-normalized space only at its own one-character word.

    The native interface can return U+3000 for an input U+0020. Both sides
    must retain the same Python character positions, and its descriptor
    must pair one source space with one output space. Other normalization
    still supplies no evidence of the original input.
    """
    if not result:return None
    output,original,words=result
    if original==source:return result
    if len(original)!=len(source):return None
    edits=[]
    for index,(got,wanted) in enumerate(zip(original,source)):
        if got==wanted:continue
        if {got,wanted}!={' ', '\u3000'}:return None
        spans=[(a,b) for a,b,c,d,pos,flags in words if (c,d)==(index,index+1)]
        if len(spans)!=1:return None
        a,b=spans[0]
        if b-a!=1 or output[a:b] not in (' ','\u3000'):return None
        edits.append((a,wanted))
    chars=list(output)
    for index,space in edits:chars[index]=space
    return ''.join(chars),source,words


class JapaneseIME:
    """Use within one COM apartment; failure leaves positive clues unavailable."""

    def __init__(self):
        self._common = C.c_void_p()
        self._language = C.c_void_p()
        self._com = False
        self._open = False
        self.available = False
        self.error = None
        self._owner = None
        self._retained = False
        self._text_cache = {}

    def __enter__(self):
        from ime_session import retain
        shared,self._retained=retain(self)
        if shared is not self or self._com:return shared
        from threading import get_ident
        self._owner=get_ident()
        if _factory is None:
            self.error = 'IFECommon factory unavailable'
            return self
        try:
            hr = _ole32.CoInitializeEx(None, 2)
            if hr < 0:
                self.error = 'CoInitializeEx 0x%08x' % (hr & 0xffffffff)
                return self
            self._com = True
            hr = _factory(C.byref(self._common))
            if hr < 0 or not self._common:
                self.error = 'CreateIFECommonInstance 0x%08x' % (hr & 0xffffffff)
                return self
            hr = _method(self._common, 0, C.POINTER(GUID),
                         C.POINTER(C.c_void_p))(
                self._common, C.byref(_LANGUAGE_ID), C.byref(self._language))
            if hr < 0 or not self._language:
                self.error = 'QueryIFELanguage 0x%08x' % (hr & 0xffffffff)
                return self
            hr = _method(self._language, 3)(self._language)
            if hr < 0:
                self.error = 'IFELanguage.Open 0x%08x' % (hr & 0xffffffff)
                return self
            self._open = True
            self.available = True
        except Exception as exc:
            self.error = repr(exc)
        return self

    def __exit__(self, *_):
        if not self._retained:self.close()

    def close(self):
        from threading import get_ident
        from ime_session import cleanup
        if self._owner is not None and self._owner!=get_ident():
            raise RuntimeError('IME resources belong to another thread')
        language,common,opened,com=self._language,self._common,self._open,self._com
        self._language=C.c_void_p();self._common=C.c_void_p()
        self._open=self._com=self.available=False
        self._owner=None;self._retained=False
        self._text_cache.clear()
        actions=[]
        if opened:actions.append(lambda:_method(language,4)(language))
        actions.extend((lambda:_release(language),lambda:_release(common)))
        if com:actions.append(_ole32.CoUninitialize)
        error=cleanup(actions)
        if error and self.error is None:self.error='IME cleanup: '+error

    def _text(self, value, method_index):
        from threading import get_ident
        if not self.available or self._owner!=get_ident() or not value:
            return None
        # Reuse successful strings only inside the owned correction scope.
        # Outside that scope each query observes the native interface again.
        from analysis_context import check_current_request
        check_current_request()
        cache=self._text_cache if self._retained else None
        key=(method_index,value)
        if cache is not None and key in cache:return cache[key]
        source = _oleaut32.SysAllocString(value)
        result = C.c_void_p()
        try:
            hr = _method(self._language, method_index, C.c_void_p,
                         C.c_long, C.c_long, C.POINTER(C.c_void_p))(
                self._language, source, 1, -1, C.byref(result))
            if hr < 0 or not result:
                return None
            text=C.wstring_at(result, _oleaut32.SysStringLen(result))
            if cache is not None:cache[key]=text
            return text
        except Exception:
            return None
        finally:
            if result:
                _oleaut32.SysFreeString(result)
            if source:
                _oleaut32.SysFreeString(source)

    def _morph(self, source, request):
        """Return strings and word ranges in Python character coordinates."""
        from threading import get_ident
        if not self.available or self._owner!=get_ident() or not source:
            return None
        from analysis_context import check_current_request
        check_current_request()
        result=C.c_void_p()
        try:
            source_units=len(source.encode('utf-16-le'))//2
            if source_units>0xffff:return None
            hr=_method(self._language, 5, C.c_uint32, C.c_uint32,
                       C.c_int, C.c_wchar_p, C.c_void_p,
                       C.POINTER(C.c_void_p))(
                self._language, request, 0, source_units, source,
                None, C.byref(result))
            if hr!=0 or not result:return None
            return _decode_morph_result(result.value,source_units)
        except (ValueError,UnicodeError,OSError,AttributeError):
            return None
        finally:
            if result:_ole32.CoTaskMemFree(result)

    def reverse_words(self, surface):
        """Return (full reading, source-aligned IME word descriptors)."""
        result=_source_aligned_spaces(self._morph(surface,0x00030000),surface)
        if not result:return None
        phonetic,original,words=result
        return phonetic,tuple((c,d,a,b,pos,flags) for a,b,c,d,pos,flags in words)

    def convert_words(self, reading):
        """First conversion with the actual supplied reading, not an inverse guess.

        GetJMorphResult can normalize a mixed input (for example an emoji's
        spoken name). Such a result does not attest our original reading.
        """
        result=_source_aligned_spaces(self._morph(reading,0x00010000),reading)
        if not result:return None
        return result[0],result[2]

    def phonetic(self, surface):
        """Read the IME's own phonetic interpretation of written text."""
        return self._text(surface, 7)

    def convert(self, reading):
        """Get the full first conversion of hypothetical phonetic text."""
        return self._text(reading, 8)
