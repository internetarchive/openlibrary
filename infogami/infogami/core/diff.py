from difflib import SequenceMatcher

def better_diff(a, b):
    tracnames = dict(equal="", insert='add', replace='mod', delete='rem')

    map = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(a=a, b=b).get_opcodes():
        n = (j2-j1) - (i2-i1)

        x = a[i1:i2]
        xn = range(i1, i2)
        y = b[j1:j2]
        yn = range(j1, j2)

        if tag == 'insert':
            x += [''] * n
            xn += [''] * n
        elif tag == 'delete':
            y += [''] * -n
            yn += [''] * -n
        
        map += zip([tracnames[tag]] * len(x), xn, x, yn, y)

    return map
