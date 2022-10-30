import os

from ..builder import PackerBuilder
from ..models import *


class AmiBuilder(PackerBuilder):
    def __init__(self):
        super(AmiBuilder, self).__init__("packer-ami")

    def configure(self):
        builder_source_config = AmazonEbs(
            name="packer-ami",
            ami_name="custom-image",
            region="us-east-1",
            access_key=os.environ.get("AWS_ACCESS_KEY_ID"),
            secret_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
            source_ami=os.environ.get("SOURCE_AMI"),
            launch_block_device_mappings=AmazonEbs.LaunchBlockDeviceMappings(
                delete_on_termination=False,
            )
        )
        self.config.add_builder_source(builder_source_config)
        self.config.builder.add_provisioner(FileProvisioner( # REPLACEME
            source="boot.sh",
            destination="/opt/boot.sh"
        ))
        self.config.builder.add_provisioner(ShellProvisioner(
            inline=["chmod", "+X", "/opt/boot.sh"]
        ))



