# -*- coding: utf-8 -*-
"""明示的な誤入力例・入力内容の引用範囲。語そのものの正誤や修正先は定義しない。

判定設計: GPT-6 / 2026-09-10〜11 / 48-XM・48-YB。
括弧だけでは保護しない。誤字の例・入力した文字列の引用と、実辞書の活用形を説明する記述を扱う。
"""
import re
from functools import lru_cache

KNOWLEDGE_VERSION = '2026-09-15c'

_ERROR_NOUN = r'(?:誤入力|誤変換|誤字|誤記|誤植|入力ミス|タイプミス|ミスタイプ|打ち間違い)'
# The label names the quoted spelling as data, even when the example is
# not explicitly erroneous. A copular assertion or direct example marker
# is required; merely mentioning input/output elsewhere is insufficient.
_INPUT_EXAMPLE = r'(?:入力|出力|表記)の?例'
_EXAMPLE_LABEL = r'(?:'+_ERROR_NOUN+r'(?:の?例)?|'+_INPUT_EXAMPLE+r')'
_AFTER = re.compile(r'\s*(?:という|といった)\s*' + _EXAMPLE_LABEL +
                    r'(?=$|[\s、。，．:：;；!?！？がはをにでとのだ])')
_BEFORE = re.compile(r'(?:'+_ERROR_NOUN+r'の?例|'+_INPUT_EXAMPLE+
                     r')\s*(?:[:：]|は|が|として(?:は|の)?)?\s*$')
# GPT-6 Astra: an explicit demonstration of an error describes its literal
# spelling. An unrelated error word elsewhere does not protect a quote.
_ERROR_DEMONSTRATION_BEFORE = re.compile(r'(?:誤り|間違い|'+_ERROR_NOUN+
    r')(?:の例)?を(?:示す|説明する|記録する)ため(?:に)?[、,\s]*$')
# 48-ZP: the quoted text is explicitly classified as an input/error example.
# Require the copular assertion; "は誤字を検出する" describes a function.
_CLASSIFIED_AFTER = re.compile(r'\s*(?:は|が|も)\s*'+_EXAMPLE_LABEL+r'\s*'
    r'(?:ではありませんでした|ではありません|ではなかった|ではない|でした|です|だった|だ)'
    r'(?=$|[\s、。，．:：;；!?！？がとねよ])')

# 48-ACD: a closed quoted expression is the object of an explicit judgment
# of linguistic acceptability. Keep the spelling being discussed. A normal
# action after the quote (正しく表示する / 自然に消える) is not this assertion.
_EXPRESSION_ASSERTION_AFTER = re.compile(
    r'\s*(?:は|が)\s*[、,]?\s*(?:(?:日本語|文法)(?:として|では)|文法的に)?\s*'
    r'(?:成立(?:している|していない|しない)|(?:不自然|自然)(?:な(?:表現|文|文章|言い方|語形))?(?:でした|だった|でしょう|です|だ)|(?:正しい|おかしい)(?:です|でしょう)?)'
    r'(?=$|[\s、。，．:：;；!?！？がとのねよかけ])')

# 入力した文字列そのものを報告する引用も、表記が記述の対象になる。
# 裸の引用や「と書いた」全般には広げない（通常の文章の校正と区別）。
_TYPED_AFTER = re.compile(r'\s*と\s*(?:(?:キー入力|入力|タイプ|打鍵)(?:し|する|すれ|せず|せよ)|'
                          r'打(?:った|って|ち|つ|て|とう))')
# 48-ACU: a reported inscription describes the literal written text.
# This does not cover the generic proofreading frame '...to kaita'.
_INSCRIPTION_AFTER = re.compile(r'\s*と\s*書いて(?:あります|ありました|あった|ある)(?=$|[\s、。，．!?！？とがのねよ])')
_PAIRS = {'「':'」','『':'』','“':'”','‘':'’','"':'"'}
_CLOSE = frozenset(_PAIRS.values())

