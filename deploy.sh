#!/bin/bash
set -e
shopt -s nullglob

pip install anaconda-client
python setup.py sdist
anaconda --token "${ANACONDA_TOKEN}" upload --force dist/*.tar.gz
