"""Packer configuration models.

This module contains object-oriented representations of Packer template
blocks.  Each class maps to a section of a ``.pkr.json`` configuration
file and can serialize itself to the JSON structure that Packer expects.
"""

from __future__ import annotations

import json
import logging
import os
import re
from platform import machine
from typing import Any

import hcl2
from typing_extensions import override

from .exceptions import PackerBuildError, raise_
from .util import parse_list

# ---------------------------------------------------------------------------
# Base classes
# ---------------------------------------------------------------------------


class SupportingType:
    """Base class for nested configuration objects (e.g. block device mappings)."""

    def is_empty(self) -> bool:
        """Return ``True`` if this object carries no meaningful configuration."""
        raise NotImplementedError

    def json(self) -> dict[str, Any] | list[Any]:
        """Return the Packer JSON representation of this object."""
        raise NotImplementedError


class PackerResource:
    """Base class for all top-level Packer resources.

    Provides common helpers for JSON serialization, input validation,
    and equality comparison.

    Args:
        _type: The Packer resource type identifier.
        name: The user-defined name for this resource.
    """

    def __init__(self, _type: str | None = None, name: str | None = None) -> None:
        self.type: str | None = _type
        self.name: str | None = name

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PackerResource):
            return NotImplemented
        return self.json() == other.json()

    def json(self) -> dict[str, Any]:
        """Return the Packer JSON representation of this resource."""
        return self.__dict__

    def is_empty(self) -> bool:
        """Return ``True`` if both *type* and *name* are unset."""
        return not any((self.type, self.name))

    @staticmethod
    def check_exclusive_inputs(**inputs: Any) -> None:
        """Validate that exactly one of the given inputs is truthy (XOR).

        Raises:
            ValueError: If zero or more than one input is truthy.
        """
        count = 0
        for value in inputs.values():
            count += 1 if value else 0
        if count != 1:
            raise ValueError(f"XOR: only 1 allowed {', '.join(inputs.keys())}")

    @staticmethod
    def check_inclusive_inputs(**inputs: Any) -> None:
        """Validate that all inputs are provided together or none at all.

        Raises:
            ValueError: If some but not all inputs are truthy.
        """
        if any(inputs.values()) and not all(inputs.values()):
            raise ValueError(f"All or none of the inputs allowed for {', '.join(inputs.keys())}")

    @staticmethod
    def all_defined_items(d: dict[str, Any], *keys_to_remove: str) -> dict[str, Any]:
        """Filter a dict to only entries with truthy values.

        :class:`SupportingType` values are serialized via their ``json()``
        method and filtered via ``is_empty()``.

        Args:
            d: The dictionary to filter.
            *keys_to_remove: Keys to exclude regardless of value.
        """

        def get_value(value: Any) -> Any:
            return value.json() if isinstance(value, SupportingType) else value

        def value_defined(value: Any) -> bool:
            return not value.is_empty() if isinstance(value, SupportingType) else value

        return {k: get_value(v) for k, v in d.items() if value_defined(v) and k not in keys_to_remove}

    @staticmethod
    def transform_type_key(data: dict[str, Any]) -> None:
        """Rename ``"type"`` to ``"_type"`` in *data* to avoid clashing with the constructor parameter."""
        if "type" in data:
            data["_type"] = data.pop("type")


# ---------------------------------------------------------------------------
# Requirements & plugins
# ---------------------------------------------------------------------------


class Plugin(PackerResource):
    """A required Packer plugin declaration.

    See: https://developer.hashicorp.com/packer/docs/templates/hcl_templates/blocks/packer

    Args:
        name: Plugin name (e.g. ``"amazon"``).
        version: Semver version string (e.g. ``"1.2.0"``).
        version_op: Version comparison operator (e.g. ``">="``, ``"="``).
        source: Plugin source URL (e.g. ``"github.com/hashicorp/amazon"``).
    """

    def __init__(self, name: str, version: str, version_op: str, source: str) -> None:
        super().__init__(name=name)
        self.version: str = version
        self.version_op: str = version_op
        self.source: str = source

    @override
    def json(self) -> dict[str, Any]:
        return {
            self.name: {
                "version": f"{self.version_op} {self.version}",
                "source": self.source,
            }
        }

    @override
    def is_empty(self) -> bool:
        return not all((self.name, self.version, self.version_op, self.source))

    @staticmethod
    def parse_plugin(content: dict[str, Any]) -> Plugin:
        """Parse a plugin from a dict that contains a ``"name"`` key."""
        return Plugin.load_plugin(content.pop("name"), content)

    @classmethod
    def load_plugin(cls, plugin_name: str, content: dict[str, Any]) -> Plugin:
        """Construct a :class:`Plugin` from a raw JSON/HCL plugin block."""
        version_match = Requirements.version_match(content["version"])
        version_op = version_match.group(1)
        version = version_match.group(2)
        return cls(plugin_name, version, version_op, content["source"])