# SP-MENTION / GPT-6 / 2026-09-13: the written form is being named or described.
_SPELLING_AFTER = re.compile(r'\s*(?:という|といった)\s*(?:表記|綴り|文字列|文字)(?=$|[\s、。，．:：;；!?！？がはをにでとの])')
_NAMING_BEFORE = re.compile(r'(?:商品名|作品名|人名|名前|名称|表記|綴り)(?:は|が|[:：])\s*$')
_NAMING_AFTER = re.compile(r'\s*(?:は|が)(?:(?:登場人物|商品|作品)の)?(?:名前|名称|名)(?:です|だ|である|$)')
_DESCRIBED_AFTER = re.compile(r'\s*(?:は|が)(?:くだけた|小書きの|特殊な)?(?:表記|綴り)(?:です|だ|である|$)')
_BARE_NAME = re.compile(r'([^\s、。！？!?「」『』()（）]+?)(?=という(?:名前|名称|名)(?:の|を|は|が|です|$))')
_REWRITE_PAIR = re.compile(r'「([^「」]+)」を「([^「」]+)」に(?:直|補正|変換|書き換え)')
_JUDGED_REWRITE_PAIR = re.compile(
    r'[×✕✖]\s*「([^「」]+)」\s*[→⇒]\s*[○〇◯]\s*「([^「」]+)」')



# GPT-6 / 2026-09-11 / 48-YI: 字形が記述対象になった活用形を保持する。
# 裸の引用や「と書いた」を一律に止めず、実辞書の一語と説明の名詞を照合。
_FORM_LABEL = r'(?:語形|活用形|未然形|連用形|終止形|連体形|仮定形|命令形|語幹|言葉|ことば|単語|語)'
_FORM_AFTER = re.compile(r'\s*(?:という|といった)\s*' + _FORM_LABEL +
                         r'(?=$|[\s、。，．:：;；!?！？がはをにでとのもだ])')


_WORD_AFTER = re.compile(r'\s*(?:という|といった)\s*(?:言葉|ことば|単語|語)'
                         r'(?=$|[\s、。，．:：;；!?！？がはをにでとのもだ])')


@lru_cache(maxsize=4096)
def _native_mentioned_word(surface):
    from morphology import dictionary_inflections
    entries=dictionary_inflections(surface) or ()
    if any(not pos.startswith(('接頭詞,','名詞,接尾,','動詞,接尾,','記号,'))
           for pos,form,base,reading in entries):
        return True
    # Repeated interjections describe a voiced expression as one written unit.
    half=len(surface)//2
    if half and surface[:half]==surface[half:]:
        return any(pos.startswith(('感動詞,','副詞,'))
                   for pos,form,base,reading in dictionary_inflections(surface[:half]) or ())
    return False


def _unquoted_word_ranges(line,quoted):
    markers=tuple(_WORD_AFTER.finditer(line))
    if not markers:return []
    from morphology import tokenize
    tokens=tokenize(line);out=[]
    for marker in markers:
        edge=len(line[:marker.start()].rstrip())
        last=next((i for i in range(len(tokens)-1,-1,-1) if tokens[i].end==edge),None)
        if last is None:continue
        candidates=[]
        for first in range(last,-1,-1):
            token=tokens[first]
            if edge-token.start>32 or (first<last and token.end!=tokens[first+1].start):break
            if token.pos=='記号' or overlaps(token.start,edge,quoted):break
            if first<last and token.pos=='助詞':break
            # Do not freeze only the last noun of a compound or one auxiliary
            # from a compound predicate. The native whole word must be present.
            if first and tokens[first-1].end==token.start:
                prior=tokens[first-1]
                # An unknown preceding piece does not establish a word
                # boundary. Nor is a bound verb after a noun a free word.
                if not prior.has_reading:
                    continue
                if (prior.pos in ('名詞','接頭詞') and (token.pos in ('名詞','助動詞')
                        or (token.pos=='動詞' and token.pos_sub.startswith(('非自立','接尾'))))):
                    continue
                if (prior.pos in ('動詞','形容詞','助動詞')
                        and token.pos in ('動詞','助動詞')):
                    continue
            if _native_mentioned_word(line[token.start:edge]):
                candidates.append((token.start,edge))
        if candidates:out.append(min(candidates))
    return out


@lru_cache(maxsize=2048)
def _native_inflected_form(surface):
    from morphology import dictionary_inflections
    return any(pos.startswith(('動詞,', '形容詞,', '助動詞,'))
               and form not in ('', '*', '基本形') and base != surface
               for pos, form, base, reading in dictionary_inflections(surface) or ())


