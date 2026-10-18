"""同じ読みの漢字の身近さの表（AI 判定）。

読み → 身近な順の2字漢語の表記。先頭の表記に「!」が付いていれば、その読みでは先頭が身近さで抜けている
（電気 ≫ 伝記・電機）。並んだ表記のどれを置くか・どの読み直しを採るかで、文脈にも本人の記録にも決め手が無いときの
最後の決め手（うに 2026-10-18: 文脈優先、読み取れなければ最も身近な語に）。表に無い読み・表記は kango_tier の段に戻る。
表は everyday_faces.json（読み → ["電気!", "伝記", "電機"]）。
"""
import json
import os

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'everyday_faces.json')
_TABLE = None


def _load():
    global _TABLE
    if _TABLE is None:
        try:
            with open(_PATH, encoding='utf-8') as f:
                _TABLE = json.load(f)
        except Exception:
            _TABLE = {}
    return _TABLE


def available():
    """表が読めているか（bundle_manifest の見張り用）。"""
    return bool(_load())


def order(reading):
    """読み → (身近な順の表記のタプル, 先頭が身近さで抜けているか)。表に無ければ ((), False)。"""
    row = _load().get(reading)
    if not row:
        return (), False
    faces = tuple(f.rstrip('!') for f in row)
    return faces, bool(row and row[0].endswith('!'))


def rank(reading, face):
    """表の中の順位（0 が最も身近）。表に無ければ None。"""
    faces, _dominant = order(reading)
    return faces.index(face) if face in faces else None
