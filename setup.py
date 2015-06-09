from setuptools import setup, find_packages

from ncplib import __version__


version_str = ".".join(str(n) for n in __version__)
        

setup(
    name = "ncplib",
    version = version_str,
    description = "CRFS NCP library for Python 3.",
    author = "Dave Hall",
    author_email = "dhall@crfs.com",
    url = "https://github.com/CRFS/python3-ncplib",
    packages = find_packages(),
    classifiers = [
        "Development Status :: 4 - Beta",
        "Environment :: Web Environment",
        "Intended Audience :: Developers",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.4",
    ],
    extras_require = {
        "dev":  [
            "nose",
            "coverage",
        ],
    },
)
