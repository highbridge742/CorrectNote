# -*- coding: utf-8 -*-
"""Small decimal arithmetic parser for explicitly requested quote calculations."""
from decimal import Decimal, DecimalException, localcontext
import re


_INPUT_CHARACTERS = {c + 0xFEE0: c for c in range(0x21, 0x7F)}
_INPUT_CHARACTERS.update(str.maketrans({'　': ' ', '×': '*', '÷': '/', '−': '-'}))

def calculate(expression):
    """Return an ASCII result, or None for incomplete/unsupported arithmetic."""
    # Width conversion must not turn unsupported powers such as 2² into 22.
    expression = expression.translate(_INPUT_CHARACTERS).strip()
    if not expression or len(expression) > 256 or '\n' in expression or '\r' in expression:
        return None
    tokens = re.findall(r'(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)|[^ \t]', expression)
    position = 0

    def primary(depth):
        nonlocal position
        if depth > 32 or position >= len(tokens):
            raise ValueError
        token = tokens[position]; position += 1
        if token in ('+', '-'):
            value = primary(depth + 1)
            return value if token == '+' else -value
        if token == '(':
            value = parse(0, depth + 1)
            if position >= len(tokens) or tokens[position] != ')':
                raise ValueError
            position += 1
            return value
        if not re.fullmatch(r'(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)', token):
            raise ValueError
        return Decimal(token)

    def parse(minimum, depth):
        nonlocal position
        value = primary(depth)
        while position < len(tokens):
            op = tokens[position]
            precedence = {'+': 1, '-': 1, '*': 2, '/': 2}.get(op, 0)
            if not precedence or precedence < minimum:
                break
            position += 1
            right = parse(precedence + 1, depth + 1)
            if op == '+': value += right
            elif op == '-': value -= right
            elif op == '*': value *= right
            else: value /= right
        return value

    try:
        with localcontext() as context:
            context.prec = 28
            value = parse(0, 0)
            if position != len(tokens) or not value.is_finite():
                return None
            if value == 0:
                return '0'
            result = format(value, 'f')
            return result.rstrip('0').rstrip('.') if '.' in result else result
    except (ValueError, DecimalException, RecursionError):
        return None


def clean_calculations(source,records):
    """Keep only explicit, nonoverlapping ranges still valid in this saved text."""
    if not isinstance(source,str) or not isinstance(records,(list,tuple)):return []
    valid=[]
    for record in records:
        if not isinstance(record,dict):continue
        start,end,surface=(record.get(k) for k in ('start','end','surface'))
        if (type(start) is not int or type(end) is not int
                or not isinstance(surface,str) or not 0<=start<end<=len(source)
                or source[start:end]!=surface or calculate(surface) is None):continue
        valid.append(dict(start=start,end=end,surface=surface))
    clean=[];end=0
    for record in sorted(valid,key=lambda x:(x['start'],x['end'])):
        if record['start']<end:continue
        clean.append(record);end=record['end']
    return clean


def continued_expression(source,calculations,start,end):
    """Extend a new quote range through adjacent, still-valid explicit formulas."""
    if not 0<=start<end<=len(source):return start,''
    previous={item.end:item for item in calculations
              if 0<=item.start<item.end<=start
              and source[item.start:item.end]==item.surface
              and calculate(item.surface)==item.result}
    while start in previous:
        start=previous[start].start
    return start,source[start:end]


