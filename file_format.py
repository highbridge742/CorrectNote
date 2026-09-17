# -*- coding: utf-8 -*-
"""A tab's text encoding and physical line endings, without document history."""
import codecs
import difflib
import re

ENCODINGS = {
    'utf-8': 'UTF-8',
    'utf-8-sig': 'UTF-8（BOM付き）',
    'cp932': 'Shift_JIS（CP932）',
    'utf-16-le': 'UTF-16 LE（BOM付き）',
    'utf-16-be': 'UTF-16 BE（BOM付き）',
}
ENDINGS = {'w': '\r\n', 'l': '\n', 'm': '\r'}
ENDING_NAMES = {'w': 'CRLF', 'l': 'LF', 'm': 'CR'}
_CODES = {value: key for key, value in ENDINGS.items()}
_NEWLINE = re.compile(r'\r\n|\r|\n')


def clean(value=None, text=''):
    """Validate old/partial session metadata; empty maps mean one uniform style."""
    value = value if isinstance(value, dict) else {}
    encoding = value.get('encoding', 'utf-8')
    if not isinstance(encoding, str) or encoding not in ENCODINGS:
        encoding = 'utf-8'
    newline = value.get('newline', 'w')
    if not isinstance(newline, str) or newline not in ENDINGS:
        newline = 'w'
    endings = value.get('endings', '')
    count = text.rstrip('\n').count('\n')
    if (not isinstance(endings, str) or len(endings) != count
            or any(code not in ENDINGS for code in endings)):
        endings = ''
    tail = value.get('tail', '')
    if not isinstance(tail, str) or any(code not in ENDINGS for code in tail):
        tail = ''
    return dict(encoding=encoding, newline=newline, endings=endings, tail=tail)


def decode(raw):
    """Decode strictly and keep BOM, mixed newlines and the file's final breaks."""
    if raw.startswith((codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE)):
        raise ValueError('UTF-32のファイルには対応していません。')
    if raw.startswith(codecs.BOM_UTF8):
        encoding, text = 'utf-8-sig', raw.decode('utf-8-sig')
    elif raw.startswith(codecs.BOM_UTF16_LE):
        encoding, text = 'utf-16-le', raw[2:].decode('utf-16-le')
    elif raw.startswith(codecs.BOM_UTF16_BE):
        encoding, text = 'utf-16-be', raw[2:].decode('utf-16-be')
    else:
        if b'\x00' in raw:
            raise ValueError('テキストファイルではないようです。')
        try:
            encoding, text = 'utf-8', raw.decode('utf-8')
        except UnicodeDecodeError:
            encoding, text = 'cp932', raw.decode('cp932')
    if '\x00' in text:
        raise ValueError('テキストファイルではないようです。')
    codes = ''.join(_CODES[m.group()] for m in _NEWLINE.finditer(text))
    normalized = _NEWLINE.sub('\n', text)
    trailing = len(normalized) - len(normalized.rstrip('\n'))
    core = normalized.rstrip('\n')
    newline = max(dict.fromkeys(codes), key=codes.count) if codes else 'w'
    body = codes[:-trailing] if trailing else codes
    value = dict(encoding=encoding, newline=newline,
                 endings=body if any(c != newline for c in body) else '',
                 tail=codes[-trailing:] if trailing else '')
    return normalized, clean(value, core)


def rebase(value, before, after):
    """Carry mixed endings with unchanged lines; new lines use the main style."""
    before, after = before.rstrip('\n'), after.rstrip('\n')
    value = clean(value, before)
    old = value['endings']
    if not old or before == after:
        return value
    left, right = before.split('\n'), after.split('\n')
    endings = [value['newline']] * (len(right) - 1)
    for tag, a, b, x, y in difflib.SequenceMatcher(None, left, right).get_opcodes():
        if tag in ('equal', 'replace'):
            for i, j in zip(range(a, b), range(x, y)):
                if i < len(old) and j < len(endings):
                    endings[j] = old[i]
    mapped = ''.join(endings)
    value['endings'] = mapped if any(c != value['newline'] for c in mapped) else ''
    return value


def encode(text, value=None):
    """Exclude editor padding, then restore the tab's file format exactly."""
    text = text.rstrip('\n')
    value = clean(value, text)
    lines = text.split('\n')
    endings = value['endings'] or value['newline'] * (len(lines) - 1)
    pieces = [line + ENDINGS[code] for line, code in zip(lines, endings)]
    pieces.append(lines[-1])
    pieces.extend(ENDINGS[code] for code in value['tail'])
    physical = ''.join(pieces)
    encoding = value['encoding']
    payload = physical.encode(encoding, errors='strict')
    if encoding == 'utf-16-le':
        payload = codecs.BOM_UTF16_LE + payload
    elif encoding == 'utf-16-be':
        payload = codecs.BOM_UTF16_BE + payload
    return payload


def newline_label(value, text=''):
    value = clean(value, text)
    styles = set(value['endings'] + value['tail'])
    if not value['endings'] and '\n' in text.rstrip('\n'):
        styles.add(value['newline'])
    if not styles:
        styles.add(value['newline'])
    return ENDING_NAMES[next(iter(styles))] if len(styles) == 1 else '混在（保持）'
