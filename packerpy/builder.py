"""High-level Packer build orchestrator."""

from __future__ import annotations

import json
import logging
import os

from .client import PackerClient
from .exceptions import PackerBuildError
from .models import Manifest, PackerConfig


class PackerBuilder:
    """Abstract base class for building Packer images.

    Subclass ``PackerBuilder`` and implement :meth:`configure` to define
    your builder sources, provisioners, and post-processors.  Then call
    :meth:`run` to generate and execute the Packer template.

    Example::

        class AmiBuilder(PackerBuilder):
            def configure(self):
                self.config.add_builder_source(AmazonEbs(...))
                self.config.builder.add_provisioner(ShellProvisioner(...))

        AmiBuilder("my-ami").run()

    Args:
        name: A human-readable name for this build.
        config_file: Path where the generated ``.pkr.json`` template is written.
        manifest_file: Path where the Packer manifest post-processor writes output.
    """

    def __init__(
        self,
        name: str,
        config_file: str = "packer-builder.pkr.json",
        manifest_file: str = "packer-manifest.json",
    ) -> None:
        self.log: logging.Logger = logging.getLogger(PackerBuilder.__name__)
        self.config: PackerConfig = PackerConfig(name, self.log)
        self.config_file: str = config_file
        self.manifest_file: str = manifest_file
        self.client: PackerClient = PackerClient(self.config_file, log=self.log)

    def artifact_exists(self) -> bool:
        """Check whether the manifest file contains a valid artifact ID."""
        if os.path.exists(self.manifest_file):
            with open(self.manifest_file, "r") as fp:
                manifest = json.load(fp)
            return manifest["builds"][0].get("artifact_id", None) is not None
        return False

    def add_manifest_post_processor(self) -> str:
        """Ensure a :class:`Manifest` post-processor is present in the build.

        Returns:
            The path to the manifest output file.
        """
        for post_processor in self.config.builder.post_processors:
            if isinstance(post_processor, Manifest):
                return post_processor.output
        self.config.builder.add_post_processor(Manifest(self.manifest_file))
        return self.manifest_file

    def configure(self) -> None:
        """Define the Packer build configuration.

        Subclasses **must** override this method to add builder sources,
        provisioners, and post-processors to ``self.config``.
        """
        raise NotImplementedError

    def build(self) -> None:
        """Run the full Packer lifecycle: init, validate, and build.

        Raises:
            PackerBuildError: If validation fails or no artifact is produced.
        """
        self.add_manifest_post_processor()
        if self.client.run("init").returncode != 0:
            raise PackerBuildError("Packer init failed")
        if self.client.run("validate").returncode != 0:
            raise PackerBuildError("Invalid packer template")
        if self.client.run("build").returncode != 0:
            raise PackerBuildError("Packer build failed")
        self.log.info(f"Checking manifest {self.manifest_file} for created artifact(s)")
        if not self.artifact_exists():
            raise PackerBuildError(
                f"Artifact does not exist. Validate file {self.config_file} and rerun with debug for more details."
            )

    def run(self) -> None:
        """Configure and execute the build."""
        self.configure()
        self.build()
