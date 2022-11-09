import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="PackerBuilder",
    version="1.0.3",
    author="sroomberg",
    author_email="stevenroomberg@gmail.com",
    description="Packer for python",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/sroomberg/packerpy",
    license="BSD 3-Clause License",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.8',
    packages=setuptools.find_packages(),
    install_requires=[
        'python-hcl2==3.0.5',
    ],
    test_suite="tests",
)