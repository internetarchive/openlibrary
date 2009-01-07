scanned = set(i[:-1] for i in open('scanned'))
loaded = set(i[:-1] for i in open('loaded'))

to_load = scanned - loaded
for i in sorted(to_load):
    print i
