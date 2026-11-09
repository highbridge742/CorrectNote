# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""控えた詰めた形の表を、ファイルを写像（mmap）して子どうしで共有する（2026-11-07・解析の子の軽さ）。

compact_tables._pickled が控える表（費用の表・語の一覧・読みの格子・分類の表・英単語の種・語の使われやすさ）は、子ごとに同じ中身を
自分のメモリに持っていた（子1つで約80MB、高では子が2〜3つ）。ここでは大きな文字列と数の並びをファイルの
後ろにそのまま置き、読む時はファイルを写像して、その上を直接引く。Windows は写像したファイルの頁を
プロセスどうしで共有し、タスクマネージャーの「メモリ（専用ワーキングセット）」にも入らない。

形: 先頭に印と見出しの長さ、pickle の見出し（大きな str・array を (位置, 長さ) の札に置き換えたもの）、
そのあと8バイトに揃えた中身。大きな str は UTF-8 で置き、_Text が str の代わりをする。位置は全部バイトで
数える（区切りの字 \\x00 \\x01 \\x02 \\n は UTF-8 で1バイトで、多バイトの字の中に現れないので、
str で探すのと同じ所が見つかる）。array は memoryview の cast で同じ型の並びとして引く。

答えは pickle の控えと同じ（同じ鍵・同じ値・同じ順）。読めない・形が違う時は None を返し、呼ぶ側は今まで
どおり作る。CN_TABLE_MMAP=0 で使わない（pickle の控え）。

