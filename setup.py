# setup.py is only used by solrbuilder to cythonize some files See
# scripts/solr_builder/build-cython.sh We might be able to remove
# it entirely if we call cython directly from that script.
from Cython.Build import cythonize
from setuptools import find_packages, setup

setup(
    # Used to make solrbuilder faster
    packages=find_packages(include=['openlibrary', 'openlibrary.*']),
    ext_modules=cythonize(
        "openlibrary/solr/update.py", compiler_directives={'language_level': "3"}
    ),
)
