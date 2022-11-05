import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="packerpy",
    version="1.0.0",
    author="sroomberg",
    author_email="stevenroomberg@gmail.com",
    description="Packer for python",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/sroomberg/packerpy",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: Apache 2.0",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.8',
    packages=setuptools.find_packages(),
    install_requires=[
        'python-hcl2==3.0.5',
    ],
)