import os

arc_dir = '/2/edward/amazon/arc'

def read_arc(filename):
    f = open(arc_dir + '/' + filename)
    idx = open(arc_dir + '/' + filename + '.idx', 'w')
    while True:
        pos = f.tell()
        line = f.readline()
        if line == '':
            break
        print >> idx, pos
        size = int(line[:-1].split(' ')[4])
        f.read(size)
        line = f.readline()
    f.close()
    idx.close()

for filename in (i for i in os.listdir(arc_dir) if i.endswith('.arc')):
    print filename
    read_arc(filename)
