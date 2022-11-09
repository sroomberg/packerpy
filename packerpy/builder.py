import logging

from .client import *
from .models import *


class PackerBuilder:
    def __init__(self, name, config_file="packer-builder.pkr.json", manifest_file="packer-manifest.json"):
        self.log: logging.Logger = logging.getLogger(PackerBuilder.__name__)
        self.config: PackerConfig = PackerConfig(name, self.log)
        self.config_file: str = config_file
        self.manifest_file: str = manifest_file
        self.client: PackerClient = PackerClient(self.config_file, log=self.log)

    def artifact_exists(self):
        if os.path.exists(self.manifest_file):
            with open(self.manifest_file, "r") as fp:
                manifest = json.load(fp)
            return manifest["builds"][0].get("artifact_id", None) is not None
        return False

    def add_manifest_post_processor(self):
        for post_processor in self.config.builder.post_processors:
            if isinstance(post_processor, Manifest):
                return post_processor.output
        self.config.builder.add_post_processor(Manifest(self.manifest_file))
        return self.manifest_file

    def configure(self):
        raise NotImplementedError

    def build(self):
        self.add_manifest_post_processor()
        self.client.run("init")
        if self.client.run("validate").returncode != 0:
            raise PackerBuildError("Invalid packer template")
        self.client.run("build")
        self.log.info(f"Checking manifest {self.manifest_file} for created artifact(s)")
        if not self.artifact_exists():
            raise PackerBuildError(f"Artifact does not exist. Validate file {self.config_file} and rerun with debug for more details.")

    def run(self):
        self.configure()
        self.build()

