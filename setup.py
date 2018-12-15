from setuptools import setup, find_packages
import glob, os
from stat import *

def executable(path):
    st = os.stat(path)[ST_MODE]
    return (st & S_IEXEC) and not S_ISDIR(st)

classifiers = """License :: OSI Approved :: GNU Affero General Public License v3
Natural Language :: English
Programming Language :: Python
Programming Language :: Python :: 2
Programming Language :: Python :: 2.7
Programming Language :: Python :: Implementation :: CPython
Programming Language :: Python :: Implementation :: PyPy""".splitlines()

# TODO: Add the following:
"""
Programming Language :: Python :: 3
Programming Language :: Python :: 3.4
Programming Language :: Python :: 3.5
Programming Language :: Python :: 3.6
Programming Language :: Python :: 3.7
"""

dependencies = """
Babel
PIL
argparse
beautifulsoup4
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
supervisor
web.py==0.33
pystatsd
eventer
Pygments
OL-GeoIP
mockcache
"""

setup(
    name='openlibrary',
    version='2.0',
    description='Open Library',
    packages=find_packages(exclude=["ez_setup"]),
    scripts=filter(executable, glob.glob('scripts/*')),
    install_requires=dependencies.split()
)

