from setuptools import setup, find_packages

from ncplib import __version__


setup(
    name="ncplib",
    version=".".join(map(str, __version__)),
    license="BSD",
    description="CRFS NCP library for Python 3.",
    author="Dave Hall",
    author_email="dhall@crfs.com",
    url="https://github.com/CRFS/python3-ncplib",
    packages=find_packages(exclude="tests"),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Web Environment",
        "Intended Audience :: Developers",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.5",
    ],
)
