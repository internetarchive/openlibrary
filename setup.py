from setuptools import setup, find_packages
import glob, os
from stat import *

def executable(path):
    st = os.stat(path)[ST_MODE]
    return (st & S_IEXEC) and not S_ISDIR(st)

setup(
    name='openlibrary',
    version='2.0',
    description='OpenlibraryBot',
    packages=find_packages(exclude=["ez_setup"]),
    scripts=filter(executable, glob.glob('scripts/*')),
    install_requires='web.py==0.33 Babel pyyaml psycopg2 simplejson python-memcached lxml PIL pymarc genshi couchdb argparse supervisor'.split(),
)
