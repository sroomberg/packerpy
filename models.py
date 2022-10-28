import hcl2
import json
import logging
import os
import re

from platform import machine

from .exceptions import PackerBuildError, raise_
from .util import *


class SupportingType:
    """
    Keep this class separate from PackerResource in case SupportingType objects need to be extended in a way that
    diverges from the pattern of PackerResource objects.
    """
    def is_empty(self) -> bool:
        raise NotImplementedError

    def json(self) -> dict:
        raise NotImplementedError


class PackerResource:
    def __init__(self, _type=None, name=None):
        self.type: str = _type
        self.name: str = name

    def __eq__(self, other):
        return self.json() == other.json()

    def json(self) -> dict:
        return self.__dict__

    def is_empty(self) -> bool:
        return not any((self.type, self.name))

    @staticmethod
    def check_exclusive_inputs(**inputs):
        count = 0
        for value in inputs.values():
            count += (1 if value else 0)
        if count != 1:
            raise ValueError(f"XOR: only 1 allowed {', '.join(inputs.keys())}")

    @staticmethod
    def check_inclusive_inputs(**inputs):
        if any(inputs.values()) and not all(inputs.values()):
            raise ValueError(f"All or none of the inputs allowed for {', '.join(inputs.keys())}")

    @staticmethod
    def all_defined_items(d: dict, *keys_to_remove) -> dict:
        def get_value(value):
            return value.json() if isinstance(value, SupportingType) else value

        def value_defined(value):
            return not value.is_empty() if isinstance(value, SupportingType) else value

        return {
            k: get_value(v)
            for k, v in d.items()
            if value_defined(v) and k not in keys_to_remove
        }

    @staticmethod
    def transform_type_key(data: dict):
        if "type" in data:
            data["_type"] = data.pop("type")


class Plugin(PackerResource):
    def __init__(self,
                 name,
                 version,
                 version_op,
                 source):
        super(Plugin, self).__init__(name=name)
        self.name: str = name
        self.version: str = version
        self.version_op: str = version_op
        self.source: str = source

    def json(self):
        return {
            self.name: {
                "version": f"{self.version_op} {self.version}",
                "source": self.source,
            }
        }

    def is_empty(self):
        return not all((self.name, self.version, self.version_op, self.source))

    @staticmethod
    def parse_plugin(content: dict):
        return Plugin.load_plugin(content.pop("name"), content)

    @classmethod
    def load_plugin(cls, plugin_name: str, content: dict):
        version_match = Requirements.version_match(content["version"])
        version_op = version_match.group(1)
        version = version_match.group(2)
        return cls(plugin_name, version, version_op, content["source"])


class Requirements(PackerResource):
    def __init__(self):
        super(Requirements, self).__init__()
        self.plugins: list[Plugin] = []
        self.version_constraint: str = ""

    def add_plugin(self, *plugins: Plugin):
        self.plugins.extend(plugins)

    def set_version_constraint(self, version_constraint):
        Requirements.version_match(version_constraint)
        self.version_constraint = version_constraint

    def is_empty(self):
        return not any((self.plugins, self.version_constraint))

    def json(self):
        if self.is_empty():
            return {}
        ret = {
            "packer": [
                {}
            ]
        }
        if self.version_constraint:
            ret["packer"][0]["required_version"] = self.version_constraint
        if self.plugins:
            ret["packer"][0]["required_plugins"] = [{}]
            for plugin in self.plugins:
                ret["packer"][0]["required_plugins"][0].update(plugin.json())
        return ret

    @staticmethod
    def version_match(version):
        match = re.match(r"([<>=]{1,2})\s*([\d.])*", version)
        if not match:
            raise PackerBuildError(f"Invalid version '{version}' - must match pattern " + r"([<>=]{1,2})\s*([\d.])*")
        return match

    @classmethod
    def load_requirements(cls, content: dict):
        requirements = cls()
        for item in content.get("packer", []):
            for plugins in item.get("required_plugins", []):
                for plugin_name, plugin_data in plugins.items():
                    requirements.add_plugin(Plugin.load_plugin(plugin_name, plugin_data))
            if "required_version" in item:
                requirements.set_version_constraint(item["required_version"])
        return requirements