def apply_to_result(result, calculations, decisions=None, tokenize_fn=None, dict_index=None):
    """Merge explicitly confirmed arithmetic with independent language corrections."""
    if not calculations:return result
    source=result['original']
    accepted=[item for item in calculations if 0<=item.start<item.end<=len(source)
              and source[item.start:item.end]==item.surface
              and calculate(item.surface)==item.result
              and not (decisions is not None and decisions.blocks(item.surface,item.result))]
    if not accepted:return result
    def overlaps(start,end):
        return any(start<item.end and item.start<end for item in accepted)
    # Use the same original ranges as menus and colors, including legacy values.
    from ui_projection import corrections
    edits=[(start,end,detail[1],detail[2]) for start,end,detail in corrections(result)
           if not overlaps(start,end)]
    edits.extend((item.start,item.end,item.result,'計算') for item in accepted)
    parts=[];details=[];original_spans=[];spans=[];cursor=0;length=0
    for start,end,value,category in sorted(edits):
        if start<cursor:continue
        parts.append(source[cursor:start]);length+=start-cursor
        parts.append(value);spans.append((length,length+len(value)))
        original_spans.append((start,end));details.append((source[start:end],value,category))
        length+=len(value);cursor=end
    parts.append(source[cursor:]);corrected=''.join(parts)
    out=dict(result,corrected=corrected,changed=corrected!=source,details=details,
             original_spans=original_spans,spans=spans)
    from literal_examples import subtract_ranges
    ranges=[(item.start,item.end) for item in accepted]
    for key in ('odd_spans','unsure_spans','odd_reasons'):
        out[key]=subtract_ranges(result.get(key,()),ranges)
    if tokenize_fn is not None:
        from corrector import _line_result_contract
        out=_line_result_contract(source,out,tokenize_fn,dict_index)
    else:
        out.pop('diagnosis',None)
    return out


def calculation_spans(record, include_identity=False):
    """Reassemble a result split into sign, decimal and number display units."""
    text=record['applied'];spans=record.get('spans',());position=0
    while position<len(spans):
        start,end,kind,before=spans[position];position+=1
        if kind!='fixed' or not 0<=start<end<=len(text):continue
        result=calculate(before)
        if result is None or before==result and not include_identity:continue
        while text[start:end]!=result and position<len(spans):
            first,last,next_kind,next_before=spans[position]
            if first!=end or next_kind!=kind or next_before!=before:break
            end=last;position+=1
        if text[start:end]==result:yield start,end,before,result


def source_calculations(record,result):
    """Original ranges of explicit calculations, never guessed from repeated digits."""
    if not result or result.get('original')!=record['original']:return None
    details=result.get('details') or ();spans=result.get('original_spans') or ()
    if len(details)!=len(spans):return ()
    found=[]
    for (start,end),detail in zip(spans,details):
        before,value,category=detail
        if (category=='計算' and 0<=start<end<=len(record['original'])
                and record['original'][start:end]==before and calculate(before)==value):
            found.append((start,end,before,value))
    return tuple(sorted(found))


def source_calculation_spans(record):
    """Pair ordered explicit source ranges with their validated displayed results."""
    source=record.get('calculation_sources') or ()
    shown=tuple(calculation_spans(record,include_identity=True))
    if len(source)!=len(shown):return ()
    found=[]
    for (lo,hi,before,value),(first,last,display_before,display_value) in zip(source,shown):
        if (record['original'][lo:hi]!=before or before!=display_before
                or value!=display_value):return ()
        found.append((lo,hi,before,value,first,last))
    return tuple(found)


def displayed_calculations(record):
    """Keep a still-applied quick-input result ASCII on subsequent rendering."""
    from analysis_work import Calculation
    return tuple(Calculation(start,end,value,value)
                 for start,end,before,value in calculation_spans(record))


def quote_enter_kind(expression):
    """Distinguish a typed row reference from explicitly requested arithmetic."""
    normalized=expression.translate(_INPUT_CHARACTERS).strip(' \t')
    if not normalized or len(normalized)>256 or '\n' in normalized or '\r' in normalized:
        return None,None
    if re.fullmatch('[0-9]+',normalized):return 'line',int(normalized)
    if re.fullmatch('[+-][0-9]+',normalized):return 'relative',int(normalized)
    if any(char in '+-*/' for char in normalized):return 'calculation',None
    return None,None