def _unquoted_form_ranges(line, quoted):
    markers = tuple(_FORM_AFTER.finditer(line))
    if not markers:
        return []
    from morphology import tokenize
    tokens = tokenize(line)
    result = []
    for marker in markers:
        # 空白を説明ラベル側へ含めても、語の途中の末尾だけは取り出さない。
        edge = len(line[:marker.start()].rstrip())
        index = next((i for i in range(len(tokens)-1, -1, -1) if tokens[i].end == edge), None)
        token = tokens[index] if index is not None else None
        if (token is None or not token.has_reading
                or token.pos not in ('動詞', '形容詞', '助動詞')
                or token.infl_form in ('', '*', '基本形')
                or line[token.start:token.end] != token.surface
                or overlaps(token.start, token.end, quoted)):
            continue
        if index and tokens[index-1].end == token.start:
            prior=tokens[index-1]
            if (not prior.has_reading or prior.pos in ('動詞','形容詞','助動詞')
                    or (prior.pos in ('名詞','接頭詞') and (token.pos=='助動詞'
                        or (token.pos=='動詞' and token.pos_sub.startswith(('非自立','接尾')))))):
                continue  # Do not freeze only the bound end of a larger expression.
        if _native_inflected_form(token.surface):
            result.append((token.start, token.end))
    return result


# 48-AAM / GPT-6 / 2026-09-12. A written uppercase code after an
# established noun names an item. Its letters are not stray kana keys.
# Require the original spelling, native noun and an actual right boundary;
# lowercase typing fragments and letters embedded in a word stay available.
_UPPER_IDENTIFIER = re.compile(r'(?<![A-Za-zＡ-Ｚａ-ｚ0-9０-９])'
    r'[A-ZＡ-Ｚ][A-ZＡ-Ｚ0-9０-９]{1,15}(?![A-Za-zＡ-Ｚａ-ｚ0-9０-９])')


@lru_cache(maxsize=4096)
def named_identifier_parts(line):
    matches=tuple(_UPPER_IDENTIFIER.finditer(line))
    if not matches:return []
    from morphology import tokenize,dictionary_inflections
    tokens=list(tokenize(line));out=[]
    for match in matches:
        start,end=match.span()
        following=next((t for t in tokens if t.start==end),None)
        if end<len(line) and not (line[end].isspace() or line[end] in '。、，．!?！？:：;；）」』】]'):
            if not (following and following.has_reading and following.pos=='助詞'):
                continue
        left=next((i for i,t in enumerate(tokens) if t.end==start),None)
        if left is None:continue
        heads=[]
        for i in range(left,-1,-1):
            token=tokens[i]
            if (not token.has_reading or token.pos!='名詞'
                    or (i<left and token.end!=tokens[i+1].start)):
                break
            head=line[token.start:start]
            if len(head)>24:break
            if not any('一'<=c<='鿿' or 'ァ'<=c<='ヶ' for c in head):continue
            if any(pos.startswith('名詞,') and not any(x in pos for x in ('非自立','接尾'))
                   for pos,form,lemma,reading in dictionary_inflections(head) or ()):
                heads.append(token.start)
        if heads:out.append((min(heads),start,end))
    return out


def named_identifier_ranges(line):
    return [(a,b) for a,code,b in named_identifier_parts(line)]


@lru_cache(maxsize=4096)
def native_reading_gloss_ranges(line):
    """48-ABC: the parenthesis explicitly repeats the preceding native reading.

    Compare original spellings only. Parentheses, a rare reading, or an
    unrelated kana phrase alone do not establish a reading annotation.
    Mixed katakana + hiragana glosses can include a repeated proper name.
    """
    matches=tuple(re.finditer(r'[（(]([^()（）\n]+)[）)]',line))
    if not matches:return []
    from morphology import tokenize,katakana_to_hiragana
    tokens=list(tokenize(line));out=[]
    for match in matches:
        if (match.group()[0],match.group()[-1]) not in (('（','）'),('(',')')):continue
        content=re.split('[、,]',match.group(1),maxsplit=1)[0]
        gloss=content.strip()
        if not gloss or not all('ぁ'<=c<='ゖ' or 'ァ'<=c<='ヶ' or c=='ー' for c in gloss):
            continue
        last=next((i for i,t in enumerate(tokens) if t.end==match.start()),None)
        if last is None:continue
        reading=''
        for i in range(last,-1,-1):
            t=tokens[i]
            literal=bool(t.surface) and all('ぁ'<=c<='ゖ' or 'ァ'<=c<='ヶ' or c=='ー' for c in t.surface)
            if ((not t.has_reading and not literal) or t.pos=='記号' or match.start()-t.start>40
                    or (i<last and t.end!=tokens[i+1].start)):
                break
            # Kana gives its own written reading even when a name is not
            # in the dictionary. Kanji still needs native reading evidence.
            reading=(t.surface if literal else t.reading)+reading
            if (katakana_to_hiragana(reading)==katakana_to_hiragana(gloss)
                    and any('一'<=c<='鿿' for c in line[t.start:match.start()])):
                start=match.start(1)+len(content)-len(content.lstrip())
                out.append((start,start+len(gloss)))
                break
    return out


