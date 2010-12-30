from setuptools import setup, find_packages
import glob, os
from stat import *

def executable(path):
    st = os.stat(path)[ST_MODE]
    return (st & S_IEXEC) and not S_ISDIR(st)

try:
    from sphinx.setup_command import BuildDoc
except ImportError:
    BuildDoc = None

dependencies = """
Babel
PIL
argparse
couchdb
genshi
gunicorn
lxml
psycopg2
pymarc
python-memcached
pyyaml
simplejson
sphinx
supervisor
web.py==0.33
"""

cmdclass = {}

if BuildDoc:
    class OLBuildDoc(BuildDoc):
        def run(self):
            print "generating API docs..."
            os.system("python scripts/generate-api-docs.py")
            BuildDoc.run(self)
    cmdclass['build_sphinx'] = OLBuildDoc

setup(
    name='openlibrary',
    version='2.0',
    description='OpenlibraryBot',
    packages=find_packages(exclude=["ez_setup"]),
    scripts=filter(executable, glob.glob('scripts/*')),
    install_requires=dependencies.split(),
    cmdclass=cmdclass
)

