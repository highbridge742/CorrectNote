# -*- coding: utf-8 -*-
"""品詞の表示（色・説明）に使う解析の包み（2026-11-09 うにさん「おもしれえ の品詞が 重い の活用になっているが、正しくは
面白い の活用」）。くだけた形（おもしれえ）を元の形容詞（おもしろい）に戻して解析し（colloquial_adj.tokenize_with）、
表記・読みは元の字のまま、活用形を「くだけた形」にして返す（字の数が同じなので位置はそのまま）。

表示の単位を作る所（units.build_line_units・build_suspect_units に渡す解析）だけで使う。補正の道は通らない。
画面（app.py）と解析の子（analysis_worker.py）の両方がこれを使う（子は app.py を読まない）。
例外なら元の解析をそのまま使う。CN_COLLOQUIAL_POS=0 で包まない（前の形）。"""
import os

_LONG = ('え', 'ー', 'ぇ')


def pos_tokenizer(fn):
    if fn is None or os.environ.get('CN_COLLOQUIAL_POS') == '0' or getattr(fn, '_colloquial_pos', False):
        return fn
    try:
        import colloquial_adj
    except Exception:
        return fn

    def wrapped(text, _fn=fn):
        # くだけた形は え・ー・ぇ の伸ばしで終わる（colloquial_adj._LONG）。無い行は見ずに元の解析（1行 約1ms の節約）
        if not text or not any(c in text for c in _LONG):
            return _fn(text)
        try:
            got = list(colloquial_adj.tokenize_with(text, _fn))
        except Exception:
            return _fn(text)
        # 表示の解析（corrector.make_tokenizer）は (表記, 品詞, 読み, 開始, 終了, 読みが確定か, 活用形) の組を返す。
        # tokenize_with が表記を元の字に戻すのは Token の形だけなので、組の形もここで元の字に戻す（位置は同じ）
        out = []
        for tok in got:
            if isinstance(tok, tuple) and len(tok) >= 5:
                start, end = tok[3], tok[4]
                shown = text[start:end]
                if shown != tok[0]:
                    tok = (shown, tok[1], shown, start, end) + tuple(tok[5:6]) + ('くだけた形',) + tuple(tok[7:])
            out.append(tok)
        return out
    wrapped._colloquial_pos = True
    return wrapped
