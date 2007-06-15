# modified (for compatibility) from the module with the following license:

# netstring.py - Netstring encoding/decoding routines.
# Version 1.1 - July 2003
# http://www.dlitz.net/software/python-netstring/
#
# Copyright (c) 2003 Dwayne C. Litzenberger <dlitz@dlitz.net>
# 
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
# 
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#
# HISTORY:
#
# Changes between 1.0 and 1.1:
# - Renamed Reader to BaseReader.  Use FileReader and StringReader instead.
# - Added BaseReader.readskip()
# - Switched to saner stream reading semantics.  Now the stream is not read
#   until information is requested which requires it to be read.
# - Added split()
#

import StringIO

maxintlen = 999     # Maximum number of digits when reading integers
                    # This allows numbers up to 10**1000 - 1, which should
                    # be large enough for most applications. :-)


def dump(s, file):
    """dump(s, file) -> None

Writes the string s as a netstring to file.
"""
    file.write(dumps(s))


def dumps(s):
    """dumps(s) -> string

Encodes the string s as a netstring, and returns the result.
"""
    return str(len(s)) + ":" + s + ","


def load(file, maxlen=None):
    """load(file, maxlen=None) -> string

Read a netstring from a file, and return the extracted netstring.

If the parsed string would be longer than maxlen, OverflowError is raised.
"""
    n = _readlen(file)
    if maxlen is not None and n > maxlen:
        raise OverflowError
    retval = file.read(n)
    #assert(len(retval) == n)
    ch = file.read(1)
    if ch == "":
        raise EOFError
    elif ch != ",":
        raise ValueError
    return retval


def loads(s, maxlen=None, returnUnparsed=False):
    """loads(s, maxlen=None, returnUnparsed=False) -> string or (string,
    string)

Extract a netstring from a string.  If returnUnparsed is false, return the
decoded netstring, otherwise return a tuple (parsed, unparsed) containing both
the parsed string and the remaining unparsed part of s.

If the parsed string would be longer than maxlen, OverflowError is raised.
"""
    f = StringIO.StringIO(s)
    parsed = load(f, maxlen=maxlen)
    if not returnUnparsed:
        return parsed
    unparsed = f.read()
    return parsed, unparsed


def _readlen(file):
    """_readlen(file) -> integer

Read the initial "[length]:" of a netstring from file, and return the length.
"""
    i = 0
    n = ""
    ch = file.read(1)
    while ch != ":":
        if ch == "":
            raise EOFError
        elif not ch in "0123456789":
            raise ValueError
        n += ch
        i += 1
        if i > maxintlen:
            raise OverflowError
        ch = file.read(1)
    #assert(ch == ":")
    return long(n)


def split(s):
    """split(s) -> list of strings

Return a list of the decoded netstrings in s.
"""
    if s == "":
    	raise EOFError
    retval = []
    unparsed = s
    while unparsed != "":
        parsed, unparsed = loads(unparsed, returnUnparsed=True)
        retval.append(parsed)
    return retval

