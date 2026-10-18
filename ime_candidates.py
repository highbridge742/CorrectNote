# -*- coding: utf-8 -*-
"""Read-only Windows TSF search-candidate evidence used by correction.

The list is a search/prediction interface, not a promise about the normal
conversion's first committed result. Callers retain source anomaly and
candidate grammar/meaning checks. Nothing calls SetResult or sends keys.
"""
import ctypes as C
from ctypes import wintypes as W
import sys
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


def _faulting_thread_reports_only():
    """Keep an enabled faulthandler from walking other threads during COM use.

    On Windows, faulthandler reports every first-chance SEH exception. COM
    raises and handles RPC errors itself while these IME objects are released
    (0x8001010E on the calling thread, 0x80010108 on an RPC thread). With
    all_threads=True the handler then reads the frames of running Python
    threads from that native thread, can fault there (access violation) and
    kill a process whose COM call had succeeded. Ordinary CorrectNote runs
    never enable faulthandler; tests and measurements (-X faulthandler, which
    multiprocessing passes to the analysis child, or faulthandler.enable())
    do. Their reports stay, for the faulting Python thread only (2026-10-15).
    """
    if sys.platform != 'win32':
        return
    try:
        import faulthandler
        if not faulthandler.is_enabled():
            return
    except Exception:
        return
    for target in (sys.stderr, sys.__stderr__):
        try:
            faulthandler.enable(file=target, all_threads=False)
            return
        except Exception:
            continue
    try:
        faulthandler.disable()
    except Exception:
        pass



class _ThreadManagerConnection:
    """Native connection only; never retains a query or candidate tuple."""
    def __init__(self,owner,manager,active,com):
        self.owner=owner;self.manager=manager;self.active=active;self.com=com
    def close(self):
        from threading import get_ident
        from ime_session import cleanup
        if self.owner!=get_ident():raise RuntimeError('IME resources belong to another thread')
        manager,active,com=self.manager,self.active,self.com
        self.manager=C.c_void_p();self.active=self.com=False
        actions=[]
        if active:actions.append(lambda:_method(manager,4)(manager))
        actions.append(lambda:_release(manager))
        if com:actions.append(_ole32.CoUninitialize)
        return cleanup(actions)


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
        self._candidate_cache = {}
        self._connection = None
        self._connection_owner = None
        self._connection_bad = False

    def __enter__(self):
        _faulting_thread_reports_only()
        from analysis_context import check_current_request
        check_current_request()
        from ime_session import retain
        shared,self._retained=retain(self)
        if shared is not self or self._com:return shared
        from threading import get_ident
        self._owner=get_ident()
        from tsf_worker import current_owner
        owner=current_owner()
        connection=owner.borrow() if owner is not None else None
        try:
            if connection is not None:
                self._manager=connection.manager
                self._active=connection.active;self._com=connection.com
                self._connection=connection;self._connection_owner=owner
            else:
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
            check_current_request()
            self.available = True
            if owner is not None and self._connection is None:
                connection=_ThreadManagerConnection(self._owner,self._manager,self._active,self._com)
                owner.publish(connection)
                self._connection=connection;self._connection_owner=owner
        except Exception as exc:
            self.error = repr(exc)
        except BaseException:
            self._connection_bad=True
            self.close()
            raise
        return self

    def __exit__(self, *exc):
        if exc and exc[0] is not None:self._connection_bad=True
        if not self._retained:self.close()

    def close(self):
        from threading import get_ident
        from ime_session import cleanup
        if self._owner is not None and self._owner!=get_ident():
            raise RuntimeError('IME resources belong to another thread')
        search,provider,manager=self._search,self._provider,self._manager
        active,com=self._active,self._com
        connection,owner=self._connection,self._connection_owner
        discard=self._connection_bad or not self.available
        self._connection=None;self._connection_owner=None;self._connection_bad=False
        if connection is not None:
            manager=C.c_void_p();active=com=False
        self._search=C.c_void_p();self._provider=C.c_void_p();self._manager=C.c_void_p()
        self._active=self._com=self.available=False
        self._owner=None;self._retained=False
        self._candidate_cache.clear()
        actions=[lambda:_release(search),lambda:_release(provider)]
        if active:actions.append(lambda:_method(manager,4)(manager))
        actions.append(lambda:_release(manager))
        if com:actions.append(_ole32.CoUninitialize)
        error=cleanup(actions)
        if error and self.error is None:self.error='IME cleanup: '+error
        if connection is not None and (discard or error):owner.discard(connection)

    def candidates(self, reading):
        """Return tuple on success, None for unavailable/unsupported query."""
        from threading import get_ident
        if not self.available or self._owner!=get_ident() or not reading:
            return None
        from analysis_context import check_current_request
        check_current_request()
        cache=self._candidate_cache if self._retained else None
        if cache is not None and reading in cache:return cache[reading]
        kept=None
        if cache is not None:
            from ime_session import line_answers
            kept=line_answers()
            if kept is not None:
                hits=kept.get(('candidates',reading))
                if hits is not None:
                    cache[reading]=hits
                    return hits
        query = _oleaut32.SysAllocString(reading)
        application = _oleaut32.SysAllocString("")
        listing = C.c_void_p()
        result=None;complete=False
        try:
            hr = _method(self._search, 4, C.c_void_p, C.c_void_p,
                         C.POINTER(C.c_void_p))(
                self._search, query, application, C.byref(listing))
            if hr >= 0 and listing:
                complete=(hr==0)
                count = W.ULONG()
                hr = _method(listing, 5, C.POINTER(W.ULONG))(
                    listing, C.byref(count))
                if hr >= 0:
                    complete=complete and hr==0
                    output = []
                    for index in range(count.value):
                        item = C.c_void_p()
                        value = C.c_void_p()
                        try:
                            hr = _method(listing, 4, W.ULONG, C.POINTER(C.c_void_p))(
                                listing, index, C.byref(item))
                            if hr < 0 or not item:
                                complete=False
                                continue
                            complete=complete and hr==0
                            hr = _method(item, 3, C.POINTER(C.c_void_p))(
                                item, C.byref(value))
                            if hr >= 0 and value:
                                output.append(C.wstring_at(value))
                            complete=complete and hr==0 and bool(value)
                        finally:
                            if value:
                                _oleaut32.SysFreeString(value)
                            _release(item)
                    result=tuple(output)
        finally:
            if result is None or not complete:self._connection_bad=True
            _release(listing)
            _oleaut32.SysFreeString(query)
            _oleaut32.SysFreeString(application)
        # Releasing the native listing can outlive the request too. Publish
        # neither a successful tuple nor an unavailable result until cleanup
        # has finished and the owner has checked the current request again.
        check_current_request()
        if cache is not None and result is not None and complete:
            cache[reading]=result
            if kept is not None:kept.put(('candidates',reading),result)
        return result
