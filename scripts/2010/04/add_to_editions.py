import os, sys, re
from openlibrary.catalog.marc.all import files
from openlibrary.catalog.get_ia import read_marc_file
from openlibrary.catalog.marc.fast_parse import get_first_tag, get_contents, get_subfield_values, handle_wrapped_lines, get_tag_lines, get_all_subfields
from openlibrary.catalog.marc.new_parser import read_oclc, has_dot

base = '/1/edward/marc/'

langs = set([
    'aar', 'abk', 'ace', 'ach', 'ada', 'ady', 'afa', 'afr', 'aka', 'akk',
    'alb', 'ale', 'alg', 'amh', 'ang', 'apa', 'ara', 'arc', 'arm', 'arn',
    'arp', 'art', 'arw', 'ase', 'asm', 'ath', 'aus', 'ava', 'ave', 'awa',
    'aym', 'aze', 'bai', 'bak', 'bal', 'bam', 'ban', 'baq', 'bas', 'bat',
    'bel', 'bem', 'ben', 'ber', 'bho', 'bik', 'bin', 'bis', 'bla', 'bnt',
    'bos', 'bra', 'bre', 'btk', 'bua', 'bug', 'bul', 'bur', 'cai', 'cam',
    'car', 'cat', 'cau', 'ceb', 'cel', 'che', 'chg', 'chi', 'chk', 'chm',
    'chn', 'cho', 'chr', 'chu', 'chv', 'chy', 'cmc', 'cmn', 'cop', 'cor',
    'cos', 'cpe', 'cpf', 'cpp', 'cre', 'crh', 'crp', 'cus', 'cze', 'dak',
    'dan', 'dar', 'day', 'del', 'din', 'doi', 'dra', 'dua', 'dum', 'dut',
    'dyu', 'dzo', 'efi', 'egy', 'eka', 'elx', 'eng', 'enm', 'epo', 'esk',
    'esp', 'est', 'eth', 'ewe', 'ewo', 'fan', 'fao', 'far', 'fat', 'fij',
    'fil', 'fin', 'fiu', 'fon', 'fre', 'fri', 'frm', 'fro', 'fry', 'ful',
    'fur', 'gaa', 'gae', 'gag', 'gal', 'gay', 'gba', 'gem', 'geo', 'ger',
    'gez', 'gil', 'gla', 'gle', 'glg', 'glv', 'gmh', 'goh', 'gon', 'gor',
    'got', 'grb', 'grc', 'gre', 'grn', 'gua', 'guj', 'gul', 'hat', 'hau',
    'haw', 'hbs', 'heb', 'her', 'hil', 'him', 'hin', 'hmn', 'hmo', 'hun',
    'iba', 'ibo', 'ice', 'ido', 'ijo', 'iku', 'ilo', 'ina', 'inc', 'ind',
    'ine', 'inh', 'int', 'ipk', 'ira', 'iri', 'iro', 'ita', 'jav', 'jpn',
    'jpr', 'jrb', 'kaa', 'kab', 'kac', 'kal', 'kam', 'kan', 'kar', 'kas',
    'kau', 'kaw', 'kaz', 'kbd', 'kha', 'khi', 'khm', 'kho', 'kik', 'kin',
    'kir', 'kmb', 'kok', 'kom', 'kon', 'kor', 'kos', 'kpe', 'krc', 'kro',
    'kru', 'kua', 'kum', 'kur', 'lad', 'lah', 'lam', 'lan', 'lao', 'lap',
    'lat', 'lav', 'lez', 'lin', 'lit', 'lol', 'loz', 'ltz', 'lua', 'lub',
    'lug', 'lun', 'luo', 'lus', 'mac', 'mad', 'mag', 'mah', 'mai', 'mak',
    'mal', 'man', 'mao', 'map', 'mar', 'mas', 'may', 'men', 'mic', 'min',
    'mis', 'mkh', 'mla', 'mlg', 'mlt', 'mnc', 'mni', 'mno', 'moh', 'mol',
    'mon', 'mos', 'mul', 'mun', 'mus', 'mwr', 'myn', 'nah', 'nai', 'nau',
    'nav', 'nbl', 'nde', 'ndo', 'nds', 'nep', 'new', 'nic', 'niu', 'non',
    'nor', 'nso', 'nub', 'nya', 'nyn', 'nyo', 'nzi', 'oci', 'oji', 'ori',
    'orm', 'oss', 'ota', 'oto', 'paa', 'pag', 'pal', 'pam', 'pan', 'pap',
    'pau', 'peo', 'per', 'phi', 'pli', 'pol', 'pon', 'por', 'pra', 'pro',
    'pus', 'que', 'raj', 'rar', 'roa', 'roh', 'rom', 'rum', 'run', 'rus',
    'sag', 'sah', 'sai', 'sal', 'sam', 'san', 'sao', 'sas', 'sat', 'scc',
    'sco', 'scr', 'sel', 'sem', 'shn', 'sho', 'sid', 'sin', 'sio', 'sit',
    'sla', 'slo', 'slv', 'smi', 'smo', 'sna', 'snd', 'snh', 'snk', 'sog',
    'som', 'son', 'sot', 'spa', 'srd', 'srr', 'ssa', 'sso', 'ssw', 'suk',
    'sun', 'sus', 'sux', 'swa', 'swe', 'swz', 'syc', 'syr', 'tag', 'tah',
    'taj', 'tam', 'tar', 'tat', 'tel', 'tem', 'ter', 'tet', 'tgk', 'tgl',
    'tha', 'tib', 'tig', 'tir', 'tiv', 'tkl', 'tli', 'tmh', 'tog', 'ton',
    'tpi', 'tsi', 'tsn', 'tso', 'tsw', 'tuk', 'tum', 'tur', 'tut', 'tvl',
    'twi', 'tyv', 'udm', 'uga', 'uig', 'ukr', 'umb', 'und', 'urd', 'uzb',
    'vai', 'ven', 'vie', 'vls', 'wak', 'wal', 'war', 'wel', 'wen', 'wol',
    'xal', 'xho', 'yao', 'yap', 'yid', 'yor', 'ypk', 'yue', 'zap', 'znd',
    'zul', 'zun'])

