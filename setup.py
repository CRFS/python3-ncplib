from setuptools import setup, find_packages


setup(
    name="ncplib",
    version="4.0.0",
    license="BSD",
    description="CRFS NCP library for Python 3.",
    author="Dave Hall",
    author_email="dhall@crfs.com",
    url="https://github.com/CRFS/python3-ncplib",
    packages=find_packages(exclude=["tests", "examples"]),
    package_data={"ncplib": ["py.typed"]},
    install_requires=[
        "async_timeout>=3.0,<4.0",
    ],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Web Environment",
        "Intended Audience :: Developers",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
    ],
)
