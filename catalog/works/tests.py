from collections import defaultdict
import re
import catalog.merge.normalize as merge

def freq_dict_top(d):
    return sorted(d.keys(), reverse=True, key=lambda i:d[i])[0]

re_brackets = re.compile('^(.*)\[.*?\]$')
re_parens = re.compile('^(.*?)(?: \(.+ (?:Edition|Press)\))+$')

def mk_norm(title):
    m = re_brackets.match(title)
    if m:
        title = m.group(1)
    norm = merge.normalize(title).strip(' ')
    norm = norm.replace(' and ', ' ')
    if norm.startswith('the '):
        norm = norm[4:]
    elif norm.startswith('a '):
        norm = norm[2:]
    return norm.replace('-', '').replace(' ', '')

def build_work_title_map(equiv, norm_titles):
    title_to_work_title = defaultdict(set)
    for (norm_title, norm_wt), v in equiv.items():
        if v != 1:
            title_to_work_title[norm_title].add(norm_wt)

    title_map = {}
    for title, v in title_to_work_title.items():
        if len(v) == 1:
            title_map[title] = list(v)[0]
            continue
        most_common_title = max(v, key=lambda i:norm_titles[i])
        if title != most_common_title:
            title_map[title] = most_common_title
        for i in v:
            if i != most_common_title:
                title_map[i] = most_common_title
    return title_map


milo_m_hastings = [
    {'lang': ['eng'], 'key': '/b/OL7009753M', 'title': 'The dollar hen'},
    {'lang': ['eng'], 'key': '/b/OL9563276M', 'title': 'The Dollar Hen (Large Print Edition)'},
    {'lang': ['eng'], 'key': '/b/OL9636071M', 'title': 'The Dollar Hen'},
    {'lang': ['eng'], 'key': '/b/OL15083244M', 'title': 'The dollar hen'},
    {'lang': ['eng'], 'key': '/b/OL8566971M', 'title': 'The Dollar Hen'},
    {'lang': ['eng'], 'key': '/b/OL9353753M', 'title': 'City of Endless Night'},
    {'lang': ['eng'], 'key': '/b/OL9462083M', 'title': 'City of Endless Night (Large Print Edition)'},
    {'lang': ['eng'], 'key': '/b/OL9642528M', 'title': 'The Dollar Hen'},
    {'lang': ['eng'], 'key': '/b/OL9736536M', 'title': 'The Dollar Hen'},
    {'lang': ['eng'], 'key': '/b/OL9735362M', 'title': 'The Dollar Hen (Illustrated Edition) (Dodo Press)'},
    {'lang': ['eng'], 'key': '/b/OL9800490M', 'title': 'The Dollar Hen'},
    {'lang': ['eng'], 'key': '/b/OL11676559M', 'title': 'City of Endless Night (Dodo Press)'},
    {'lang': ['eng'], 'key': '/b/OL11752220M', 'title': 'The Dollar Hen'},
    {'lang': ['eng'], 'key': '/b/OL11985500M', 'title': 'The Dollar Hen'},
    {'lang': ['eng'], 'key': '/b/OL11985503M', 'title': 'The Dollar Hen'}
]