def sources():
    for d in os.listdir(base):
#        if d.startswith('talis'):
#            continue
        if d.endswith('old'):
            continue
        if d == 'indcat':
            continue
        if not os.path.isdir(base + d):
            continue
        yield d

def iter_marc():
    rec_no = 0
    for ia in sources():
        print ia
        for part, size in files(ia):
            full_part = ia + "/" + part
            filename = base + full_part
            assert os.path.exists(filename)
            print filename
            f = open(filename)
            for pos, loc, data in read_marc_file(full_part, f):
                rec_no +=1
                yield rec_no, pos, loc, data

# source_record,oclc,accompanying_material,translated_from,title

re_oclc = re.compile ('^\(OCoLC\).*?0*(\d+)')

out = open('/3/edward/updates', 'w')
want = set(['001', '003', '035', '041', '245', '300'])
for rec_no, pos, loc, data in iter_marc():
    fields = {}
    rec = {}
    title_seen = False
    for tag, line in handle_wrapped_lines(get_tag_lines(data, want)):
        if tag == '245':
            if title_seen:
                continue
            title_seen = True
            if line[1] == '0': # no prefix
                continue
            contents = get_contents(line, ['a', 'b'])
            if 'a' in contents:
                rec['title'] = ' '.join(x.strip(' /,;:') for x in contents['a'])
            elif 'b' in contents:
                rec['title'] = contents['b'][0].strip(' /,;:')
            if 'title' in rec and has_dot(rec['title']):
                rec['title'] = rec['title'][:-1]
            continue
        if tag == '300':
            if 'accompanying_material' in rec:
                continue
            subtag_e = ' '.join(i.strip('. ') for i in get_subfield_values(line, set(['e'])))
            if subtag_e:
                if subtag_e.lower() in ('list', 'notes', 'book'):
                    continue
                rec['accompanying_material'] = subtag_e
            continue
        fields.setdefault(tag, []).append(line)

    for line in fields.get('041', []):
        found = []
        marc_h = list(get_subfield_values(line, 'h'))
        if not marc_h:
            continue
        for h in marc_h:
            if len(h) % 3 != 0:
                print 'bad:', list(get_all_subfields(line))
                continue
            found += ['/l/' + i for i in (h[i * 3:(i+1) * 3].lower() for i in range(len(h) / 3)) if i in langs]
        if found:
            rec.setdefault('translated_from', []).extend(found)

    rec.update(read_oclc(fields))

    if rec:
        rec['source_record'] = loc
        print >> out, rec
out.close()
