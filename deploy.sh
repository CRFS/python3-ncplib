#!/bin/bash
set -e

pip install anaconda-client
python setup.py sdist
anaconda --token "${ANACONDA_TOKEN}" upload --force dist/*.tar.gz
