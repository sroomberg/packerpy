import logging

from .client import *
from .models import *


class PackerBuilder:
    def __init__(self, name, config_file="packer-builder.pkr.json"):
        self.log: logging.Logger = logging.getLogger(PackerBuilder.__name__)
        self.config: PackerConfig = PackerConfig(name, self.log)
        self.config_file: str = config_file
        self.client: PackerClient = PackerClient(self.config_file, log=self.log)

    def build(self):
        pass
