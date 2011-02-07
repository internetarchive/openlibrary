import web, re
from infogami.utils.view import public

# some code from http://code.google.com/p/python-iptools/source/browse/trunk/src/iptools/__init__.py

# Copyright (c) 2008-2010, Bryan Davis
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without 
# modification, are permitted provided that the following conditions are met:
#     - Redistributions of source code must retain the above copyright notice, 
#     this list of conditions and the following disclaimer.
#     - Redistributions in binary form must reproduce the above copyright 
#     notice, this list of conditions and the following disclaimer in the 
#     documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" 
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE 
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE 
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE 
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR 
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF 
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS 
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN 
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) 
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE 
# POSSIBILITY OF SUCH DAMAGE.

def ip_to_long(ip):
    long_ip = 0
    for q in ip.split('.'):
        long_ip = (lngip << 8) | int(q)
    return long_ip

re_cidr = re.compile('^([0-9.]+)/(\d+)$')
re_ip_start_end = re.compile('^([0-9.]+)\s*-\s*([0-9.]+)$')

def ip_in_range(ip_range):
    ip_range = ip_range.strip()

    if web.ctx.ip == ip_range: # single IP
        return True

    m = re_cidr.match(ip_range)
    if m: # cidr
        quads = m.group(1).split('.')
        prefix = int(m.group(2))

        baseIp = 0
        for i in range(4):
            baseIp = (baseIp << 8) | int(len(quads) > i and quads[i] or 0)

        # keep left most prefix bits of baseIp
        shift = 32 - prefix
        start = baseIp >> shift << shift

        # expand right most 32 - prefix bits to 1
        mask = (1 << shift) - 1
        end = start | mask
    else:
        m = re_ip_start_end.match('^([0-9.]+)\s*-\s*([0-9.]+)$')
        if m:
            start = ip_to_long(m.group(1))
            end = ip_to_long(m.group(2))
        else:
            return False # unrecognized IP range

    return start <= web.ctx.ip <= end

@public
def in_library():
    for key in web.ctx.site.things({'type': '/type/library'}):
        l = web.ctx.site.get(key)
        if any(ip_in_range(r) for r in l.ip_ranges.splitlines()):
            return True
    return False