aaron_bancroft = [ # /a/OL17005A
    {'lang': ['eng'], 'key': '/b/OL595471M', 'title': 'A sermon preached before His Excellency Caleb Strong, Esq., Governour, the Honourable the Council, Senate, and House of Representatives of the commonwealth of Massachusetts, May 27, 1801'},
    {'lang': ['eng'], 'key': '/b/OL1247387M', 'title': 'A discourse delivered before the convention of Congregational ministers of Massachusetts, at their annual meeting in Boston, June 1, 1820'},
    {'lang': ['eng'], 'key': '/b/OL6472976M', 'title': 'The importance of a religious education illustrated and enforced'},
    {'lang': ['eng'], 'key': '/b/OL6919451M', 'title': 'A discourse delivered at Windsor, in the state of Vermont, on the 23rd of June, MDCCXC'},
    {'lang': ['eng'], 'key': '/b/OL6950265M', 'title': 'A sermon delivered in Worcester, January 31, 1836'},
    {'key': '/b/OL7048038M', 'title': 'Sermons on those doctrines of the gospel, and on those constituent principles of the church, which Christian professors have made the subject of controversy. ..'},
    {'key': '/b/OL7197334M', 'title': 'The life of George Washington ....'},
    {'lang': ['eng'], 'key': '/b/OL14572992M', 'title': 'A sermon, delivered at Worcester, on the eleventh of June, 1793'},
    {'lang': ['eng'], 'key': '/b/OL14588026M', 'title': 'An eulogy on the character of the late Gen. George Washington.'},
    {'lang': ['eng'], 'key': '/b/OL14601446M', 'title': 'A sermon, delivered at Brimfield, on the 20th of June, 1798'},
    {'lang': ['eng'], 'key': '/b/OL14608347M', 'title': 'The importance of a religious education illustrated and enforced.'},
    {'lang': ['eng'], 'key': '/b/OL14702050M', 'title': 'The nature and worth of Christian liberty'},
    {'lang': ['eng'], 'key': '/b/OL14981988M', 'title': 'A vindication of the result of the late Mutual Council convened in Princeton'},
    {'lang': ['eng'], 'key': '/b/OL14992328M', 'title': 'An essay on the life of George Washington'},
    {'lang': ['eng'], 'key': '/b/OL15054440M', 'title': 'Importance of education'},
    {'lang': ['eng'], 'key': '/b/OL15070888M', 'title': 'The leaf an emblem of human life'},
    {'lang': ['eng'], 'key': '/b/OL15075529M', 'title': 'The world passeth away, but the children of God abide forever'},
    {'lang': ['eng'], 'key': '/b/OL15085786M', 'title': 'The doctrine of immortality'},
    {'lang': ['eng'], 'key': '/b/OL15093560M', 'title': 'The comparative advantages of the ministerial profession'},
    {'lang': ['eng'], 'key': '/b/OL15115706M', 'title': 'The duties enjoined by the Fourth commandment'},
    {'lang': ['eng'], 'key': '/b/OL15120201M', 'title': 'A discourse on conversion'},
    {'lang': ['eng'], 'key': '/b/OL15120290M', 'title': 'The nature and worth of Christian liberty'},
    {'lang': ['eng'], 'key': '/b/OL17052663M', 'title': 'An eulogy on the character of the late Gen. George Washington'},
    {'lang': ['eng'], 'key': '/b/OL17704747M', 'title': 'The doctrine of immortality'},
    {'lang': ['eng'], 'key': '/b/OL17707429M', 'title': 'Importance of education'},
    {'lang': ['eng'], 'key': '/b/OL17709244M', 'title': 'A vindication of the result of the late mutual council convened in Princeton'},
    {'lang': ['eng'], 'key': '/b/OL18776110M', 'title': 'Sermons on those doctrines of the gospel, and on those constituent principles of the church, which Christian professors have made the subject of controversy'},
    {'lang': ['eng'], 'key': '/b/OL6573411M', 'title': 'The life of George Washington, commander in chief of the American army, through the revolutionary war'},
    {'lang': ['eng'], 'key': '/b/OL15592993M', 'title': 'A discourse on conversion'},
    {'lang': ['eng'], 'key': '/b/OL17712475M', 'title': 'A discourse on conversion'},
    {'lang': ['eng'], 'key': '/b/OL6290214M', 'title': 'The life of George Washington'},
    {'lang': ['eng'], 'key': '/b/OL6571503M', 'title': 'The life of George Washington'},
    {'lang': ['eng'], 'key': '/b/OL6573412M', 'title': 'Life of George Washington'},
    {'work_title': 'Essay on the life of George Washington', 'key': '/b/OL7168113M', 'title': 'Life of George Washington, commander in chief of the American army through the revolutionary war, and the first president of the United States.'},
    {'work_title': 'Essay on the life of George Washington', 'key': '/b/OL7243025M', 'title': 'The life of George Washington, commander in chief of the American army, through the revolutionary war, and the first president of the United States'},
    {'lang': ['eng'], 'key': '/b/OL28289M', 'title': 'The life of George Washington, commander-in-chief of the American Army through the Revolutionary War and the first President of the United States'},
    {'lang': ['eng'], 'key': '/b/OL6354818M', 'title': 'The life of George Washington, commander-in-chief of the American Army through the revolutionary war, and the first president of the United States.'},
    {'key': '/b/OL7113589M', 'title': 'The life of George Washington, Commander-in-Chief of the American Army, through the Revolutionary War; and the first President of the United States.'}
]

def find_works(books):
    for book in books:
        m = re_parens.match(book['title'])
        if m:
            book['title'] = m.group(1)
        n = mk_norm(book['title'])
        book['norm_title'] = n

    books_by_key = dict((b['key'], b) for b in books)
    norm_titles = defaultdict(int)

    for book in books:
        norm_titles[book['norm_title']] += 1

    title_map = build_work_title_map({}, norm_titles)

    works = defaultdict(lambda: defaultdict(list))
    work_titles = defaultdict(list)
    for b in books:
        if 'eng' not in b.get('lang', []) and 'norm_wt' in b:
            work_titles[b['norm_wt']].append(b['key'])
            continue
        n = b['norm_title']
        title = b['title']
        if n in title_map:
            n = title_map[n]
            title = freq_dict_top(rev_wt[n])
        works[n][title].append(b['key'])

    #for k, v in works.items():
    #    print k
    #    print '  ', sum(len(i) for i in v.values()), dict(v)
    #print

    works = sorted([(sum(map(len, w.values() + [work_titles[n]])), n, w) for n, w in works.items()])

    for a, b, c in works:
        print a, b, dict(c)

find_works(milo_m_hastings)
find_works(aaron_bancroft)