class Requirements(PackerResource):
    """Packer version and plugin requirements.

    See: https://developer.hashicorp.com/packer/docs/templates/hcl_templates/blocks/packer
    """

    def __init__(self) -> None:
        super().__init__()
        self.plugins: list[Plugin] = []
        self.version_constraint: str = ""

    def add_plugin(self, *plugins: Plugin) -> None:
        """Register one or more required plugins."""
        self.plugins.extend(plugins)

    def set_version_constraint(self, version_constraint: str) -> None:
        """Set the required Packer version constraint (e.g. ``">=1.7.0"``)."""
        Requirements.version_match(version_constraint)
        self.version_constraint = version_constraint

    @override
    def is_empty(self) -> bool:
        return not any((self.plugins, self.version_constraint))

    @override
    def json(self) -> dict[str, Any]:
        if self.is_empty():
            return {}
        ret: dict[str, Any] = {"packer": [{}]}
        if self.version_constraint:
            ret["packer"][0]["required_version"] = self.version_constraint
        if self.plugins:
            ret["packer"][0]["required_plugins"] = [{}]
            for plugin in self.plugins:
                ret["packer"][0]["required_plugins"][0].update(plugin.json())
        return ret

    @staticmethod
    def version_match(version: str) -> re.Match[str]:
        """Validate and parse a version constraint string.

        Args:
            version: A string like ``">= 1.0.1"`` or ``"=1.2.3"``.

        Returns:
            A regex match with group(1) as the operator and group(2) as the version.

        Raises:
            PackerBuildError: If the version string doesn't match the expected pattern.
        """
        match = re.match(r"([<>=]{1,2})\s*([\d.]*)", version)
        if not match:
            raise PackerBuildError(f"Invalid version '{version}' - must match pattern " + r"([<>=]{1,2})\s*([\d.])*")
        return match

    @classmethod
    def load_requirements(cls, content: dict[str, Any]) -> Requirements:
        """Load requirements from a parsed Packer config dict."""
        requirements = cls()
        for item in content.get("packer", []):
            for plugins in item.get("required_plugins", []):
                for plugin_name, plugin_data in plugins.items():
                    requirements.add_plugin(Plugin.load_plugin(plugin_name, plugin_data))
            if "required_version" in item:
                requirements.set_version_constraint(item["required_version"])
        return requirements


# ---------------------------------------------------------------------------
# Builder source configurations
# ---------------------------------------------------------------------------


class BuilderSourceConfig(PackerResource):
    """A Packer builder source block.

    See: https://developer.hashicorp.com/packer/docs/templates/hcl_templates/blocks/build/source

    Args:
        _type: The builder type (e.g. ``"amazon-ebs"``, ``"docker"``).
        name: A unique name for this source within the template.
    """

    def __init__(self, _type: str, name: str) -> None:
        super().__init__(_type=_type, name=name)

    def __repr__(self) -> str:
        return f"{self.type}.{self.name}"

    def __str__(self) -> str:
        return f"source.{self.type}.{self.name}"

    @override
    def json(self) -> dict[str, Any]:
        return {self.type: {self.name: PackerResource.all_defined_items(self.__dict__, "type", "name")}}

    @override
    def is_empty(self) -> bool:
        return not any((self.type, self.name))

    @staticmethod
    def merge_builder_source_json(*builder_sources: BuilderSourceConfig) -> dict[str, Any]:
        """Merge multiple builder sources into a single ``"source"`` block."""
        return {"source": [builder_source.json() for builder_source in builder_sources]}

    @classmethod
    def load_builder_source_config(cls, content: dict[str, Any]) -> BuilderSourceConfig:
        """Construct a :class:`BuilderSourceConfig` from a raw JSON/HCL source block."""
        if isinstance(cls, EmptyBuilderSourceConfig):
            return EmptyBuilderSourceConfig()
        if content:
            name, data = next(iter(content.items()))
            if name != "empty":
                PackerResource.transform_type_key(data)
                return cls(**dict(name=name, **data))
        return EmptyBuilderSourceConfig()


