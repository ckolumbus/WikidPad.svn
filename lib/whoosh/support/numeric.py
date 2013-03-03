#===============================================================================
# Copyright 2010 Matt Chaput
# 
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
#    http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#===============================================================================

import struct
from array import array


_dstruct = struct.Struct("<d")
_qstruct = struct.Struct("<q")
_dpack, _dunpack = _dstruct.pack, _dstruct.unpack
_qpack, _qunpack = _qstruct.pack, _qstruct.unpack

_max_sortable_int = 4294967295L
_max_sortable_long = 18446744073709551615L


# Functions for converting numbers to and from sortable representations

def int_to_sortable_int(x, signed=True):
    if signed: x += 1 << 31
    assert x >= 0
    return x

def sortable_int_to_int(x, signed=True):
    if signed: x -= 1 << 31
    return x

def long_to_sortable_long(x, signed=True):
    if signed: x += 1 << 63
    assert x >= 0
    return x

def sortable_long_to_long(x, signed=True):
    if signed: x -= 1 << 63
    return x

def float_to_sortable_long(x, signed=True):
    x = _qunpack(_dpack(x))[0]
    if x < 0:
        x ^= 0x7fffffffffffffff
    if signed: x += 1 << 63
    assert x >= 0
    return x

def sortable_long_to_float(x, signed=True):
    if signed: x -= 1 << 63
    if x < 0:
        x ^= 0x7fffffffffffffff
    x = _dunpack(_qpack(x))[0]
    return x

# Functions for converting numbers to and from text

def int_to_text(x, shift=0, signed=True):
    x = int_to_sortable_int(x, signed)
    return sortable_int_to_text(x, shift)

def text_to_int(text, signed=True):
    x = text_to_sortable_int(text)
    x = sortable_int_to_int(x, signed)
    return x

def long_to_text(x, shift=0, signed=True):
    x = long_to_sortable_long(x, signed)
    return sortable_long_to_text(x, shift)

def text_to_long(text, signed=True):
    x = text_to_sortable_long(text)
    x = sortable_long_to_long(x, signed)
    return x

def float_to_text(x, shift=0, signed=True):
    x = float_to_sortable_long(x, signed)
    return sortable_long_to_text(x, shift)

def text_to_float(text, signed=True):
    x = text_to_sortable_long(text)
    x = sortable_long_to_float(x, signed)
    return x

# Functions for converting sortable representations to and from text.
#
# These functions use hexadecimal strings to encode the numbers, rather than
# converting them to text using a 7-bit encoding, because while the hex
# representation uses more space (8 bytes as opposed to 5 bytes for a 32 bit
# number), it's 5-10 times faster to encode/decode in Python.
#
# The functions for 7 bit encoding are still available (to_7bit and from_7bit)
# if needed.


def sortable_int_to_text(x, shift=0):
    if shift:
        x >>= shift
    text = chr(shift) + u"%08x" % x
    assert len(text) == 9
    return text

def sortable_long_to_text(x, shift=0):
    if shift:
        x >>= shift
    text = chr(shift) + u"%016x" % x
    assert len(text) == 17
    return text

def text_to_sortable_int(text):
    #assert len(text) == 9
    return int(text[1:], 16)

def text_to_sortable_long(text):
    #assert len(text) == 17
    return long(text[1:], 16)


# Functions for generating tiered ranges

def split_range(valsize, step, start, end):
    """Splits a range of numbers (from ``start`` to ``end``, inclusive)
    into a sequence of trie ranges of the form ``(start, end, shift)``. The
    consumer of these tuples is expected to shift the ``start`` and ``end``
    right by ``shift``.
    
    This is used for generating term ranges for a numeric field. The queries
    for the edges of the range are generated at high precision and large blocks
    in the middle are generated at low precision.
    """
    
    shift = 0
    while True:
        diff = 1 << (shift + step)
        mask = ((1 << step) - 1) << shift
        setbits = lambda x: x | ((1 << shift) - 1)
        
        haslower = (start & mask) != 0
        hasupper = (end & mask) != mask
        
        not_mask = ~mask & ((1 << valsize + 1) - 1)
        nextstart = (start + diff if haslower else start) & not_mask
        nextend = (end - diff if hasupper else end) & not_mask
        
        if shift + step >= valsize or nextstart > nextend:
            yield (start, setbits(end), shift)
            break
        
        if haslower:
            yield (start, setbits(start | mask), shift)
        if hasupper:
            yield (end & not_mask, setbits(end), shift)
        
        start = nextstart
        end = nextend
        shift += step


def tiered_ranges(numtype, signed, start, end, shift_step, startexcl, endexcl):
    # First, convert the start and end of the range to sortable representations
    
    valsize = 32 if numtype is int else 64
    
    # Convert start and end values to sortable ints
    if start is None:
        start = 0
    else:
        if numtype is int:
            start = int_to_sortable_int(start, signed)
        elif numtype is long:
            start = long_to_sortable_long(start, signed)
        elif numtype is float:
            start = float_to_sortable_long(start, signed)
        if startexcl: start += 1
    
    if end is None:
        end = _max_sortable_int if valsize == 32 else _max_sortable_long
    else:
        if numtype is int:
            end = int_to_sortable_int(end, signed)
        elif numtype is long:
            end = long_to_sortable_long(end, signed)
        elif numtype is float:
            end = float_to_sortable_long(end, signed)
        if endexcl: end -= 1
    
    if numtype is int:
        to_text = sortable_int_to_text
    else:
        to_text = sortable_long_to_text
    
    if not shift_step:
        yield (to_text(start), to_text(end))
        return
    
    # Yield the term ranges for the different resolutions
    for rstart, rend, shift in split_range(valsize, shift_step, start, end):
        starttext = to_text(rstart, shift=shift)
        endtext = to_text(rend, shift=shift)
        yield (starttext, endtext)


# Functions for encoding numeric values as sequences of 7-bit ascii characters

def to_7bit(x, islong):
    if not islong:
        shift = 31
        nchars = 5
    else:
        shift = 63
        nchars = 10

    buffer = array("c", "\x00" * nchars)
    x += (1 << shift) - 1
    while x:
        buffer[nchars - 1] = chr(x & 0x7f)
        x >>= 7
        nchars -= 1
    return buffer.tostring()

def from_7bit(text):
    if len(text) == 5:
        shift = 31
    elif len(text) == 10:
        shift = 63
    else:
        raise ValueError("text is not 5 or 10 bytes")

    x = 0
    for char in text:
        x <<= 7
        char = ord(char)
        if char > 0x7f:
            raise Exception
        x |= char
    x -= (1 << shift) - 1
    return int(x)
