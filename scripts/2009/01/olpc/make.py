import os

def system(cmd):
    print cmd
    os.system(cmd)

def copy_src():
    system('cp -r src/* dist/openlibrary')

def copy_gnubook():
    if os.path.exists('dist/bookreader'):
        system('cd dist/bookreader && git pull')
    else:
        system('git clone http://github.com/anandology/bookreader.git dist/bookreader > /dev/null')

    system('cp -r dist/bookreader/GnuBook dist/openlibrary/')

def copy_books():
    def copy(id):
        system('cd dist/downloads && wget -nv http://www.archive.org/download/%s/%s_flippy.zip' % (id, id))
        system('mkdir -p dist/openlibrary/books/' + id)
        system('unzip -u dist/downloads/%s_flippy.zip -d dist/openlibrary/books/%s > /dev/null' % (id, id))

    for id in open('books.index').read().split():
        copy(id)

def make_books_js():
    books = open('books.index').read().split()
    print 'creating dist/openlibrary/js/books.js'
    f = open('dist/openlibrary/js/books.js', 'w')
    f.write('var books = ')
    f.write(repr(books));
    f.write(';\n');
    f.close()

def main():
    system('mkdir -p dist/openlibrary dist/downloads')
    copy_src()
    copy_gnubook()
    copy_books()
    make_books_js()
    system('cd dist && zip -r openlibrary.xol openlibrary > /dev/null')
    print
    print "Activity file generated at: dist/openlibrary.xol"
    
if __name__ == "__main__":
    main()
