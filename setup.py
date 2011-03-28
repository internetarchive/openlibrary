from setuptools import setup, find_packages
import glob, os
from stat import *

def executable(path):
    st = os.stat(path)[ST_MODE]
    return (st & S_IEXEC) and not S_ISDIR(st)

dependencies = """
Babel
PIL
argparse
BeautifulSoup
CouchDB==0.8
DBUtils
genshi
gunicorn
iptools
lxml
psycopg2
pymarc
pytest
python-memcached
pyyaml
simplejson
sphinx
supervisor
web.py==0.33
"""

from openlibrary.core.setup_commands import commands

setup(
    name='openlibrary',
    version='2.0',
    description='Open Library',
    packages=find_packages(exclude=["ez_setup"]),
    scripts=filter(executable, glob.glob('scripts/*')),
    install_requires=dependencies.split(),
    cmdclass=commands
)