class BuilderSourceConfig(PackerResource):
    def __init__(self, _type, name):
        super(BuilderSourceConfig, self).__init__(_type=_type, name=name)

    def __repr__(self):
        return f"{self.type}.{self.name}"

    def __str__(self):
        return f"source.{self.type}.{self.name}"

    def json(self):
        return {
            self.type: {
                self.name: PackerResource.all_defined_items(self.__dict__, "type", "name")
            }
        }

    def is_empty(self):
        return not any((self.type, self.name))

    @staticmethod
    def merge_builder_source_json(*builder_sources) -> dict:
        return {"source": [builder_source.json() for builder_source in builder_sources]}

    @classmethod
    def load_builder_source_config(cls, content: dict):
        if isinstance(cls, EmptyBuilderSourceConfig):
            return EmptyBuilderSourceConfig()
        if content:
            name, data = next(iter(content.items()))
            if name != "empty":
                PackerResource.transform_type_key(data)
                return cls(**dict(name=name, **data))
        return EmptyBuilderSourceConfig()


class EmptyBuilderSourceConfig(BuilderSourceConfig):
    def __init__(self, name="empty"):
        super(EmptyBuilderSourceConfig, self).__init__("empty", name)

    def __hash__(self):
        return id(self)

    def __eq__(self, other):
        return True

    def is_empty(self):
        return True


class AmazonEbs(BuilderSourceConfig):
    def __init__(self,
                 name,
                 ami_name,
                 region,
                 access_key,
                 secret_key,
                 **kwargs):
        super(AmazonEbs, self).__init__("amazon-ebs", name)
        self.ami_name: str = ami_name
        self.region: str = region
        self.access_key: str = access_key
        self.secret_key: str = secret_key
        self.token: str = kwargs.get("token", None)
        if self.token:
            PackerResource.check_inclusive_inputs(access_key=self.access_key,
                                                  secret_key=self.secret_key,
                                                  token=self.token)
        else:
            PackerResource.check_inclusive_inputs(access_key=self.access_key,
                                                  secret_key=self.secret_key)
        self.launch_block_device_mappings: AmazonEbs.LaunchBlockDeviceMappings = kwargs.get("launch_block_device_mappings", None)
        self.tags: dict = kwargs.get("tags", {})
        self.source_ami: str = kwargs.get("source_ami", None)
        self.source_ami_filter: AmazonEbs.SourceAmiFilter = kwargs.get("source_ami_filter", None)
        self.instance_type: str = kwargs.get("instance_type", None)
        self.ssh_username: str = kwargs.get("ssh_username", None)
        self.ssh_keypair_name: str = kwargs.get("ssh_keypair_name", None)
        self.ssh_private_key_file: str = kwargs.get("ssh_private_key_file", None)
        PackerResource.check_inclusive_inputs(ssh_keypair_name=self.ssh_keypair_name,
                                              ssh_private_key_file=self.ssh_private_key_file)
        self.availability_zone: str = kwargs.get("availability_zone", None)
        self.skip_credential_validation: bool = kwargs.get("skip_credential_validation", False)
        self.ami_users: list = kwargs.get("ami_users", [])
        self.ami_regions: list = kwargs.get("ami_regions", [])
        self.skip_region_validation: bool = kwargs.get("skip_region_validation", False)
        self.snapshot_volume: str = kwargs.get("snapshot_volume", None)
        self.snapshot_tags: dict = kwargs.get("snapshot_tags", {})
        self.snapshot_users: list = kwargs.get("snapshot_users", [])

    class LaunchBlockDeviceMappings(SupportingType):
        def __init__(self, **kwargs):
            self.delete_on_termination = kwargs.get("delete_on_termination", None)
            self.device_name = kwargs.get("device_name", None)
            self.encrypted = kwargs.get("encrypted", None)
            self.iops = kwargs.get("iops", None)
            self.no_device = kwargs.get("no_device", None)
            self.snapshot_id = kwargs.get("snapshot_id", None)
            self.throughput = kwargs.get("throughput", None)
            self.virtual_name = kwargs.get("virtual_name", None)
            self.volume_type = kwargs.get("volume_type", None)
            self.volume_size = kwargs.get("volume_size", None)
            self.kms_key_id = kwargs.get("kms_key_id", None)

        def is_empty(self):
            return not self.__dict__

        def json(self):
            return [PackerResource.all_defined_items(self.__dict__)]

    class SourceAmiFilter(SupportingType):
        def __init__(self, owners, filters, most_recent=False):
            self.owners = owners
            self.filters = filters
            self.most_recent = most_recent

        def is_empty(self):
            return not any(self.__dict__.values())

        def json(self):
            return PackerResource.all_defined_items(self.__dict__)


