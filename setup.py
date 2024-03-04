# -*- coding: utf-8 -*-

from setuptools import setup
import pathlib


here = pathlib.Path(__file__).parent.resolve()
long_description = (here / "README.md").read_text(encoding="utf-8")

with open("requirements.txt") as f:
    required = f.read().splitlines()

setup(
    name="sworkflow",
    version="0.0.1",
    description="workflow for job dependency with slurm",
    long_description=long_description,
    long_description_content_type="text/markdown",
    # python_requires=">=3.9",
    package_dir={"": "."},
    packages=[
        "sworkflow",
    ],
    install_requires=required,
    entry_points="""
        [console_scripts]
        sworkflow=sworkflow:cli
    """,
    classifiers=[
        "Development Status :: 0.0.1",
        "Intended Audience :: Developers",
        "Intended Audience :: Information Technology",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
    author="Pavan Siligam",
    author_email="pavan.siligam@gmail.com",
    license="MIT",
    url="https://github.com/siligam/sworkflow",
)