class EmptyBuilderSourceConfig(BuilderSourceConfig):
    """Placeholder source used when loading configs with no real source defined."""

    def __init__(self, name: str = "empty") -> None:
        super().__init__("empty", name)

    def __hash__(self) -> int:
        return id(self)

    @override
    def __eq__(self, other: object) -> bool:
        return True

    @override
    def is_empty(self) -> bool:
        return True


class AmazonEbs(BuilderSourceConfig):
    """Amazon EBS-backed AMI builder source.

    See: https://developer.hashicorp.com/packer/plugins/builders/amazon/ebs

    Args:
        name: Unique source name.
        ami_name: Name for the output AMI.
        region: AWS region to build in.
        access_key: AWS access key ID.
        secret_key: AWS secret access key.
        **kwargs: Optional parameters — see Packer docs for the full list.
    """

    def __init__(
        self,
        name: str,
        ami_name: str,
        region: str,
        access_key: str,
        secret_key: str,
        **kwargs: Any,
    ) -> None:
        super().__init__("amazon-ebs", name)
        self.ami_name: str = ami_name
        self.region: str = region
        self.access_key: str = access_key
        self.secret_key: str = secret_key
        self.token: str | None = kwargs.get("token", None)
        if self.token:
            PackerResource.check_inclusive_inputs(
                access_key=self.access_key, secret_key=self.secret_key, token=self.token
            )
        else:
            PackerResource.check_inclusive_inputs(access_key=self.access_key, secret_key=self.secret_key)
        self.launch_block_device_mappings: AmazonEbs.LaunchBlockDeviceMappings | None = kwargs.get(
            "launch_block_device_mappings", None
        )
        self.tags: dict[str, str] = kwargs.get("tags", {})
        self.source_ami: str | None = kwargs.get("source_ami", None)
        self.source_ami_filter: AmazonEbs.SourceAmiFilter | None = kwargs.get("source_ami_filter", None)
        self.instance_type: str | None = kwargs.get("instance_type", None)
        self.ssh_username: str | None = kwargs.get("ssh_username", None)
        self.ssh_keypair_name: str | None = kwargs.get("ssh_keypair_name", None)
        self.ssh_private_key_file: str | None = kwargs.get("ssh_private_key_file", None)
        PackerResource.check_inclusive_inputs(
            ssh_keypair_name=self.ssh_keypair_name, ssh_private_key_file=self.ssh_private_key_file
        )
        self.availability_zone: str | None = kwargs.get("availability_zone", None)
        self.skip_credential_validation: bool = kwargs.get("skip_credential_validation", False)
        self.ami_users: list[str] = kwargs.get("ami_users", [])
        self.ami_regions: list[str] = kwargs.get("ami_regions", [])
        self.skip_region_validation: bool = kwargs.get("skip_region_validation", False)
        self.snapshot_volume: str | None = kwargs.get("snapshot_volume", None)
        self.snapshot_tags: dict[str, str] = kwargs.get("snapshot_tags", {})
        self.snapshot_users: list[str] = kwargs.get("snapshot_users", [])

    class LaunchBlockDeviceMappings(SupportingType):
        """EBS volume configuration for the launch instance.

        All parameters are optional and map directly to the Packer
        ``launch_block_device_mappings`` block.
        """

        def __init__(self, **kwargs: Any) -> None:
            self.delete_on_termination: bool | None = kwargs.get("delete_on_termination", None)
            self.device_name: str | None = kwargs.get("device_name", None)
            self.encrypted: bool | None = kwargs.get("encrypted", None)
            self.iops: int | None = kwargs.get("iops", None)
            self.no_device: bool | None = kwargs.get("no_device", None)
            self.snapshot_id: str | None = kwargs.get("snapshot_id", None)
            self.throughput: int | None = kwargs.get("throughput", None)
            self.virtual_name: str | None = kwargs.get("virtual_name", None)
            self.volume_type: str | None = kwargs.get("volume_type", None)
            self.volume_size: int | None = kwargs.get("volume_size", None)
            self.kms_key_id: str | None = kwargs.get("kms_key_id", None)

        @override
        def is_empty(self) -> bool:
            return not self.__dict__

        @override
        def json(self) -> list[dict[str, Any]]:
            return [PackerResource.all_defined_items(self.__dict__)]

    class SourceAmiFilter(SupportingType):
        """Filter to find the source AMI dynamically.

        Args:
            owners: List of AWS account IDs or aliases that own the AMI.
            filters: Dict of AMI filter key-value pairs.
            most_recent: If ``True``, select the most recently created matching AMI.
        """

        def __init__(
            self,
            owners: list[str],
            filters: dict[str, str],
            most_recent: bool = False,
        ) -> None:
            self.owners: list[str] = owners
            self.filters: dict[str, str] = filters
            self.most_recent: bool = most_recent

        @override
        def is_empty(self) -> bool:
            return not any(self.__dict__.values())

        @override
        def json(self) -> dict[str, Any]:
            return PackerResource.all_defined_items(self.__dict__)


