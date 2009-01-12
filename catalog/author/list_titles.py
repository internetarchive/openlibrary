titles = {}
with_title = {}

for line in open("/1/pharos/edward/titles"):
    try:
        loc, fields = eval(line)
    except SyntaxError:
        break
    except ValueError:
        continue
    t = [b for a, b in fields if a == 'c']
    if len(t) != 1:
        continue
    fields = tuple((a, b.strip('.') if a=='d' else b) for a, b in fields)
    title = t[0].strip(' ,.').lower()
    titles[title] = titles.get(title, 0) + 1
    with_title.setdefault(title, {})
    with_title[title][fields] = with_title[title].get(fields, 0) + 1

for k, v in sorted(((a, b) for a, b in titles.items() if b > 10), reverse=True, key=lambda x: x[1]):
    print `k`, v
    for a, b in sorted(((a, b) for a, b in with_title[k].items() if b > 5), reverse=True, key=lambda x: x[1])[0:30]:
        print '  ', a, b
    print
