# -*- coding: utf-8 -*-
"""Volatile evidence of which document-context entries a completed row read."""
from collections.abc import Mapping


class Reads(Mapping):
    def __init__(self, values):
        self._values=values or {}
        self.keys_read=set()
        self.truth=None
        self.whole=False

    def __getitem__(self,key):
        self.keys_read.add(key)
        return self._values[key]

    def __iter__(self):
        self.whole=True
        return iter(self._values)

    def __len__(self):
        self.whole=True
        return len(self._values)

    def __bool__(self):
        self.truth=bool(self._values)
        return self.truth

    def evidence(self,unit_keys=()):
        return dict(version=1,keys=tuple(sorted(self.keys_read)),truth=self.truth,
                    whole=self.whole,unit_keys=tuple(sorted(unit_keys)))


def compatible(result,previous,current,attested):
    """Unknown evidence falls back to ordinary reanalysis, including disk caches."""
    evidence=(result or {}).get('_context_evidence')
    if not isinstance(evidence,dict) or evidence.get('version')!=1:
        return False
    previous=previous or {};current=current or {}
    if evidence.get('whole') and previous!=current:
        return False
    if evidence.get('truth') is not None and bool(current)!=evidence['truth']:
        return False
    missing=object()
    if any(previous.get(key,missing)!=current.get(key,missing)
           for key in evidence.get('keys',())):
        return False
    return all((key in attested)==present for key,present in evidence.get('unit_keys',()))


class ImeEvidence:
    """A row's IME questions and answers, small in memory; iterates as the (surface, answers) pairs it was made
    from. Nearly all answers are empty (70,000 of 71,000 pairs in 113 rows, 11.6MB: about 83KB a row, by far the
    largest part of a finished row in the main process), so the surfaces with no answer share one string."""
    __slots__=('answered','empty')
    SEPARATOR=chr(0)

    def __init__(self,pairs):
        answered=[];empty=[]
        for surface,values in pairs:
            if values or self.SEPARATOR in surface or not surface:answered.append((surface,values))
            else:empty.append(surface)
        self.answered=tuple(answered);self.empty=self.SEPARATOR.join(empty)

    def __iter__(self):
        yield from self.answered
        if self.empty:
            for surface in self.empty.split(self.SEPARATOR):
                yield surface,()

    def __len__(self):
        return len(self.answered)+(self.empty.count(self.SEPARATOR)+1 if self.empty else 0)

    def __eq__(self,other):
        try:return sorted(self)==sorted(other)
        except TypeError:return NotImplemented

    __hash__=None

    def __getstate__(self):
        return self.answered,self.empty

    def __setstate__(self,state):
        self.answered,self.empty=state


def completed(value):
    """Attach proof only after receiving a completed worker result."""
    result=value['result']
    evidence=value.get('context_evidence')
    if evidence is not None:
        result=dict(result,_context_evidence=evidence)
    if value.get('ime_evidence') is not None:
        result=dict(result,_ime_evidence=ImeEvidence(value['ime_evidence']))
    if value.get('input_signature') is not None:
        result=dict(result,_input_signature=value['input_signature'])
    return result


def signature(nearby=(),readings=(),calculations=(),previous=None):
    part=previous_part(previous)
    return (tuple(nearby),tuple(readings),tuple(calculations))+((part,) if part else ())


# A row that opens on a particle reads the last phrase of the row above (correction_entry.
# _continuation_prefix, 2026-11-02). These two say what that can be without the tokenizer, for the
# parent: same marks as there (tests_previous_line_20261102 holds them together).
_SENTENCE_END='\u3002\uff0e.\uff01\uff1f!?\u300d\u300f\uff09)\u3011'
_CLAUSE_CUT='\u3002\uff0e\u3001\uff0c,\uff01\uff1f!?\t \u3000\u300c\u300e\uff08(\u3010'


def previous_line_of(lines,index):
    """The row above, as correct_line takes it, or None. Source rows, in either layout (the unified view
    projects them, this does not). A row with tab columns has no one row above: its first column does
    not follow the other row's last one."""
    if not 0<index<len(lines):return None
    above=lines[index-1];line=lines[index]
    if not above or '\t' in above or '\t' in line:return None
    return above


def previous_part(previous_line):
    """All of the row above that the answer can depend on: its last phrase, or '' when it ends a sentence
    or a clause. Part of a row's signature, so a row is not reused once this changed."""
    if not previous_line:return ''
    above=previous_line.rstrip('\r\n')
    if not above or above[-1] in _SENTENCE_END or above[-1] in _CLAUSE_CUT:return ''
    return above[max(above.rfind(mark) for mark in _CLAUSE_CUT)+1:]


def reuse_rows(results,todo,previous,signatures,old_context,new_context,attested):
    """Reuse only completed values whose semantic inputs still match exactly."""
    from analysis_cache import reusable_result
    available={}
    for row in previous:
        key=(row or {}).get('_input_signature')
        if (key is not None and reusable_result(row)
                and compatible(row,old_context,new_context,attested)):
            available[(row['original'],key)]=row
    remaining=[]
    for index in todo:
        old=available.get((results[index]['original'],signatures[index]))
        if old is None:remaining.append(index)
        else:results[index]=dict(old)
    return remaining


from contextlib import contextmanager
from contextvars import ContextVar
from threading import get_ident
from time import monotonic

_REQUEST_CHECK=ContextVar('correctnote_request_check',default=None)


class SupersededAnalysis(BaseException):
    """Internal control flow; optional-evidence errors must not swallow it."""


def check_current_request(*,frequent=False):
    scope=_REQUEST_CHECK.get()
    if scope is None or scope[0]!=get_ident():return
    cadence=scope[2]
    if frequent and cadence is not None:
        now=monotonic()
        if cadence[1] is not None and now<cadence[1]:return
        cadence[1]=now+cadence[0]
    if scope[1]():raise SupersededAnalysis()


@contextmanager
def request_scope(check,*,poll_interval=0):
    # Only explicitly frequent checkpoints share this request-local cadence.
    # Entry, semantic boundaries and publication still always check now.
    cadence=[poll_interval,None] if poll_interval>0 else None
    token=_REQUEST_CHECK.set((get_ident(),check,cadence))
    try:yield
    finally:_REQUEST_CHECK.reset(token)