class GoogleComputeBuilder(BuilderSourceConfig):
    """Google Compute Engine image builder source.

    See: https://developer.hashicorp.com/packer/plugins/builders/googlecompute

    Exactly one of *source_image* or *source_image_family* must be provided.

    Args:
        name: Unique source name.
        project_id: GCP project ID to build in.
        zone: GCP zone to run the build instance in (e.g. ``"us-central1-a"``).
        source_image: Exact source image name to use as the base.
        source_image_family: Image family to resolve to the latest non-deprecated image.
        **kwargs: Optional parameters — see Packer docs for the full list.
    """

    def __init__(
        self,
        name: str,
        project_id: str,
        zone: str,
        source_image: str | None = None,
        source_image_family: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__("googlecompute", name)
        PackerResource.check_exclusive_inputs(source_image=source_image, source_image_family=source_image_family)
        self.project_id: str = project_id
        self.zone: str = zone
        self.source_image: str | None = source_image
        self.source_image_family: str | None = source_image_family
        self.image_name: str | None = kwargs.get("image_name", None)
        self.image_family: str | None = kwargs.get("image_family", None)
        self.image_description: str | None = kwargs.get("image_description", None)
        self.image_labels: dict[str, str] = kwargs.get("image_labels", {})
        self.machine_type: str | None = kwargs.get("machine_type", None)
        self.disk_size: int | None = kwargs.get("disk_size", None)
        self.disk_type: str | None = kwargs.get("disk_type", None)
        self.network: str | None = kwargs.get("network", None)
        self.subnetwork: str | None = kwargs.get("subnetwork", None)
        self.tags: list[str] = kwargs.get("tags", [])
        self.ssh_username: str | None = kwargs.get("ssh_username", None)
        self.service_account_email: str | None = kwargs.get("service_account_email", None)
        self.scopes: list[str] = kwargs.get("scopes", [])
        self.credentials_file: str | None = kwargs.get("credentials_file", None)
        self.access_token: str | None = kwargs.get("access_token", None)
        if self.credentials_file and self.access_token:
            raise ValueError("Provide at most one of credentials_file or access_token")
        self.metadata: dict[str, str] = kwargs.get("metadata", {})
        self.startup_script_file: str | None = kwargs.get("startup_script_file", None)
        self.preemptible: bool = kwargs.get("preemptible", False)
        self.omit_external_ip: bool = kwargs.get("omit_external_ip", False)
        self.on_host_maintenance: str | None = kwargs.get("on_host_maintenance", None)
        self.use_iap: bool = kwargs.get("use_iap", False)
        self.use_os_login: bool = kwargs.get("use_os_login", False)


class DockerBuilder(BuilderSourceConfig):
    """Docker image builder source.

    See: https://developer.hashicorp.com/packer/plugins/builders/docker

    Exactly one of *commit*, *discard*, or *export_path* must be provided.

    Args:
        name: Unique source name.
        image: Base Docker image to build from.
        message: Commit message when using ``commit=True``.
        commit: If ``True``, commit the container to an image.
        discard: If ``True``, discard the container after provisioning.
        export_path: Path to export the container filesystem as a tarball.
        **kwargs: Optional parameters including ``changes``, ``platform``,
            and ``local_build_vars``.
    """

    def __init__(
        self,
        name: str,
        image: str,
        message: str = "",
        commit: bool | None = None,
        discard: bool | None = None,
        export_path: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__("docker", name)
        self.image: str = image
        self.message: str = message
        PackerResource.check_exclusive_inputs(commit=commit, discard=discard, export_path=export_path)
        self.commit: bool | None = commit
        self.discard: bool | None = discard
        self.export_path: str | None = export_path
        self.changes: list[str] = kwargs.get("changes", [])
        self.platform: str = kwargs.get("platform", DockerBuilder.default_platform())
        DockerBuilder.set_local_build_vars(**kwargs.get("local_build_vars", {}))

    @staticmethod
    def default_platform() -> str:
        """Return ``"linux/amd64"`` on ARM64 hosts, empty string otherwise."""
        return "linux/amd64" if machine().endswith("arm64") else ""

    @staticmethod
    def set_local_build_vars(**flags: Any) -> None:
        """Set environment variables for the local Docker build."""
        os.environ.update({k: str(v) for k, v in flags.items()})


BUILDER_SOURCE_CONFIG_LOOKUP: dict[str, type[BuilderSourceConfig]] = {
    "empty": EmptyBuilderSourceConfig,
    "amazon-ebs": AmazonEbs,
    "googlecompute": GoogleComputeBuilder,
    "docker": DockerBuilder,
}


# ---------------------------------------------------------------------------
# Builder resources (provisioners & post-processors)
# ---------------------------------------------------------------------------


class BuilderResource(PackerResource):
    """Base class for resources within a build block (provisioners, post-processors).

    Args:
        _type: The resource type identifier.
    """

    def __init__(self, _type: str) -> None:
        super().__init__(_type=_type)

    @override
    def json(self) -> dict[str, Any]:
        return PackerResource.all_defined_items(self.__dict__)

    @override
    def is_empty(self) -> bool:
        return not PackerResource.all_defined_items(self.__dict__, "type")


class Provisioner(BuilderResource):
    """A Packer provisioner that runs during the build.

    See: https://developer.hashicorp.com/packer/docs/templates/hcl_templates/blocks/build/provisioner

    Args:
        _type: Provisioner type (e.g. ``"shell"``, ``"file"``).
        **kwargs: Additional provisioner-specific options.
    """

    def __init__(self, _type: str, **kwargs: Any) -> None:
        super().__init__(_type)
        self.only: list[str] = kwargs.get("only", [])

    def add_only_sources(self, *sources: BuilderSourceConfig) -> None:
        """Restrict this provisioner to run only for the specified sources."""
        for source in sources:
            self.only.append(repr(source))

    @staticmethod
    def merge_provisioner_json(*provisioners: Provisioner) -> dict[str, Any]:
        """Merge multiple provisioners into a single ``"provisioner"`` block."""
        return {
            "provisioner": [
                {provisioner.type: PackerResource.all_defined_items(provisioner.json(), "type")}
                for provisioner in provisioners
            ]
        }

    @classmethod
    def load_provisioner(cls, content: dict[str, Any]) -> Provisioner:
        """Construct a :class:`Provisioner` from a raw JSON/HCL provisioner block."""
        PackerResource.transform_type_key(content)
        return cls(**content)


class EmptyProvisioner(Provisioner):
    """Placeholder provisioner used when loading configs with no real provisioner."""

    def __init__(self) -> None:
        super().__init__("empty")

    def __hash__(self) -> int:
        return id(self)

    @override
    def __eq__(self, other: object) -> bool:
        return True


class ShellProvisioner(Provisioner):
    """Run shell commands or scripts on the build instance.

    See: https://developer.hashicorp.com/packer/docs/provisioners/shell

    Exactly one of *inline*, *script*, or *scripts* must be provided.

    Args:
        inline: List of shell commands to run inline.
        script: Path to a single script file to upload and execute.
        scripts: List of script file paths to upload and execute in order.
        **kwargs: Additional options like ``execute_command``, ``env``,
            ``environment_vars``.
    """

    def __init__(
        self,
        inline: list[str] | None = None,
        script: str | None = None,
        scripts: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__("shell", **kwargs)
        PackerResource.check_exclusive_inputs(inline=inline, script=script, scripts=scripts)
        self.inline: list[str] | None = inline
        self.script: str | None = script
        self.scripts: list[str] | None = scripts
        self.execute_command: str | None = kwargs.get("execute_command", None)
        self.env: dict[str, str] = kwargs.get("env", {})
        self.environment_vars: list[str] = kwargs.get("environment_vars", [])


class ShellLocalProvisioner(Provisioner):
    """Run shell commands or scripts on the machine running Packer.

    See: https://developer.hashicorp.com/packer/docs/provisioners/shell-local

    Exactly one of *command*, *inline*, *script*, or *scripts* must be provided.

    Args:
        command: A single shell command string to execute locally.
        inline: List of shell commands to run inline.
        script: Path to a single script file to execute locally.
        scripts: List of script file paths to execute locally in order.
        **kwargs: Additional options like ``env``, ``environment_vars``,
            ``execute_command``.
    """

    def __init__(
        self,
        command: str | None = None,
        inline: list[str] | None = None,
        script: str | None = None,
        scripts: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__("shell-local", **kwargs)
        PackerResource.check_exclusive_inputs(command=command, inline=inline, script=script, scripts=scripts)
        self.command: str | None = command
        self.inline: list[str] | None = inline
        self.script: str | None = next(ShellLocalProvisioner.set_scripts(script)) if script else None
        self.scripts: list[str] | None = list(ShellLocalProvisioner.set_scripts(scripts)) if scripts else None
        self.env: dict[str, str] = kwargs.get("env", {})
        self.environment_vars: list[str] = kwargs.get("environment_vars", [])
        self.execute_command: str | None = kwargs.get("execute_command", None)

    @staticmethod
    def set_scripts(*scripts: str) -> Any:
        """Validate and yield script paths, recursing into directories."""
        for script in scripts:
            if os.path.exists(script):
                if os.path.isdir(script):
                    yield ShellLocalProvisioner.set_scripts(*os.listdir(script))
                elif os.path.isfile(script):
                    yield script
            else:
                raise FileExistsError(f"Invalid path {script}")


class FileProvisioner(Provisioner):
    """Upload files or content to the build instance.

    See: https://developer.hashicorp.com/packer/docs/provisioners/file

    Exactly one of *content*, *source*, or *sources* must be provided.

    Args:
        content: Inline string content to write to *destination*.
        source: Path to a single file to upload.
        destination: Remote path to write the file to.
        **kwargs: Additional options including ``sources`` and ``generated``.
    """

    def __init__(
        self,
        content: str | None = None,
        source: str | None = None,
        destination: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__("file", **kwargs)
        self.content: str | None = content
        self.source: str | None = source
        self.destination: str | None = destination
        self.sources: list[str] = kwargs.get("sources", [])
        PackerResource.check_exclusive_inputs(content=self.content, source=self.source, sources=self.sources)
        self.generated: bool = kwargs.get("generated", False)


PROVISIONER_LOOKUP: dict[str, type[Provisioner]] = {
    "empty": EmptyProvisioner,
    "shell": ShellProvisioner,
    "shell-local": ShellLocalProvisioner,
    "file": FileProvisioner,
}


# ---------------------------------------------------------------------------
# Post-processors
# ---------------------------------------------------------------------------


class PostProcessor(BuilderResource):
    """A Packer post-processor that runs after a successful build.

    See: https://developer.hashicorp.com/packer/docs/post-processors

    Args:
        _type: Post-processor type (e.g. ``"manifest"``, ``"docker-tag"``).
        **kwargs: Additional post-processor-specific options.
    """

    def __init__(self, _type: str, **kwargs: Any) -> None:
        super().__init__(_type)
        self.only: list[str] = kwargs.get("only", [])

    def add_only_sources(self, *sources: BuilderSourceConfig) -> None:
        """Restrict this post-processor to run only for the specified sources."""
        for source in sources:
            self.only.append(repr(source))

    @staticmethod
    def merge_post_processor_json(*post_processors: PostProcessor) -> dict[str, Any]:
        """Merge multiple post-processors into a single ``"post-processors"`` block."""
        ret: dict[str, Any] = {"post-processors": [{"post-processor": {}}]}
        for post_processor in post_processors:
            if post_processor.type not in ret["post-processors"][0]["post-processor"]:
                ret["post-processors"][0]["post-processor"][post_processor.type] = []
            ret["post-processors"][0]["post-processor"][post_processor.type].append(
                PackerResource.all_defined_items(post_processor.json(), "type")
            )
        return ret

    @classmethod
    def load_post_processor(cls, content: dict[str, Any]) -> PostProcessor:
        """Construct a :class:`PostProcessor` from a raw JSON/HCL post-processor block."""
        PackerResource.transform_type_key(content)
        return cls(**content)


class EmptyPostProcessor(PostProcessor):
    """Placeholder post-processor used when loading configs with no real post-processor."""

    def __init__(self) -> None:
        super().__init__("empty")

    def __hash__(self) -> int:
        return id(self)

    @override
    def __eq__(self, other: object) -> bool:
        return True


class Manifest(PostProcessor):
    """Write a manifest of the build artifacts to a JSON file.

    See: https://developer.hashicorp.com/packer/docs/post-processors/manifest

    Args:
        output: Path to write the manifest JSON file.
    """

    def __init__(self, output: str) -> None:
        super().__init__("manifest")
        self.output: str = output


class DockerImport(PostProcessor):
    """Import a Docker container as an image.

    See: https://developer.hashicorp.com/packer/plugins/post-processors/docker/docker-import

    Args:
        repository: The Docker repository to import into.
        **kwargs: Optional parameters including ``tag``.
    """

    def __init__(self, repository: str, **kwargs: Any) -> None:
        super().__init__("docker-import", **kwargs)
        self.repository: str = repository
        self.tag: str = kwargs.get("tag", "latest")


class DockerTag(PostProcessor):
    """Tag a Docker image.

    See: https://developer.hashicorp.com/packer/plugins/post-processors/docker/docker-tag

    Args:
        repository: The Docker repository to tag.
        **kwargs: Optional parameters including ``tags``.
    """

    def __init__(self, repository: str, **kwargs: Any) -> None:
        super().__init__("docker-tag", **kwargs)
        self.repository: str = repository
        self.tags: list[str] = parse_list(kwargs.get("tags", []))


class DockerPush(PostProcessor):
    """Push a Docker image to a registry.

    See: https://developer.hashicorp.com/packer/plugins/post-processors/docker/docker-push

    Exactly one of *ecr_login* or *login* must be provided.

    Args:
        **kwargs: Authentication parameters — either ECR-based
            (``ecr_login``, ``aws_access_key``, ``aws_secret_key``, ``aws_token``)
            or username/password-based (``login``, ``login_username``,
            ``login_password``, ``login_server``).
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__("docker-push", **kwargs)
        self.ecr_login: bool | None = kwargs.get("ecr_login", None)
        self.login: bool | None = kwargs.get("login", None)
        PackerResource.check_exclusive_inputs(ecr_login=self.ecr_login, login=self.login)
        self.aws_access_key: str | None = kwargs.get("aws_access_key", None)
        self.aws_secret_key: str | None = kwargs.get("aws_secret_key", None)
        self.aws_token: str | None = kwargs.get("aws_token", None)
        PackerResource.check_inclusive_inputs(
            ecr_login=self.ecr_login,
            aws_access_key=self.aws_access_key,
            aws_secret_key=self.aws_secret_key,
            aws_token=self.aws_token,
        )
        self.login_server: str | None = kwargs.get("login_server", None)
        self.login_username: str | None = kwargs.get("login_username", None)
        self.login_password: str | None = kwargs.get("login_password", None)
        PackerResource.check_inclusive_inputs(
            login=self.login, login_username=self.login_username, login_password=self.login_password
        )


POST_PROCESSOR_LOOKUP: dict[str, type[PostProcessor]] = {
    "empty": EmptyPostProcessor,
    "manifest": Manifest,
    "docker-import": DockerImport,
    "docker-tag": DockerTag,
    "docker-push": DockerPush,
}


# ---------------------------------------------------------------------------
# Build & config
# ---------------------------------------------------------------------------


class Builder(PackerResource):
    """A Packer build block that ties together sources, provisioners, and post-processors.

    See: https://developer.hashicorp.com/packer/docs/templates/hcl_templates/blocks/build

    Args:
        name: A unique name for this build.
    """

    def __init__(self, name: str) -> None:
        super().__init__(name=name)
        self.sources: list[str] = []
        self.provisioners: list[Provisioner] = []
        self.post_processors: list[PostProcessor] = []

    @override
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Builder):
            return NotImplemented
        return self.json() == other.json()

    def add_source(self, *builder_source_configs: BuilderSourceConfig) -> None:
        """Add one or more builder sources to this build, deduplicating by string representation."""
        self.sources.extend([str(bsc) for bsc in builder_source_configs if str(bsc) not in self.sources])

    def add_provisioner(self, *provisioners: Provisioner) -> None:
        """Append provisioners to the build's provisioner list."""
        self.provisioners.extend(provisioners)

    def add_post_processor(self, *post_processors: PostProcessor) -> None:
        """Append post-processors to the build's post-processor list."""
        self.post_processors.extend(post_processors)

    @override
    def json(self) -> dict[str, Any]:
        ret: dict[str, Any] = {
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

    @override
    def is_empty(self) -> bool:
        return not any((self.sources, self.provisioners, self.post_processors))

    def get_only_source(self, source_name: str) -> list[str]:
        """Return sources whose string representation contains *source_name*."""
        return list(filter(lambda source_str: source_name in source_str, self.sources))

    @classmethod
    def load_builder(cls, content: dict[str, Any], name: str | None = None) -> Builder:
        """Construct a :class:`Builder` from a parsed Packer config dict.

        Args:
            content: The full parsed config (expects a ``"build"`` key).
            name: Fallback name if the config has no build block.

        Raises:
            PackerBuildError: If no build block is found and no *name* is given.
        """
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
            builder.add_provisioner(
                *(
                    PROVISIONER_LOOKUP[provisioner_type].load_provisioner(provisioner_data)
                    for provisioner in builder_data.get("provisioner", [])
                    for provisioner_type, provisioner_data in provisioner.items()
                )
            )
            for post_processor_list_item in builder_data.get("post-processors", []):
                for pp_type, pp_data_list in post_processor_list_item.get("post-processor", {}).items():
                    builder.add_post_processor(
                        POST_PROCESSOR_LOOKUP[pp_type].load_post_processor(next(iter(pp_data_list)))
                    )
        return builder


class PackerConfig:
    """Top-level Packer configuration that produces a complete ``.pkr.json`` template.

    A ``PackerConfig`` aggregates requirements, builder sources, and a
    :class:`Builder` (with its provisioners and post-processors) into a
    single serializable structure.

    Args:
        config_name: A human-readable name for this configuration.
        log: Optional logger instance.
    """

    def __init__(self, config_name: str, log: logging.Logger | None = None) -> None:
        self.config_name: str = config_name
        self.builder: Builder = Builder(self.config_name)
        self.requirements: Requirements = Requirements()
        self.builder_sources: dict[str, BuilderSourceConfig] = {}
        self.log: logging.Logger = log or logging.getLogger(PackerConfig.__name__)

    def __str__(self) -> str:
        return self.config_name

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PackerConfig):
            return NotImplemented
        try:
            return all(
                (
                    self.config_name == other.config_name,
                    self.builder == other.builder,
                    self.requirements == other.requirements,
                    set(self.builder_sources.keys()) == set(other.builder_sources.keys()),
                    all(self.builder_sources[k] == other.builder_sources[k] for k in self.builder_sources),
                )
            )
        except KeyError:
            return False

    def set_requirements(self, requirements: Requirements) -> None:
        """Replace the current requirements with *requirements*."""
        self.requirements = requirements

    def add_builder_source(self, *builder_sources: BuilderSourceConfig) -> None:
        """Register builder sources and add them to the build block."""
        self.builder_sources.update({builder_source.name: builder_source for builder_source in builder_sources})
        self.builder.add_source(*builder_sources)

    def json(self) -> dict[str, Any]:
        """Serialize the full configuration to a Packer-compatible dict."""
        ret: dict[str, Any] = {}
        ret.update(self.requirements.json())
        ret.update(BuilderSourceConfig.merge_builder_source_json(*self.builder_sources.values()))
        ret.update(self.builder.json())
        return ret

    def is_empty(self) -> bool:
        return not any(
            (
                not self.requirements.is_empty(),
                not self.builder.is_empty(),
                not any((builder_source.is_empty() for builder_source in self.builder_sources.values())),
            )
        )

    @classmethod
    def load_config(
        cls,
        config_name: str,
        config_path: str | None = None,
        config_content: dict[str, Any] | str | None = None,
        config_type: str | None = None,
    ) -> PackerConfig:
        """Load a Packer configuration from a file, dict, or raw string.

        Provide exactly one of the following:

        - ``config_path``: Path to a ``.json`` or ``.hcl`` file.
        - ``config_content`` (dict): An already-parsed config dictionary.
        - ``config_content`` (str) + ``config_type``: A raw JSON or HCL string
          with its type specified as ``"json"`` or ``"hcl"``.

        Args:
            config_name: A name for the resulting configuration.
            config_path: Path to a Packer config file.
            config_content: A parsed dict or raw config string.
            config_type: ``"json"`` or ``"hcl"`` — required when *config_content*
                is a string.

        Returns:
            A fully populated :class:`PackerConfig`.

        Raises:
            ValueError: If the input combination is invalid or the file type
                is unsupported.
        """
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
                    supported = ", ".join(file_loader.keys())
                    data = file_loader.get(
                        file_type,
                        lambda: raise_(ValueError(f"Unsupported file type {file_type}. Supported Types: {supported}")),
                    )(fp)
            else:
                data = {}
        elif config_content and isinstance(config_content, dict):
            data = config_content
        elif config_content and isinstance(config_content, str) and config_type:
            supported = ", ".join(content_loader.keys())
            data = content_loader.get(
                config_type,
                lambda: raise_(ValueError(f"Unsupported file type {config_type}. Supported Types: {supported}")),
            )(config_content)
        else:
            raise ValueError(
                "Expected one of the following combinations of input vars: "
                "[config_path|config_content (type: dict)|config_content (type: str) and config_type]"
            )
        config.set_requirements(Requirements.load_requirements(data))
        config.builder = Builder.load_builder(data, name=config_name)
        [
            [
                config.add_builder_source(BUILDER_SOURCE_CONFIG_LOOKUP[_type].load_builder_source_config(source[_type]))
                for _type in source.keys()
            ]
            for source in data.get("source", [])
        ]
        return config
