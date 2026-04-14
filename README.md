# packerpy

Pythonic abstractions for [HashiCorp Packer](https://www.packer.io/). Build, configure, and execute Packer templates entirely from Python code — no hand-written JSON or HCL required.

## Requirements

- Python >= 3.10
- [Packer CLI](https://developer.hashicorp.com/packer/downloads)

## Installation

```bash
pip install PackerBuilder
```

[PyPI](https://pypi.org/project/PackerBuilder/)

## Quick Start

```python
import os
from packerpy import PackerBuilder, AmazonEbs, ShellProvisioner

class AmiBuilder(PackerBuilder):
    def configure(self):
        source = AmazonEbs(
            name="my-ami",
            ami_name="custom-image",
            region="us-east-1",
            access_key=os.environ["AWS_ACCESS_KEY_ID"],
            secret_key=os.environ["AWS_SECRET_ACCESS_KEY"],
            source_ami=os.environ["SOURCE_AMI"],
            instance_type="t3.micro",
            ssh_username="ec2-user",
        )
        self.config.add_builder_source(source)
        self.config.builder.add_provisioner(
            ShellProvisioner(inline=["echo 'Hello from Packer!'"])
        )

AmiBuilder("my-ami").run()
```

## Usage

### Core Classes

| Class | Description |
|-------|-------------|
| [`PackerBuilder`](packerpy/builder.py) | Abstract base class — subclass and implement `configure()` to define your build |
| [`PackerClient`](packerpy/client.py) | Thin wrapper around the Packer CLI (`init`, `validate`, `build`, etc.) |
| [`PackerConfig`](packerpy/models.py) | Top-level config that serializes to a `.pkr.json` template |

### Builder Sources

Builder sources define *what* to build. Each maps to a Packer builder plugin.

| Class | Packer Type | Description |
|-------|-------------|-------------|
| `AmazonEbs` | `amazon-ebs` | Build EBS-backed Amazon AMIs |
| `DockerBuilder` | `docker` | Build Docker images |

```python
from packerpy import AmazonEbs

source = AmazonEbs(
    name="web-server",
    ami_name="web-server-{{timestamp}}",
    region="us-east-1",
    access_key="AKIA...",
    secret_key="...",
    instance_type="t3.micro",
    source_ami="ami-0abcdef1234567890",
    ssh_username="ec2-user",
    launch_block_device_mappings=AmazonEbs.LaunchBlockDeviceMappings(
        volume_type="gp3",
        volume_size=20,
        delete_on_termination=True,
    ),
)
```

### Provisioners

Provisioners define *how* to configure the build instance.

| Class | Packer Type | Description |
|-------|-------------|-------------|
| `ShellProvisioner` | `shell` | Run shell commands on the build instance |
| `ShellLocalProvisioner` | `shell-local` | Run shell commands on the machine running Packer |
| `FileProvisioner` | `file` | Upload files to the build instance |

```python
from packerpy import ShellProvisioner, FileProvisioner

# Run inline commands
shell = ShellProvisioner(inline=["apt-get update", "apt-get install -y nginx"])

# Upload a file then run it
upload = FileProvisioner(source="setup.sh", destination="/tmp/setup.sh")
run = ShellProvisioner(inline=["chmod +x /tmp/setup.sh", "/tmp/setup.sh"])
```

### Post-Processors

Post-processors run after a successful build.

| Class | Packer Type | Description |
|-------|-------------|-------------|
| `Manifest` | `manifest` | Write build artifact metadata to a JSON file |
| `DockerImport` | `docker-import` | Import a Docker container as an image |
| `DockerTag` | `docker-tag` | Tag a Docker image |
| `DockerPush` | `docker-push` | Push a Docker image to a registry |

### Loading Existing Configs

Load a Packer config from a JSON file, HCL file, dict, or raw string:

```python
from packerpy import PackerConfig

# From a file
config = PackerConfig.load_config("my-build", config_path="packer.pkr.json")

# From a dict
config = PackerConfig.load_config("my-build", config_content={...})

# From a raw HCL string
config = PackerConfig.load_config("my-build", config_content=hcl_str, config_type="hcl")
```

### Requirements & Plugins

Declare required Packer versions and plugins:

```python
from packerpy import PackerConfig, Requirements, Plugin

config = PackerConfig("my-build")
config.requirements.set_version_constraint(">=1.7.0")
config.requirements.add_plugin(
    Plugin("amazon", "1.2.0", ">=", "github.com/hashicorp/amazon")
)
```

### Restricting to Specific Sources

Provisioners and post-processors can be restricted to run only for specific sources:

```python
provisioner = ShellProvisioner(inline=["echo 'only on this source'"])
provisioner.add_only_sources(source)
```

## Architecture

```
PackerConfig
├── Requirements
│   ├── version_constraint
│   └── plugins: [Plugin, ...]
├── builder_sources: {name: BuilderSourceConfig, ...}
│   ├── AmazonEbs
│   ├── DockerBuilder
│   └── ...
└── Builder
    ├── sources: [str, ...]
    ├── provisioners: [Provisioner, ...]
    │   ├── ShellProvisioner
    │   ├── ShellLocalProvisioner
    │   └── FileProvisioner
    └── post_processors: [PostProcessor, ...]
        ├── Manifest
        ├── DockerImport
        ├── DockerTag
        └── DockerPush
```

## License

BSD 3-Clause License
