from catalog.marc.fast_parse import get_all_subfields
import re

samples = [
    "00\x1faDi 1 juan.Guo se tian xiang /Wu Jingsuo bian.Ba duan jin /Xingshizhushi bian ji --di 2 juan.Wu sheng xi ;Shi er lou /Li Yu --di 3 juan.Jin xiang ting /Su'anzhuren bian.\x1ftFen zhuang lou /Zhuxishanren --\x1fgdi 4 juan.Wu se shi /Bilian'gezhuren.Ba dong tian /Wuseshizhuren.Wu feng yin /Chichi dao ren bian zhu --di 5 juan.Shuang feng qi yuan /Xueqiaozhuren zi ding.Jin shi yuan.Qing meng tuo /Anyangjiumin --di 6 juan.Wu mei yuan.Xiu qiu yuan.Yuan yang ying /Qiaoyunshanren bian --di 7 juan.Mei ren shu /Xu Zhen.Wan hua lou /Li Yutang --di 8 juan.Bei shi yan yi /Du Gang.Kong kong huan /Wugangzhuren bian ci.Chun qiu pei --di 9 juan.Qian Qi guo zhi /Wumenxiaoke.Hou Qi guo zhi /Yanshuisanren.Qiao shi yan yi /Lu Yingyang --di 10 juan.Liaohai dan zhong lu /Lu Renlong.Tian bao tu.Jin xiu yi --di 11 juan.Shi mei tu.Huan xi yuan jia /Xihuyuyinzhuren.Feng liu he shang.Liang jiao hun /Tianhuazangzhuren --di 12 juan.Ge lian hua ying.Qi lou chong meng /Wang Lanzhi.\x1e",
    '00\x1ftManierismus als Artistik : systematische Aspekte einer \xe8asthetischen Kategorie / R\xe8udiger Zymner -- "Stil" und "Manier" in der Alltagskultur / Kaspar Maase -- Die Wortfamilie von it. "Maniera" zwischen Literatur, bildender Kunst und Psychologie / Margarete Lindemann -- Der Manierismus : zur Problematik einer kunsthistorischen Erfindung / Horst Bredekamp -- Inszenierte K\xe8unstlichkeit : Musik als manieristisches Dispositiv / Hermann Danuser -- Manierismus als Stilbegriff in der Architekturgeschichte / Hermann Hipp -- "Raffael ohne H\xe8ande," oder, Das Kunstwerk zwischen Sch\xe8opfung und Fabrikation : Konzepte der "maniera" bei Vasari und seinen Zeitgenossen / Ursula Link-Heer -- "Sprezzatura" : Pontormos Portraits und das h\xe8ofische Ideal des Manierismus / Axel Christoph Gampp -- Maniera and the grotesque / Maria Fabricius Hansen -- Neulateinisches Figurengedicht und manieristische Poetik : zum "Poematum liber" (1573) des Richard Willis / Ulrich Ernst -- Manierismus als Selbstbehauptung, Jean Paul / Wolfgang Braungart --  Artistische Erkenntnis : (Sprach-)Alchimie und Manierismus in der Romantik / Axel Dunker -- "Als lebeten sie" / Holk Cruse.\x1e',
]

re_gt = re.compile('^(gt)+$')
re_gtr = re.compile('^(gtr)+$')
re_at = re.compile('^at+$')
re_end_num = re.compile('\d[]. ]*$')
for line in open('test_data/marc_toc'):
    (loc, line) = eval(line)
    #print loc
    subfields = list(get_all_subfields(line))
    if subfields[0][0] == '6':
        subfields.pop(0)
    subtags = ''.join(k for k, v in subfields)
    if re_at.match(subtags):
        a = subfields[0][1]
        m = re_end_num.search(a)
        print bool(m), `a`
        continue

        if not m:
            for k, v in subfields:
                print k, `v`
        assert m
    continue
    if re_gtr.match(subtags):
        continue
        for i in range(len(subfields)/3):
            g = subfields[i * 3][1]
            t = subfields[i * 3 + 1][1].strip('- /')
            r = subfields[i * 3 + 2][1].strip('- ')
            print `g, t, r`
        print
        continue
    if re_gt.match(subtags):
        continue
        for i in range(len(subfields)/2):
            g = subfields[i * 2][1]
            t = subfields[i * 2 + 1][1].strip('- /')
            print `g, t`
        print
        continue
    print subtags
    for k, v in subfields:
        print k, `v`
    print
