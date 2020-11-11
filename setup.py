# Copyright (C) 2019 Nicolas Legrand
import os


def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()


DESCRIPTION = """Hierarchical meta-d' model"""

DISTNAME = "metadPy"
MAINTAINER = "Nicolas Legrand"
MAINTAINER_EMAIL = "nicolas.legrand@cfin.au.dk"
VERSION = "0.0.1"

INSTALL_REQUIRES = [
    "numpy>=1.18.1",
    "scipy>=1.3",
    "pandas>=0.24",
    "matplotlib>=3.1.3",
    "pymc3>=3.8",
    "seaborn>=0.10.0",
]

PACKAGES = [
    "metadPy",
]

try:
    from setuptools import setup

    _has_setuptools = True
except ImportError:
    from distutils.core import setup

if __name__ == "__main__":

    setup(
        name=DISTNAME,
        author=MAINTAINER,
        author_email=MAINTAINER_EMAIL,
        maintainer=MAINTAINER,
        maintainer_email=MAINTAINER_EMAIL,
        description=DESCRIPTION,
        long_description=open("README.rst").read(),
        long_description_content_type="text/x-rst",
        license="GPL-3.0",
        version=VERSION,
        install_requires=INSTALL_REQUIRES,
        include_package_data=True,
        packages=PACKAGES,
    )