class DockerBuilder(BuilderSourceConfig):
    def __init__(self,
                 name,
                 image,
                 message="",
                 commit=None,
                 discard=None,
                 export_path=None,
                 **kwargs):
        super(DockerBuilder, self).__init__("docker", name)
        self.image: str = image
        self.message: str = message
        PackerResource.check_exclusive_inputs(commit=commit,
                                              discard=discard,
                                              export_path=export_path)
        self.commit: bool = commit
        self.discard: bool = discard
        self.export_path: str = export_path
        self.changes: list = kwargs.get("changes", [])
        self.platform: str = kwargs.get("platform", DockerBuilder.default_platform())
        DockerBuilder.set_local_build_vars(**kwargs.get("local_build_vars", {}))

    @staticmethod
    def default_platform():
        return "linux/amd64" if machine().endswith("arm64") else ""

    @staticmethod
    def set_local_build_vars(**flags):
        os.environ.update({k: str(v) for k, v in flags.items()})


BUILDER_SOURCE_CONFIG_LOOKUP = {
    "empty": EmptyBuilderSourceConfig,
    "amazon-ebs": AmazonEbs,
    "docker": DockerBuilder,
}


class BuilderResource(PackerResource):
    def __init__(self, _type):
        super(BuilderResource, self).__init__(_type=_type)

    def json(self):
        return PackerResource.all_defined_items(self.__dict__)

    def is_empty(self):
        return not PackerResource.all_defined_items(self.__dict__, "type")


class Provisioner(BuilderResource):
    def __init__(self, _type, **kwargs):
        super(Provisioner, self).__init__(_type)
        self.only: list = kwargs.get("only", [])

    def add_only_sources(self, *sources: BuilderSourceConfig):
        for source in sources:
            self.only.append(repr(source))

    @staticmethod
    def merge_provisioner_json(*provisioners) -> dict:
        return {
            "provisioner": [
                {provisioner.type: PackerResource.all_defined_items(provisioner.json(), "type")}
                for provisioner in provisioners
            ]
        }

    @classmethod
    def load_provisioner(cls, content: dict):
        PackerResource.transform_type_key(content)
        return cls(content)


class EmptyProvisioner(Provisioner):
    def __init__(self):
        super(EmptyProvisioner, self).__init__("empty")

    def __hash__(self):
        return id(self)

    def __eq__(self, other):
        return True


class ShellProvisioner(Provisioner):
    def __init__(self,
                 inline=None,
                 script=None,
                 scripts=None,
                 **kwargs):
        super(ShellProvisioner, self).__init__("shell", **kwargs)
        PackerResource.check_exclusive_inputs(inline=inline,
                                              script=script,
                                              scripts=scripts)
        self.inline: list = inline
        self.script: str = script
        self.scripts: list = scripts
        self.execute_command: str = kwargs.get("execute_command", None)
        self.env: dict = kwargs.get("env", {})
        self.environment_vars: list = kwargs.get("environment_vars", [])


class ShellLocalProvisioner(Provisioner):
    def __init__(self,
                 command=None,
                 inline=None,
                 script=None,
                 scripts=None,
                 **kwargs):
        super(ShellLocalProvisioner, self).__init__("shell-local", **kwargs)
        PackerResource.check_exclusive_inputs(command=command,
                                              inline=inline,
                                              script=script,
                                              scripts=scripts)
        self.command: str = command
        self.inline: list = inline
        self.script: str = next(ShellLocalProvisioner.set_scripts(script)) if script else None
        self.scripts: list = list(ShellLocalProvisioner.set_scripts(scripts)) if scripts else None
        self.env: dict = kwargs.get("env", {})
        self.environment_vars: list = kwargs.get("environment_vars", [])
        self.execute_command: str = kwargs.get("execute_command", None)

    @staticmethod
    def set_scripts(*scripts):
        for script in scripts:
            if os.path.exists(script):
                if os.path.isdir(script):
                    yield ShellLocalProvisioner.set_scripts(*os.listdir(script))
                elif os.path.isfile(script):
                    yield script
            else:
                raise FileExistsError(f"Invalid path {script}")


class FileProvisioner(Provisioner):
    def __init__(self,
                 content=None,
                 source=None,
                 destination=None,
                 **kwargs):
        super(FileProvisioner, self).__init__("file", **kwargs)
        self.content: str = content
        self.source: str = source
        self.destination: str = destination
        self.sources: list = kwargs.get("sources", [])
        PackerResource.check_exclusive_inputs(content=self.content,
                                              source=self.source,
                                              sources=self.sources)
        self.generated: bool = kwargs.get("generated", False)


