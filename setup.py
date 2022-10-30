import setuptools
import subprocess

from setuptools.command.develop import develop


class VerifyPackerInstallation(develop):
    def run(self):
        try:
            subprocess.check_call("packer version")
        except subprocess.CalledProcessError:
            raise EnvironmentError("Please install packer (https://developer.hashicorp.com/packer/downloads) before using this tool.")


with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="packerpy",
    version="0.0.1",
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
    packages=[
        "builder",
        "client",
        "examples",
        "exceptions",
        "models",
        "test",
        "util",
    ],
    install_requires=[
        'python-hcl2==3.0.5',
    ],
    cmdclass={
        "develop": VerifyPackerInstallation,
    }
)