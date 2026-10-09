# -*- coding: utf-8 -*-
"""User-requested literal-only rows: formatting and explicit links, no NLP."""
import re
from text_links import find_links


# RFC 2397 framing identifies data, not prose; this is not a URI validator.
# Even unfinished payload escapes/base64 stay literal. Do not decode them.
# No image-type restriction or length cutoff is needed.
_MIME_TOKEN = r"[A-Z0-9!#$%&'*+.^_`|~-]+"
_DATA_URI = re.compile(
    r"data:(?:"+_MIME_TOKEN+r"/"+_MIME_TOKEN+r")?"
    r"(?:;"+_MIME_TOKEN+r"="+_MIME_TOKEN+r")*(?:;base64)?,"
    r"[A-Z0-9;/?:@&=+$,\-_.!~*'()%]*", re.IGNORECASE|re.ASCII)


def _data_uri_only(text):
    value=text.strip()
    pairs={'"':'"',"'":"'",'「':'」','『':'』'}
    if len(value)>=2 and pairs.get(value[0])==value[-1]:value=value[1:-1]
    return _DATA_URI.fullmatch(value) is not None


MAX_ANALYZED_LINE_LENGTH = 4000


def unwrapped_only(text):
    """Bound rendering and NLP by logical row, independently of window width."""
    if '\n' in text:return False
    if len(text)>MAX_ANALYZED_LINE_LENGTH:return True
    if '\r' in text:return False
    return _data_uri_only(text)


def literal_only(text):
    if not text.strip():return True
    if '\n' in text:return False
    if unwrapped_only(text):return True
    if '\r' in text:return False
    links=find_links(text)
    if not links:return False
    edge=0
    for link in links:
        start,end=link.start,link.end
        # The detector deliberately excludes a matched surrounding quotation.
        pairs={'"':'"',"'":"'",'「':'」','『':'』'}
        if start>edge and text[start-1] in pairs and end<len(text) and text[end]==pairs[text[start-1]]:
            start-=1;end+=1
        if text[edge:start].strip():return False
        edge=end
    return not text[edge:].strip()


def result(text):
    return dict(original=text,corrected=text,changed=False,details=[],spans=[],
                original_spans=[],unsure_spans=[],odd_spans=[],odd_reasons=[],
                analysis_status='complete')


def units(text):
    # No linguistic candidates for rows that the user explicitly excludes.
    # Text selection, copying and explicit-link tags remain native widget work.
    return text,[]


def prepared(lines):
    return dict(context={},attested={},words={line:[] for line in lines if line.strip()})