PROVISIONER_LOOKUP = {
    "empty": EmptyProvisioner,
    "shell": ShellProvisioner,
    "shell-local": ShellLocalProvisioner,
    "file": FileProvisioner,
}


class PostProcessor(BuilderResource):
    def __init__(self, _type, **kwargs):
        super(PostProcessor, self).__init__(_type)
        self.only: list = kwargs.get("only", [])

    def add_only_sources(self, *sources: BuilderSourceConfig):
        for source in sources:
            self.only.append(repr(source))

    @staticmethod
    def merge_post_processor_json(*post_processors) -> dict:
        ret = {
            "post-processors": [
                {
                    "post-processor": {}
                }
            ]
        }
        for post_processor in post_processors:
            if post_processor.type not in ret["post-processors"][0]["post-processor"]:
                ret["post-processors"][0]["post-processor"][post_processor.type] = []
            ret["post-processors"][0]["post-processor"][post_processor.type].append(PackerResource.all_defined_items(post_processor.json(), "type"))
        return ret

    @classmethod
    def load_post_processor(cls, content: dict):
        PackerResource.transform_type_key(content)
        return cls(**content)


class EmptyPostProcessor(PostProcessor):
    def __init__(self):
        super(EmptyPostProcessor, self).__init__("empty")

    def __hash__(self):
        return id(self)

    def __eq__(self, other):
        return True


class Manifest(PostProcessor):
    def __init__(self, output):
        super(Manifest, self).__init__("manifest")
        self.output: str = output


class DockerImport(PostProcessor):
    def __init__(self, repository, **kwargs):
        super(DockerImport, self).__init__("docker-import", **kwargs)
        self.repository: str = repository
        self.tag: str = kwargs.get("tag", "latest")


class DockerTag(PostProcessor):
    def __init__(self, repository, **kwargs):
        super(DockerTag, self).__init__("docker-tag", **kwargs)
        self.repository: str = repository
        self.tags: list = parse_list(kwargs.get("tags", []))


class DockerPush(PostProcessor):
    def __init__(self, **kwargs):
        super(DockerPush, self).__init__("docker-push", **kwargs)
        self.ecr_login: bool = kwargs.get("ecr_login", None)
        self.login: bool = kwargs.get("login", None)
        PackerResource.check_exclusive_inputs(ecr_login=self.ecr_login,
                                              login=self.login)
        self.aws_access_key: str = kwargs.get("aws_access_key", None)
        self.aws_secret_key: str = kwargs.get("aws_secret_key", None)
        self.aws_token: str = kwargs.get("aws_token", None)
        PackerResource.check_inclusive_inputs(ecr_login=self.ecr_login,
                                              aws_access_key=self.aws_access_key,
                                              aws_secret_key=self.aws_secret_key,
                                              aws_token=self.aws_token)
        self.login_server: str = kwargs.get("login_server", None)
        self.login_username: str = kwargs.get("login_username", None)
        self.login_password: str = kwargs.get("login_password", None)
        PackerResource.check_inclusive_inputs(login=self.login,
                                              login_username=self.login_username,
                                              login_password=self.login_password)


POST_PROCESSOR_LOOKUP = {
    "empty": EmptyPostProcessor,
    "manifest": Manifest,
    "docker-import": DockerImport,
    "docker-tag": DockerTag,
    "docker-push": DockerPush,
}


