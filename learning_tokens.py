# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu; GPL-3.0-or-later.
"""自動学習の形態素解析を、画面のスレッドの外で行う（2026-10-18）。

`janome_import.learn_from_text` は解析と覚える所が1つの関数で、3000行の
新しい本文では画面のスレッドを約7秒止めていた。janome_import.py は
public_nominal_cache が SHA を控えているので変えない。代わりに:

    tokenize(text)              同じ解析を別のスレッドで（語彙に触らない）
    learn(store, text, tokens)  その結果で learn_from_text をそのまま呼ぶ
                                （覚える所は1つのまま。画面のスレッドで）

janome の辞書は mmap を共有しているので、読むあいだは janome の錠前を持つ。
ただし一度に持つのは数百語の分だけにして、画面の側の解析を待たせない
（同じ生成器を少しずつ進めるだけなので、出てくる語は一度に読むのと同じ）。
"""
import janome_import

# 学習のあいだ janome_import.Tokenizer を差し替えるので、本物はここで控える
_TOKENIZER = getattr(janome_import, 'Tokenizer', None)
STEP = 256


def tokenize(text):
    """`learn_from_text` が作るのと同じ語の並び。解析できなければ None。"""
    if not janome_import.HAS_JANOME or not text or _TOKENIZER is None:
        return None
    lock = janome_import._janome_lock
    tokens = []
    try:
        with lock():
            stream = _TOKENIZER().tokenize(text)
        while True:
            with lock():
                for _ in range(STEP):
                    tokens.append(next(stream))
    except StopIteration:
        return tokens
    except SystemExit:      # janome が辞書の不具合で sys.exit を呼ぶ（学び16）
        return None
    except Exception:
        return None


class _Made:
    """`learn_from_text` の中の Tokenizer() の代わり。作ってある語を返す。"""

    def __init__(self, tokens):
        self._tokens = tokens

    def tokenize(self, text):
        return iter(self._tokens)


def learn(store, text, tokens):
    """`janome_import.learn_from_text(store, text)` を、解析済みの語で呼ぶ。
    戻り値も同じ（中身が変わった語の数）。解析できていなければ 0。"""
    if tokens is None:
        return 0
    real = janome_import.Tokenizer
    janome_import.Tokenizer = lambda *args, **kwargs: _Made(tokens)
    try:
        return janome_import.learn_from_text(store, text)
    finally:
        janome_import.Tokenizer = real
