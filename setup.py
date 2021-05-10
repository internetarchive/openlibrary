import glob
import os

from setuptools import setup
from stat import ST_MODE, S_IEXEC, S_ISDIR
from Cython.Build import cythonize

def executable(path):
    st = os.stat(path)[ST_MODE]
    return (st & S_IEXEC) and not S_ISDIR(st)


setup(
    name='openlibrary',
    version='2.0',
    description='Open Library',
    scripts=filter(executable, glob.glob('scripts/*')),
    # Used to make solrbuilder faster
    ext_modules=cythonize(
        "openlibrary/solr/update_work.py",
        compiler_directives={'language_level': "3"})
)
