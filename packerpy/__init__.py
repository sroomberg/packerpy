"""PackerBuilder — Pythonic abstractions for HashiCorp Packer.

This package provides object-oriented models for programmatically
building Packer templates and executing Packer builds from Python.

Quick start::

    from packerpy import PackerBuilder, AmazonEbs, ShellProvisioner

    class MyBuilder(PackerBuilder):
        def configure(self):
            self.config.add_builder_source(AmazonEbs(...))
            self.config.builder.add_provisioner(ShellProvisioner(inline=["echo hello"]))

    MyBuilder("my-build").run()
"""

from packerpy.builder import PackerBuilder
from packerpy.client import PackerClient
from packerpy.exceptions import PackerBuildError, PackerClientError
from packerpy.models import (
    AmazonEbs,
    Builder,
    BuilderResource,
    BuilderSourceConfig,
    DockerBuilder,
    DockerImport,
    DockerPush,
    DockerTag,
    EmptyBuilderSourceConfig,
    EmptyPostProcessor,
    EmptyProvisioner,
    FileProvisioner,
    Manifest,
    PackerConfig,
    PackerResource,
    Plugin,
    PostProcessor,
    Provisioner,
    Requirements,
    ShellLocalProvisioner,
    ShellProvisioner,
    SupportingType,
)

__all__ = [
    "AmazonEbs",
    "Builder",
    "BuilderResource",
    "BuilderSourceConfig",
    "DockerBuilder",
    "DockerImport",
    "DockerPush",
    "DockerTag",
    "EmptyBuilderSourceConfig",
    "EmptyPostProcessor",
    "EmptyProvisioner",
    "FileProvisioner",
    "Manifest",
    "PackerBuildError",
    "PackerBuilder",
    "PackerClient",
    "PackerClientError",
    "PackerConfig",
    "PackerResource",
    "Plugin",
    "PostProcessor",
    "Provisioner",
    "Requirements",
    "ShellLocalProvisioner",
    "ShellProvisioner",
    "SupportingType",
]