def _unquoted_error_ranges(line,quoted):
    """The proposition named by an explicit error label is literal evidence.

    GPT-6 Astra / 2026-09-14. The same という誤変換 marker used after
    quotes also names an unquoted example. Sentence/quotation punctuation
    bounds it; unrelated error vocabulary elsewhere supplies no protection.
    """
    out=[]
    for marker in _AFTER.finditer(line):
        end=len(line[:marker.start()].rstrip())
        start=end
        while start and line[start-1] not in '。！？!?、,;；:：\n\r「」『』“”‘’"()（）':start-=1
        while start<end and line[start].isspace():start+=1
        if start<end and not overlaps(start,end,quoted):out.append((start,end))
    return out


def protected_ranges(line):
    """記述対象のコードポイント範囲。閉じていない引用や裸の括弧は対象外。"""
    if not isinstance(line,str) or not line:
        return []
    stack=[];found=[];quoted=[]
    for pos,ch in enumerate(line):
        if ch=='"':
            back=pos-1
            while back>=0 and line[back]=='\\':back-=1
            if (pos-1-back)%2:continue
        if stack and ch==stack[-1][1]:
            start,_close=stack.pop()
            quoted.append((start,pos+1))
            if not line[start+1:pos].strip():continue
            if (_AFTER.match(line,pos+1) or _CLASSIFIED_AFTER.match(line,pos+1) or _TYPED_AFTER.match(line,pos+1) or
                    _EXPRESSION_ASSERTION_AFTER.match(line,pos+1) or _INSCRIPTION_AFTER.match(line,pos+1) or
                    (_FORM_AFTER.match(line,pos+1) and _native_inflected_form(line[start+1:pos])) or
                    _SPELLING_AFTER.match(line,pos+1) or _NAMING_AFTER.match(line,pos+1) or
                    _DESCRIBED_AFTER.match(line,pos+1) or _NAMING_BEFORE.search(line[:start]) or
                    (_WORD_AFTER.match(line,pos+1) and _native_mentioned_word(line[start+1:pos])) or
                    _BEFORE.search(line[max(0,start-64):start]) or
                    _ERROR_DEMONSTRATION_BEFORE.search(line[max(0,start-64):start])):
                found.append((start+1,pos))
        elif ch in _PAIRS:
            stack.append((pos,_PAIRS[ch]))
        elif ch in _CLOSE:
            # 対応しない閉じ括弧をまたいで外側を保護しない。
            quoted.extend((start,pos+1) for start,_ in stack)
            stack.clear()
    quoted.extend((start,len(line)) for start,_ in stack)
    found.extend(m.span(1) for m in _BARE_NAME.finditer(line))
    for pattern in (_REWRITE_PAIR,_JUDGED_REWRITE_PAIR):
        for match in pattern.finditer(line):
            found.extend((match.span(1),match.span(2)))
    found.extend(_unquoted_error_ranges(line,quoted))
    found.extend(_unquoted_form_ranges(line,quoted))
    found.extend(_unquoted_word_ranges(line,quoted))
    found.extend(named_identifier_ranges(line))
    found.extend(native_reading_gloss_ranges(line))
    from mark_usage import intentional_ranges
    found.extend(intentional_ranges(line))
    merged=[]
    for a,b in sorted(found):
        if merged and a<=merged[-1][1]:merged[-1]=(merged[-1][0],max(b,merged[-1][1]))
        else:merged.append((a,b))
    return merged


def overlaps(a,b,ranges):
    # 挿入点は範囲の内側だけを覆う。始点/終点の外側の文字は保持範囲を変えない。
    return any((x<a<y if a==b else a<y and x<b) for x,y in ranges)


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
