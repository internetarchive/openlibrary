import os, os.path, subprocess, sys, md5

import locale # PHP sort order
locale.setlocale(locale.LC_ALL, 'en_US')

os.chdir('/2/pharos/lc_updates/marc_loc_updates')

print "checking for new files"
# the Python FTP library doesn't work for LoC, so use Perl
download_count = int(subprocess.Popen(["/usr/bin/perl", "../get.pl"], stdout=subprocess.PIPE).communicate()[0])

if download_count == 0: # no new data
    print "no new files available"
    sys.exit(0)

print download_count, "new files downloaded"

def shellcall(*args):
    p = subprocess.Popen(args, stdout=subprocess.PIPE)
    return p.stdout.read()
 
def md5sum(filename):
    return shellcall('md5sum', '--', filename).split()[0]

def sha1sum(filename):
    return shellcall('sha1sum', '--', filename).split()[0]

for fn in os.listdir('.'):
    assert not fn.endswith('~')

def files_xml_one(fn):
    if fn.endswith('_meta.xml'):
        format = "Metadata"
    elif fn.endswith('.txt'):
        format = 'Text'
    else:
        format = "Data"
    fn_stat = os.stat(fn)
    md5hash = md5sum(fn)
    sha1hash = sha1sum(fn) 
    
    out = ''
    out += '  <file name="%s" source="original">\n' % fn.replace('&', '&amp;')
    out += '    <format>%s</format>\n' % format
    out += '    <size>%s</size>\n' % fn_stat.st_size
    out += '    <md5>%s</md5>\n' % md5hash
    out += '    <sha1>%s</sha1>\n' % sha1hash
    out += '  </file>\n'
    
    return out, ((fn, md5hash))

def files_xml_all(itemid, fnlst):
    files_l = [] # for calculating canonical md5

    out = '<files>\n'
    for fn in fnlst:
        tmp = files_xml_one(fn)
        out += tmp[0]
        files_l.append(tmp[1])
    
    files_l.sort(lambda x, y: locale.strcoll(x[0], y[0]))
    
    files_lout = ''
    for file_l in files_l:
        files_lout += '%s %s\n' % file_l
    files_md5 = md5.md5(files_lout).hexdigest()
    
    out += '  <file name="%s_files.xml" source="metadata">\n' % itemid
    out += '    <format>Metadata</format>\n'
    out += '    <md5>%s</md5>\n' % files_md5
    out += '  </file>\n'
    
    out += '</files>\n'

    open(itemid + '_files.xml', 'w').write(out)

item_id = 'marc_loc_updates'
fnlst = [x for x in os.listdir('.') if not x.endswith('_files.xml')]
print 'generating files.xml'
files_xml_all(item_id, fnlst)

print 'uploading to archive.org'
subprocess.call(['/home/aaronsw/bin/uploaditem.py', '--update'])
