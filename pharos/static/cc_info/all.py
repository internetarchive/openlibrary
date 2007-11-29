import re, urllib, os.path

becky = 'http://invisible.net/openlibrary/copyright/'

bl = ('moreinfo_unknown_copyright.html',
      'moreinfo_in_copyright.html',
      'moreinfo_out_copyright.html',
      )

f='\n'.join((urllib.urlopen(becky+b).read()) for b in bl)

pat = '"(Shade_of_Raintree_County_files/[^"]+)"'
print len(f)

fl = sorted(set(re.findall(pat, f)))

def get(fn):
    c = '%s/%s'% (becky, fn)
    bn = os.path.basename(fn)
    if os.path.exists(bn):
        print '* %s exists'% bn
        return
    of = open(bn, 'w')
    b = urllib.urlopen(c).read()
    print '* %s: %d bytes'% (bn, len(b))
    of.write(b)
    of.close()

map(get, fl)
