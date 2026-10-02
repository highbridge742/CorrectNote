# -*- coding: utf-8 -*-
"""Read-only Windows TSF search-candidate evidence used by correction.

The list is a search/prediction interface, not a promise about the normal
conversion's first committed result. Callers retain source anomaly and
candidate grammar/meaning checks. Nothing calls SetResult or sends keys.
"""
import ctypes as C
from ctypes import wintypes as W
import uuid


class GUID(C.Structure):
    _fields_ = (("Data1", C.c_uint32), ("Data2", C.c_uint16),
                ("Data3", C.c_uint16), ("Data4", C.c_ubyte * 8))


def _guid(value):
    return GUID.from_buffer_copy(uuid.UUID(value).bytes_le)


HRESULT = C.c_int32


class _UnavailableFunction:
    """Optional Windows calls fail explicitly while the module stays importable."""
    def __call__(self, *args):
        raise OSError('Windows COM is unavailable on this platform')


class _UnavailableLibrary:
    def __getattr__(self, name):
        function = _UnavailableFunction()
        setattr(self, name, function)
        return function


try:
    _ole32 = C.OleDLL("ole32")
    _oleaut32 = C.WinDLL("oleaut32")
except (AttributeError, OSError):
    _ole32 = _UnavailableLibrary()
    _oleaut32 = _UnavailableLibrary()
_ole32.CoInitializeEx.argtypes = (C.c_void_p, W.DWORD)
_ole32.CoInitializeEx.restype = HRESULT
_ole32.CoUninitialize.argtypes = ()
_ole32.CoCreateInstance.argtypes = (C.POINTER(GUID), C.c_void_p, W.DWORD,
                                    C.POINTER(GUID), C.POINTER(C.c_void_p))
_ole32.CoCreateInstance.restype = HRESULT
_oleaut32.SysAllocString.argtypes = (W.LPCWSTR,)
_oleaut32.SysAllocString.restype = C.c_void_p
_oleaut32.SysFreeString.argtypes = (C.c_void_p,)


def _method(pointer, index, *types):
    table = C.cast(pointer, C.POINTER(C.POINTER(C.c_void_p))).contents
    return C.WINFUNCTYPE(HRESULT, C.c_void_p, *types)(table[index])


def _release(pointer):
    if pointer:
        _method(pointer, 2)(pointer)


class SearchCandidates:
    """Use on the same COM apartment/thread from enter through exit."""

    def __init__(self):
        self._manager = C.c_void_p()
        self._provider = C.c_void_p()
        self._search = C.c_void_p()
        self._com = False
        self._active = False
        self.available = False
        self.error = None
        self._owner = None
        self._retained = False

    def __enter__(self):
        from ime_session import retain
        shared,self._retained=retain(self)
        if shared is not self or self._com:return shared
        from threading import get_ident
        self._owner=get_ident()
        try:
            hr = _ole32.CoInitializeEx(None, 2)  # STA
            if hr < 0:
                self.error = "CoInitializeEx 0x%08x" % (hr & 0xffffffff)
                return self
            self._com = True
            hr = _ole32.CoCreateInstance(
                C.byref(_guid("529a9e6b-6587-4f23-ab9e-9c7d683e3c50")),
                None, 1, C.byref(_guid("aa80e801-2021-11d2-93e0-0060b067b86e")),
                C.byref(self._manager))
            if hr < 0 or not self._manager:
                self.error = "ThreadMgr 0x%08x" % (hr & 0xffffffff)
                return self
            client = W.DWORD()
            hr = _method(self._manager, 3, C.POINTER(W.DWORD))(
                self._manager, C.byref(client))
            if hr < 0:
                self.error = "Activate 0x%08x" % (hr & 0xffffffff)
                return self
            self._active = True
            hr = _method(self._manager, 11, C.POINTER(GUID), C.POINTER(C.c_void_p))(
                self._manager,
                C.byref(_guid("03b5835f-f03c-411b-9ce2-aa23e1171e36")),
                C.byref(self._provider))
            if hr < 0 or not self._provider:
                self.error = "Japanese provider 0x%08x" % (hr & 0xffffffff)
                return self
            hr = _method(self._provider, 5, C.POINTER(GUID), C.POINTER(GUID),
                         C.POINTER(C.c_void_p))(
                self._provider,
                C.byref(_guid("00000000-0000-0000-0000-000000000000")),
                C.byref(_guid("87a2ad8f-f27b-4920-8501-67602280175d")),
                C.byref(self._search))
            if hr < 0 or not self._search:
                self.error = "Search function 0x%08x" % (hr & 0xffffffff)
                return self
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
        search,provider,manager=self._search,self._provider,self._manager
        active,com=self._active,self._com
        self._search=C.c_void_p();self._provider=C.c_void_p();self._manager=C.c_void_p()
        self._active=self._com=self.available=False
        self._owner=None;self._retained=False
        actions=[lambda:_release(search),lambda:_release(provider)]
        if active:actions.append(lambda:_method(manager,4)(manager))
        actions.append(lambda:_release(manager))
        if com:actions.append(_ole32.CoUninitialize)
        error=cleanup(actions)
        if error and self.error is None:self.error='IME cleanup: '+error

    def candidates(self, reading):
        """Return tuple on success, None for unavailable/unsupported query."""
        from threading import get_ident
        if not self.available or self._owner!=get_ident() or not reading:
            return None
        query = _oleaut32.SysAllocString(reading)
        application = _oleaut32.SysAllocString("")
        listing = C.c_void_p()
        try:
            hr = _method(self._search, 4, C.c_void_p, C.c_void_p,
                         C.POINTER(C.c_void_p))(
                self._search, query, application, C.byref(listing))
            if hr < 0 or not listing:
                return None
            count = W.ULONG()
            hr = _method(listing, 5, C.POINTER(W.ULONG))(
                listing, C.byref(count))
            if hr < 0:
                return None
            output = []
            for index in range(count.value):
                item = C.c_void_p()
                value = C.c_void_p()
                try:
                    hr = _method(listing, 4, W.ULONG, C.POINTER(C.c_void_p))(
                        listing, index, C.byref(item))
                    if hr < 0 or not item:
                        continue
                    hr = _method(item, 3, C.POINTER(C.c_void_p))(
                        item, C.byref(value))
                    if hr >= 0 and value:
                        output.append(C.wstring_at(value))
                finally:
                    if value:
                        _oleaut32.SysFreeString(value)
                    _release(item)
            return tuple(output)
        finally:
            _release(listing)
            _oleaut32.SysFreeString(query)
            _oleaut32.SysFreeString(application)
