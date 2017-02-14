# -*- coding: utf-8 -*-
# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
# vi: set ft=python sts=4 ts=4 sw=4 et:
"""
Base module variables
"""
from __future__ import unicode_literals

__author__ = '...'
__version__ = '99.99.99'
__copyright__ = 'Copyright 2016, Center for Reproducible Neuroscience, Stanford University'
__license__ = '3-clause BSD'
__maintainer__ = 'Ross Blair'
__email__ = 'rosswilsonblair@gmail.com'
__status__ = 'Prototype'
__url__ = 'https://github.com/rwblair/motcorr_comp'
__packagename__ = 'motcorr_comp'
__description__ = """"""
__longdesc__ = """
"""

DOWNLOAD_URL = (
    'https://pypi.python.org/packages/source/{name[0]}/{name}/{name}-{ver}.tar.gz'.format(
        name=__packagename__, ver=__version__))

REQUIRES = [
    'numpy',
    'lockfile',
    'future',
    'scikit-learn',
    'matplotlib',
    'nilearn',
    'sklearn',
    'nibabel',
    'pandas',
    'grabbit',
    'pybids>=0.0.1',
    'nitime',
    'niworkflows',
    'nipype>=0.13.0rc1'
]

LINKS_REQUIRES = []

TESTS_REQUIRES = [
    "mock",
    "codecov"
]

EXTRA_REQUIRES = {
    'doc': ['sphinx'],
    'tests': TESTS_REQUIRES,
    'duecredit': ['duecredit']
}

# Enable a handle to install all extra dependencies at once
EXTRA_REQUIRES['all'] = [val for _, val in list(EXTRA_REQUIRES.items())]
CLASSIFIERS = [
    'Development Status :: 3 - Alpha',
    'Intended Audience :: Science/Research',
    'Topic :: Scientific/Engineering :: Image Recognition',
    'License :: OSI Approved :: BSD License',
    'Programming Language :: Python :: 2.7',
    'Programming Language :: Python :: 3.5',
]