class Builder(PackerResource):
    def __init__(self, name):
        super(Builder, self).__init__(name=name)
        self.sources: list[str] = []
        self.provisioners: list[Provisioner] = []
        self.post_processors: list[PostProcessor] = []

    def __eq__(self, other):
        return self.json() == other.json()

    def add_source(self, *builder_source_configs: BuilderSourceConfig):
        self.sources.extend([str(bsc) for bsc in builder_source_configs if str(bsc) not in self.sources])

    def add_provisioner(self, *provisioners: Provisioner):
        self.provisioners.extend(provisioners)

    def add_post_processor(self, *post_processors: PostProcessor):
        self.post_processors.extend(post_processors)

    def json(self):
        ret = {
            "build": [
                {
                    "name": self.name,
                    "sources": self.sources,
                }
            ]
        }
        if self.provisioners:
            ret["build"][0].update(Provisioner.merge_provisioner_json(*self.provisioners))
        if self.post_processors:
            ret["build"][0].update(PostProcessor.merge_post_processor_json(*self.post_processors))
        return ret

    def is_empty(self):
        return not any((self.sources, self.provisioners, self.post_processors))

    def get_only_source(self, source_name):
        return list(filter(lambda source_str: source_name in source_str, self.sources))

    @classmethod
    def load_builder(cls, content: dict, name: str = None):
        try:
            builder_data = content.get("build", [])[0]
            builder = cls(builder_data["name"])
        except (KeyError, IndexError):
            if name:
                builder = cls(name)
            else:
                raise PackerBuildError("No build block found in content and no name specified for empty builder.")
        except TypeError:
            raise PackerBuildError("Invalid packer config file.")
        else:
            builder.sources = builder_data.get("sources", [])
            builder.add_provisioner(*(PROVISIONER_LOOKUP[provisioner_type].load_provisioner(provisioner_data)
                                      for provisioner in builder_data.get("provisioner", [])
                                      for provisioner_type, provisioner_data in provisioner.items()))
            for post_processor_list_item in builder_data.get("post-processors", []):
                for post_processor_type, post_processor_data_list in post_processor_list_item.get("post-processor", {}).items():
                    builder.add_post_processor(POST_PROCESSOR_LOOKUP[post_processor_type].load_post_processor(next(iter(post_processor_data_list))))
        return builder


class PackerConfig:
    def __init__(self, config_name, log=None):
        self.config_name: str = config_name
        self.builder: Builder = Builder(self.config_name)
        self.requirements: Requirements = Requirements()
        self.builder_sources: dict[str, BuilderSourceConfig] = {}
        self.log = log or logging.getLogger(PackerConfig.__name__)

    def __str__(self):
        return self.config_name

    def __eq__(self, other):
        try:
            return all((self.config_name == other.config_name,
                        self.builder == other.builder,
                        self.requirements == other.requirements,
                        set(self.builder_sources.keys()) == set(other.builder_sources.keys()),
                        all((self.builder_sources[k] == other.builder_sources[k] for k in self.builder_sources.keys()))))
        except KeyError:
            return False

    def set_requirements(self, requirements: Requirements):
        self.requirements = requirements

    def add_builder_source(self, *builder_sources: BuilderSourceConfig):
        self.builder_sources.update({builder_source.name: builder_source for builder_source in builder_sources})
        self.builder.add_source(*builder_sources)

    def json(self):
        ret = {}
        ret.update(self.requirements.json())
        ret.update(BuilderSourceConfig.merge_builder_source_json(*self.builder_sources.values()))
        ret.update(self.builder.json())
        return ret

    def is_empty(self):
        return not any((not self.requirements.is_empty(),
                        not self.builder.is_empty(),
                        not any((builder_source.is_empty() for builder_source in self.builder_sources.values()))))

    @classmethod
    def load_config(cls, config_name, config_path=None, config_content=None, config_type=None):
        file_loader = {
            "json": json.load,
            "hcl": hcl2.load,
        }
        content_loader = {
            "json": json.loads,
            "hcl": hcl2.loads,
        }
        config = cls(config_name)
        if config_path:
            if os.path.exists(config_path) and os.path.isfile(config_path):
                with open(config_path, "r") as fp:
                    file_type = config_path.rsplit(".", 1)[-1]
                    data = file_loader.get(
                        file_type,
                        lambda: raise_(ValueError(f"Unsupported file type {file_type}. Supported Types: {', '.join(file_loader.keys())}"))
                    )(fp)
            else:
                data = {}
        elif config_content and isinstance(config_content, dict):
            data = config_content
        elif config_content and isinstance(config_content, str) and config_type:
            data = content_loader.get(
                config_type,
                lambda: raise_(ValueError(f"Unsupported file type {config_type}. Supported Types: {', '.join(content_loader.keys())}"))
            )(config_content)
        else:
            raise ValueError("Expected one of the following combinations of input vars: [config_path|config_content (type: dict)|config_content (type: str) and config_type]")
        config.set_requirements(Requirements.load_requirements(data))
        config.builder = Builder.load_builder(data, name=config_name)
        [[config.add_builder_source(BUILDER_SOURCE_CONFIG_LOOKUP[_type].load_builder_source_config(source[_type]))
          for _type in source.keys()] for source in data.get("source", [])]
        return config


