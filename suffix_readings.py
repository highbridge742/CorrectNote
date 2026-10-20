"""接尾の名詞（券・状・所・館・費 など）の読みの表。

かなのまま打った複合語（ふくびき＋けん・しょうたい＋じょう）を「辞書の語＋接尾」と読むために使う。
表は suffix_readings.json（読み → 表記の並び）。janome の辞書（IPAdic）の 名詞:接尾:一般／サ変接続／形容動詞語幹
から開発時に導いた（tools: build_suffix_readings.py）。実機（janome の無い所）は表だけを読む。
"""
import json
import os

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'suffix_readings.json')
_TABLE = None


def _load():
    global _TABLE
    if _TABLE is None:
        try:
            with open(_PATH, encoding='utf-8') as f:
                _TABLE = json.load(f).get('readings') or {}
        except Exception:
            _TABLE = {}
    return _TABLE


def available():
    """表が読めているか（bundle_manifest の見張り用）。"""
    return bool(_load())


def is_suffix_reading(reading):
    """読み reading が接尾の名詞の読みか。"""
    return reading in _load()
