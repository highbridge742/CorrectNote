# -*- coding: utf-8 -*-
"""明示的な誤入力例・入力内容の引用範囲。語そのものの正誤や修正先は定義しない。

判定設計: GPT-6 / 2026-09-10〜11 / 48-XM・48-YB。
括弧だけでは保護しない。誤字の例または入力した文字列だと明示された引用を扱う。
"""
import re

_ERROR_NOUN = r'(?:誤入力|誤変換|誤字|誤記|誤植|入力ミス|タイプミス|ミスタイプ|打ち間違い)'
_AFTER = re.compile(r'\s*(?:という|といった)\s*' + _ERROR_NOUN +
                    r'(?:の?例)?(?=$|[\s、。，．:：;；!?！？がはをにでとのだ])')
_BEFORE = re.compile(_ERROR_NOUN + r'の?例\s*[:：]?\s*$')
# 入力した文字列そのものを報告する引用も、表記が記述の対象になる。
# 裸の引用や「と書いた」全般には広げない（通常の文章の校正と区別）。
_TYPED_AFTER = re.compile(r'\s*と\s*(?:(?:キー入力|入力|タイプ|打鍵)(?:し|する|すれ|せず|せよ)|'
                          r'打(?:った|って|ち|つ|て|とう))')
_PAIRS = {'「':'」','『':'』','“':'”','‘':'’','"':'"'}
_CLOSE = frozenset(_PAIRS.values())


def protected_ranges(line):
    """引用内容のコードポイント範囲。閉じていない引用や裸の括弧は対象外。"""
    if not isinstance(line,str) or not line:
        return []
    stack=[];found=[]
    for pos,ch in enumerate(line):
        if ch=='"':
            back=pos-1
            while back>=0 and line[back]=='\\':back-=1
            if (pos-1-back)%2:continue
        if stack and ch==stack[-1][1]:
            start,_close=stack.pop()
            if not line[start+1:pos].strip():continue
            if (_AFTER.match(line,pos+1) or _TYPED_AFTER.match(line,pos+1) or
                    _BEFORE.search(line[max(0,start-64):start])):
                found.append((start+1,pos))
        elif ch in _PAIRS:
            stack.append((pos,_PAIRS[ch]))
        elif ch in _CLOSE:
            # 対応しない閉じ括弧をまたいで外側を保護しない。
            stack.clear()
    merged=[]
    for a,b in sorted(found):
        if merged and a<=merged[-1][1]:merged[-1]=(merged[-1][0],max(b,merged[-1][1]))
        else:merged.append((a,b))
    return merged


def overlaps(a,b,ranges):
    return any((x<=a<y if a==b else a<y and x<b) for x,y in ranges)


def subtract_ranges(items,ranges):
    """範囲の外側の判定だけを残す。不正データは結果契約の検査へ渡す。"""
    if not isinstance(items,(list,tuple)):
        return items
    out=[]
    for item in items:
        if (not isinstance(item,(list,tuple)) or len(item)<2 or
                type(item[0]) is not int or type(item[1]) is not int or item[0]>=item[1]):
            out.append(item);continue
        pieces=[(item[0],item[1])]
        for x,y in ranges:
            next_pieces=[]
            for a,b in pieces:
                if b<=x or y<=a:next_pieces.append((a,b));continue
                if a<x:next_pieces.append((a,x))
                if y<b:next_pieces.append((y,b))
            pieces=next_pieces
        out.extend((a,b,*item[2:]) for a,b in pieces)
    return out
