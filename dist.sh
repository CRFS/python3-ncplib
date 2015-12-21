#!/bin/bash
set -e
shopt -s nullglob

# Environment.
OS_NAME=`uname -s | tr '[:upper:]' '[:lower:]'`
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Create a work space.
BUILD_DIR=`mktemp -d /tmp/build.XXXX`
MINICONDA_DIR="${BUILD_DIR}/miniconda"

# Clean up on exit.
clean() {
    rm -rf "${BUILD_DIR}"
}
trap clean EXIT

# Download miniconda.
echo "Started downloading miniconda"
if [ "${OS_NAME}" = "darwin" ]; then
    MINICONDA_INSTALL_URL="https://repo.continuum.io/miniconda/Miniconda3-latest-MacOSX-x86_64.sh"
else
    MINICONDA_INSTALL_URL="https://repo.continuum.io/miniconda/Miniconda3-latest-Linux-x86_64.sh"
fi
curl --location --silent "${MINICONDA_INSTALL_URL}" > "${BUILD_DIR}/miniconda.sh"
echo "Finished downloading miniconda"

# Install miniconda.
echo "Started installing Miniconda"
bash "${BUILD_DIR}/miniconda.sh" -b -p "${MINICONDA_DIR}"
echo "Finished installing Miniconda"

# Install build dependencies.
echo "Started installing build dependencies"
"${MINICONDA_DIR}/bin/conda" install --yes --quiet "python=${PYTHON_VERSION}" conda-build anaconda-client
echo "Finished installing build dependencies"

# Determine package version.
export PACKAGE_VERSION=`"${MINICONDA_DIR}/bin/python" -c 'import ncplib; print(".".join(map(str, ncplib.__version__)))'`

# Build the package.
echo "Started building package"
"${MINICONDA_DIR}/bin/conda" build --skip-existing --channel https://conda.anaconda.org/etianen --python "${PYTHON_VERSION}" "${DIR}"
echo "Finished building package"

# Create a source distribution.
echo "Started creating source distribution"
"${MINICONDA_DIR}/bin/python" setup.py sdist
echo "Finished creating source distribution"

# Deploys the package.
PACKAGE_FILENAME=`"${MINICONDA_DIR}/bin/conda" build --python "${PYTHON_VERSION}" ${DIR} --output`
if [ -f "${PACKAGE_FILENAME}" -a -n "${TRAVIS_TAG}" ]; then
    echo "Started uploading ${PACKAGE_NAME}"
    "${MINICONDA_DIR}/bin/anaconda" --token "${ANACONDA_TOKEN}" upload --force "${PACKAGE_FILENAME}" dist/*.tar.gz
    echo "Finished uploading ${PACKAGE_NAME}"
fi
