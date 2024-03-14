from pathlib import Path
from setuptools import setup
from Cython.Build import cythonize

setup(
    ext_modules=cythonize(
        str(Path(__file__).parent / "solr_builder" / "solr_builder.py"),
        compiler_directives={'language_level': "3"},
    )
)
