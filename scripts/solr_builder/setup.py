from pathlib import Path

from Cython.Build import cythonize
from setuptools import setup

setup(
    py_modules=['solr_builder'],
    ext_modules=cythonize(
        str(Path(__file__).parent / "solr_builder" / "solr_builder.py"),
        compiler_directives={'language_level': "3"},
    ),
)