写像に置くのは、値の文字列と数の並び（位置の並び・費用・格子の数）だけ。鍵の文字列は str のまま持つ: 鍵は
引くたびに探す所で、_Text を通すと40行の解析が約7%遅かった（雲）。値だけなら同じ速さで、子の専用メモリが
3行の解析のあと 386MB → 344MB（雲）。CN_MAP_KEYS=1 で鍵も置く（307MB・遅い、試し用）。
"""
import io
import mmap
import os
import pickle
from array import array

ENV = 'CN_TABLE_MMAP'
_MAGIC = b'CNMAPPED1\n'
# これより小さい str・array は見出しの中にそのまま入れる
_BIG = 1 << 16
_ALIGN = 8
_MAP_KEYS = os.environ.get('CN_MAP_KEYS') == '1'


def enabled():
    return os.environ.get(ENV) != '0'


class _Text:
    """写像したファイルの中の UTF-8 の文字列。compact_tables が blob・values に使う操作だけを持つ。
    位置と長さはバイトで数える（呼ぶ側の位置の並びもバイトで作ってある）。"""
    __slots__ = ('_view', '_mm', '_start', '_end')

    def __init__(self, mm, start, length):
        self._mm = mm
        self._start = start
        self._end = start + length
        self._view = memoryview(mm)[start:start + length]

    def __len__(self):
        return self._end - self._start

    def __getitem__(self, item):
        if type(item) is slice:
            begin, stop = item.start, item.stop
            if item.step is None and begin is not None and stop is not None and 0 <= begin <= stop:
                # compact_tables の切り出し（位置は区切りの直後なので UTF-8 の字の切れ目）
                start = self._start
                return self._mm[start + begin:min(start + stop, self._end)].decode('utf-8')
            return self._view[item].tobytes().decode('utf-8')
        raise TypeError('_Text supports slices only')

    def find(self, sub, start=None, end=None):
        base = self._start
        if start is not None and end is not None and 0 <= start <= end:
            got = self._mm.find(sub.encode('utf-8'), base + start, min(base + end, self._end))
            return got - base if got >= 0 else -1
        n = self._end - base
        start = 0 if start is None else (max(0, start + n) if start < 0 else min(start, n))
        end = n if end is None else (max(0, end + n) if end < 0 else min(end, n))
        got = self._mm.find(sub.encode('utf-8'), base + start, base + end)
        return got - base if got >= 0 else -1

    def rfind(self, sub):
        got = self._mm.rfind(sub.encode('utf-8'), self._start, self._end)
        return got - self._start if got >= 0 else -1

    def endswith(self, suffix):
        data = suffix.encode('utf-8')
        n = len(data)
        return n <= len(self) and self._view[len(self) - n:].tobytes() == data

    def __str__(self):
        return self._view.tobytes().decode('utf-8')

    def split(self, sep=None, maxsplit=-1):
        return str(self).split(sep, maxsplit)

    def __eq__(self, other):
        return str(self) == other if isinstance(other, str) else NotImplemented

    __hash__ = None

    def __reduce__(self):
        return (str, (str(self),))


def _byte_starts(text, sep, chars):
    """区切りの字の直後の位置の並び（字で数えた chars と同じ数）を、UTF-8 のバイトで数え直す。
    数が合わない（区切りでない所の位置）なら None。"""
    import re
    got = array('I', (m.end() for m in re.finditer(re.escape(sep.encode('utf-8')), text.encode('utf-8'))))
    return got if len(got) == len(chars) else None


# 写像の中に置くのは、詰めた形の物の中の文字列と並びだけ（ほかの大きな str は str のまま見出しに入れる）
_MARKED = {}


def _mark(*objects):
    for obj in objects:
        if obj is not None:
            _MARKED[id(obj)] = obj


def _convert(value):
    """compact_tables の物の中の、字で数えた位置の並びをバイトの位置に直した写しを作る（書く時だけ）。
    直せない物（知らない形）は None。"""
    import compact_tables as C
    if isinstance(value, (tuple, list)):
        out = []
        for item in value:
            got = _convert(item)
            if got is None and item is not None:
                return None
            out.append(got)
        return tuple(out) if isinstance(value, tuple) else out
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            got = _convert(item)
            if got is None and item is not None:
                return None
            out[key] = got
        return out
    if value is None or isinstance(value, (str, int, float, bool, bytes, frozenset)):
        return value
    if type(value) is array:
        return value
    if isinstance(value, C._Keys):
        if not _MAP_KEYS:
            # 鍵の文字列は str のまま（引くたびに通る所なので速さを保つ）。位置の並びだけ写像に置く
            _mark(value._starts)
            return value
        keys = C._Keys.__new__(C._Keys)
        keys._blob, keys._sep, keys._sample = value._blob, value._sep, value._sample
        keys._starts = _byte_starts(value._blob, value._sep, value._starts)
        _mark(keys._blob, keys._starts)
        return keys if keys._starts is not None else None
    if isinstance(value, C.CompactWords):
        got = C.CompactWords.__new__(C.CompactWords)
        got._keys = _convert(value._keys)
        return got if got._keys is not None else None
    if isinstance(value, (C.CompactPairs, C.CompactLists, C.CompactStrings)):
        got = type(value).__new__(type(value))
        for name in type(value).__slots__:
            setattr(got, name, getattr(value, name))
        got._keys = _convert(value._keys)
        got._value_starts = _byte_starts(value._values, '\x00', value._value_starts)
        _mark(got._values, got._value_starts, getattr(got, '_order', None))
        return got if got._keys is not None and got._value_starts is not None else None
    if isinstance(value, C.CompactTuples):
        got = C.CompactTuples.__new__(C.CompactTuples)
        got._keys, got._width = _convert(value._keys), value._width
        return got if got._keys is not None else None
    if isinstance(value, C.CompactCosts):
        got = C.CompactCosts.__new__(C.CompactCosts)
        got._keys = _convert(value._keys)
        got._values = value._values
        _mark(got._values)
        return got if got._keys is not None else None
    if isinstance(value, C.CompactLattice):
        got = C.CompactLattice.__new__(C.CompactLattice)
        for name in C.CompactLattice.__slots__:
            setattr(got, name, getattr(value, name))
        got._keys = _convert(value._keys)
        got._surfaces = _convert(value._surfaces)
        got._memo = {}
        _mark(got._starts, got._left, got._right, got._cost, got._pos)
        return got if got._keys is not None and got._surfaces is not None else None
    return None


class _Writer(pickle.Pickler):
    def __init__(self, file, chunks):
        super().__init__(file, protocol=4)
        self._chunks = chunks
        self._size = 0

    def persistent_id(self, obj):
        if id(obj) not in _MARKED or _MARKED[id(obj)] is not obj:
            return None
        if type(obj) is str and len(obj) >= _BIG // 4:
            data = obj.encode('utf-8')
            return ('t', self._add(data), len(data))
        if type(obj) is array and obj.itemsize * len(obj) >= _BIG:
            data = obj.tobytes()
            return ('a', obj.typecode, self._add(data), len(data))
        return None

    def _add(self, data):
        at = self._size
        self._chunks.append(data)
        self._size += len(data)
        pad = (-self._size) % _ALIGN
        if pad:
            self._chunks.append(b'\0' * pad)
            self._size += pad
        return at


class _Reader(pickle.Unpickler):
    def __init__(self, file, mm, base):
        super().__init__(file)
        self._mm = mm
        self._base = base

    def persistent_load(self, pid):
        kind = pid[0]
        if kind == 't':
            return _Text(self._mm, self._base + pid[1], pid[2])
        if kind == 'a':
            typecode, at, length = pid[1], pid[2], pid[3]
            return memoryview(self._mm)[self._base + at:self._base + at + length].cast(typecode)
        raise pickle.UnpicklingError('unknown mapped part')

    def find_class(self, module, name):
        # 控えに書くのは compact_tables の物と組み込みの入れ物だけ
        if module in ('compact_tables', 'builtins', 'array', '_codecs', 'copyreg', 'collections'):
            return super().find_class(module, name)
        raise pickle.UnpicklingError('not a table: %s.%s' % (module, name))


def write(path, stamp, value):
    """value を写像して読める形で path に書く。書けない形なら False。"""
    _MARKED.clear()
    try:
        converted = _convert(value)
        if converted is None:
            return False
        chunks = []
        head = io.BytesIO()
        _Writer(head, chunks).dump((stamp, converted))
        head = head.getvalue()
    finally:
        _MARKED.clear()
    start = len(_MAGIC) + 8 + len(head)
    pad = (-start) % _ALIGN
    total = start + pad + sum(len(c) for c in chunks)
    tmp = '%s.%d.tmp' % (path, os.getpid())
    try:
        with open(tmp, 'wb') as stream:
            stream.write(_MAGIC)
            stream.write(len(head).to_bytes(4, 'little') + total.to_bytes(4, 'little'))
            stream.write(head)
            stream.write(b'\0' * pad)
            for c in chunks:
                stream.write(c)
        os.replace(tmp, path)
        return True
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass
        return False


def read(path, stamp):
    """(True, 値) か (False, None)。写像は値が生きている間残る（ファイルは閉じてよい）。"""
    try:
        with open(path, 'rb') as stream:
            size = os.fstat(stream.fileno()).st_size
            if size < len(_MAGIC) + 8:
                return False, None
            mm = mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            if mm[:len(_MAGIC)] != _MAGIC:
                mm.close()
                return False, None
            at = len(_MAGIC)
            head_len = int.from_bytes(mm[at:at + 4], 'little')
            total = int.from_bytes(mm[at + 4:at + 8], 'little')
            if total != size:
                mm.close()
                return False, None
            start = at + 8 + head_len
            base = start + (-start) % _ALIGN
            saved, value = _Reader(io.BytesIO(mm[at + 8:start]), mm, base).load()
        except Exception:
            try:
                mm.close()
            except Exception:
                pass
            return False, None
        if saved != stamp:
            # 写像した物を手放せば閉じられる（値はここで捨てる）
            del value
            return False, None
        return True, value
    except Exception:
        return False, None
