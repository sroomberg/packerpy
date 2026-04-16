import json
import os
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from packerpy.builder import PackerBuilder
from packerpy.client import PackerClient
from packerpy.exceptions import PackerBuildError, PackerClientError
from packerpy.models import (
    AmazonEbs,
    Builder,
    BuilderResource,
    BuilderSourceConfig,
    EmptyBuilderSourceConfig,
    EmptyPostProcessor,
    EmptyProvisioner,
    PackerConfig,
    PackerResource,
    Plugin,
    PostProcessor,
    Provisioner,
    Requirements,
)


class BasePackerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.maxDiff = None


class TestPackerResource(BasePackerTest):
    def setUp(self):
        self.packer_resource = PackerResource("test", "test")

    def test_json(self):
        self.assertDictEqual(self.packer_resource.json(), {"type": "test", "name": "test"})

    def test_is_empty(self):
        self.assertFalse(self.packer_resource.is_empty())

    def test_is_empty_without_name(self):
        self.packer_resource.name = None
        self.assertFalse(self.packer_resource.is_empty())

    def test_is_empty_without_type(self):
        self.packer_resource.type = None
        self.assertFalse(self.packer_resource.is_empty())

    def test_is_empty_without_attrs(self):
        self.packer_resource.name = None
        self.packer_resource.type = None
        self.assertTrue(self.packer_resource.is_empty())

    @unittest.expectedFailure
    def test_exclusive_inputs(self):
        with self.assertRaises(ValueError):
            PackerResource.check_exclusive_inputs(a="", b=None, c=[], d={}, e=True)

    def test_exclusive_inputs_multiple_inputs(self):
        with self.assertRaises(ValueError):
            PackerResource.check_exclusive_inputs(a="", b=None, c=["something"], d="hello")

    def test_exclusive_inputs_no_inputs(self):
        with self.assertRaises(ValueError):
            PackerResource.check_exclusive_inputs(a="", b=None, c=[], d={}, e=False)

    @unittest.expectedFailure
    def test_inclusive_inputs(self):
        with self.assertRaises(ValueError):
            PackerResource.check_inclusive_inputs(a="hello", b=1, c=True)

    @unittest.expectedFailure
    def test_inclusive_inputs_without_values(self):
        with self.assertRaises(ValueError):
            PackerResource.check_inclusive_inputs(a="", b=None, c=[], d={}, e=False)

    def test_inclusive_inputs_failure(self):
        with self.assertRaises(ValueError):
            PackerResource.check_exclusive_inputs(a="", b=True, c=["something"], d="hello")

    def test_all_defined_items(self):
        test_dict = dict(a="", b=None, c=["something"], d="hello")
        self.assertDictEqual(PackerResource.all_defined_items(test_dict), dict(c=["something"], d="hello"))

    def test_all_defined_items_empty(self):
        test_dict = dict(a="", b=None, c=[])
        self.assertDictEqual(PackerResource.all_defined_items(test_dict), dict())

    def test_all_defined_items_with_keys_to_remove(self):
        test_dict = dict(a="hello", b=1, c=True)
        self.assertDictEqual(PackerResource.all_defined_items(test_dict, "a"), dict(b=1, c=True))


class TestPlugin(BasePackerTest):
    def setUp(self):
        self.plugin = Plugin("test", "test_version", "=", "test_source")

    def test_json(self):
        self.assertDictEqual(
            self.plugin.json(),
            {
                "test": {
                    "version": "= test_version",
                    "source": "test_source",
                }
            },
        )

    def test_is_empty(self):
        self.assertFalse(self.plugin.is_empty())

    def test_load_plugin(self):
        plugin_json = {
            "version": "> 1.0.6",
            "source": "github.com/user/repo",
        }
        self.assertEqual(
            Plugin.load_plugin("test_plugin", plugin_json), Plugin("test_plugin", "1.0.6", ">", "github.com/user/repo")
        )


class TestRequirements(BasePackerTest):
    def setUp(self):
        self.requirements = Requirements()

    def test_is_empty(self):
        self.assertTrue(self.requirements.is_empty())

    def test_json_1(self):
        self.requirements.set_version_constraint(">=1")
        self.assertDictEqual(
            self.requirements.json(),
            {
                "packer": [
                    {
                        "required_version": self.requirements.version_constraint,
                    }
                ]
            },
        )

    def test_json_2(self):
        plugin = Plugin("test", "1", ">", "test_source")
        self.requirements.add_plugin(plugin)
        self.assertDictEqual(
            self.requirements.json(),
            {
                "packer": [
                    {
                        "required_plugins": [
                            plugin.json(),
                        ],
                    },
                ],
            },
        )

    def test_json_3(self):
        plugin = Plugin("test", "1", ">", "test_source")
        self.requirements.add_plugin(plugin)
        self.requirements.set_version_constraint(">=1.0.1")
        self.assertDictEqual(
            self.requirements.json(),
            {
                "packer": [
                    {
                        "required_version": self.requirements.version_constraint,
                        "required_plugins": [
                            plugin.json(),
                        ],
                    }
                ]
            },
        )

    def test_valid_version_1(self):
        match = Requirements.version_match("> 1.0.1")
        self.assertEqual(match.group(1), ">")
        self.assertEqual(match.group(2), "1.0.1")

    def test_valid_version_2(self):
        match = Requirements.version_match(">1.0.1")
        self.assertEqual(match.group(1), ">")
        self.assertEqual(match.group(2), "1.0.1")

    def test_invalid_version_1(self):
        with self.assertRaises(PackerBuildError):
            Requirements.version_match("")

    def test_invalid_version_2(self):
        with self.assertRaises(PackerBuildError):
            Requirements.version_match("~>1")

    def test_invalid_version_3(self):
        with self.assertRaises(PackerBuildError):
            Requirements.version_match("badversion")

    def test_load_requirements(self):
        requirements_json = {
            "packer": [
                {
                    "required_version": ">=2",
                    "required_plugins": [
                        {
                            "test_plugin": {
                                "version": "= 1.0.1",
                                "source": "github.com/user/repo",
                            }
                        }
                    ],
                }
            ]
        }
        self.requirements.set_version_constraint(">=2")
        self.requirements.add_plugin(Plugin("test_plugin", "1.0.1", "=", "github.com/user/repo"))
        self.assertDictEqual(Requirements.load_requirements(requirements_json).json(), self.requirements.json())


class TestBuilderSourceConfig(BasePackerTest):
    def setUp(self):
        self.builder_source = BuilderSourceConfig("test_type", "test_name")

    def test_repr(self):
        self.assertEqual(repr(self.builder_source), "test_type.test_name")

    def test_str(self):
        self.assertEqual(str(self.builder_source), "source.test_type.test_name")

    def test_json(self):
        self.assertDictEqual(self.builder_source.json(), {"test_type": {"test_name": {}}})

    def test_json_with_supporting_type(self):
        amazon_builder = AmazonEbs(
            "amazon-ami",
            "ami-name",
            "us-east-1",
            "test-key",
            "test-secret",
            launch_block_device_mappings={
                "delete_on_termination": True,
                "device_name": "some-device",
                "encrypted": False,
            },
        )
        self.assertDictEqual(
            amazon_builder.json(),
            {
                "amazon-ebs": {
                    "amazon-ami": {
                        "ami_name": "ami-name",
                        "region": "us-east-1",
                        "access_key": "test-key",
                        "secret_key": "test-secret",
                        "launch_block_device_mappings": {
                            "delete_on_termination": True,
                            "device_name": "some-device",
                            "encrypted": False,
                        },
                    }
                }
            },
        )

    def test_is_empty(self):
        self.assertFalse(self.builder_source.is_empty())

    def test_merge_builder_source_json(self):
        builder_sources = [self.builder_source, BuilderSourceConfig("test_type_2", "test_name_2")]
        self.assertDictEqual(
            BuilderSourceConfig.merge_builder_source_json(*builder_sources),
            {"source": [builder_source.json() for builder_source in builder_sources]},
        )

    def test_load_builder_source_config_empty(self):
        self.assertDictEqual(
            BuilderSourceConfig.load_builder_source_config({}).json(), EmptyBuilderSourceConfig().json()
        )

    def test_load_builder_source_config(self):
        builder_source_json = {"test_name": {"type": "test_type"}}
        self.assertDictEqual(
            BuilderSourceConfig.load_builder_source_config(builder_source_json).json(),
            BuilderSourceConfig("test_type", "test_name").json(),
        )


class TestBuilderResource(BasePackerTest):
    def setUp(self):
        self.builder_resource = BuilderResource("test_resource")

    def test_json(self):
        self.assertDictEqual(self.builder_resource.json(), {"type": "test_resource"})

    def test_is_empty(self):
        self.assertTrue(self.builder_resource.is_empty())


class TestProvisioner(BasePackerTest):
    def setUp(self):
        self.provisioner = Provisioner("test_provisioner")

    def test_json_with_only(self):
        self.provisioner.add_only_sources(BuilderSourceConfig("test_type", "test_name"))
        self.assertDictEqual(
            Provisioner.merge_provisioner_json(self.provisioner),
            {"provisioner": [{"test_provisioner": {"only": ["test_type.test_name"]}}]},
        )

    def test_json_with_multiple_only(self):
        self.provisioner.add_only_sources(
            BuilderSourceConfig("test_type", "test_name"), BuilderSourceConfig("test_type_2", "test_name_2")
        )
        self.assertDictEqual(
            Provisioner.merge_provisioner_json(self.provisioner),
            {
                "provisioner": [
                    {
                        "test_provisioner": {
                            "only": [
                                "test_type.test_name",
                                "test_type_2.test_name_2",
                            ]
                        }
                    }
                ]
            },
        )

    def test_json_without_only(self):
        self.assertDictEqual(
            Provisioner.merge_provisioner_json(self.provisioner), {"provisioner": [{"test_provisioner": {}}]}
        )

    def test_merge_provisioner_json(self):
        self.assertDictEqual(
            Provisioner.merge_provisioner_json(*[self.provisioner, Provisioner("test_provisioner_2")]),
            {
                "provisioner": [
                    {"test_provisioner": {}},
                    {"test_provisioner_2": {}},
                ]
            },
        )

    def test_load_provisioner(self):
        provisioner_json = {"_type": "test_type"}
        self.assertEqual(Provisioner.load_provisioner(provisioner_json), Provisioner("test_type"))


class TestPostProcessor(BasePackerTest):
    def test_merge_post_processor_json(self):
        self.assertDictEqual(
            PostProcessor.merge_post_processor_json(*[PostProcessor("test_pp_1"), PostProcessor("test_pp_2")]),
            {
                "post-processors": [
                    {
                        "post-processor": {
                            "test_pp_1": [{}],
                            "test_pp_2": [{}],
                        }
                    }
                ]
            },
        )

    def test_load_post_processor(self):
        self.assertEqual(PostProcessor.load_post_processor({"type": "test_type"}), PostProcessor("test_type"))


class TestBuilder(BasePackerTest):
    def setUp(self):
        self.builder = Builder("test_builder")
        self.builder.add_source(BuilderSourceConfig("builder_source_type", "builder_source_name"))
        self.builder.add_provisioner(Provisioner("test_provisioner"))
        self.builder.add_post_processor(PostProcessor("test_post_processor"))

    def test_is_empty(self):
        self.assertFalse(self.builder.is_empty())

    def test_json(self):
        self.assertDictEqual(
            self.builder.json(),
            {
                "build": [
                    {
                        "name": "test_builder",
                        "sources": ["source.builder_source_type.builder_source_name"],
                        "provisioner": [{"test_provisioner": {}}],
                        "post-processors": [{"post-processor": {"test_post_processor": [{}]}}],
                    }
                ]
            },
        )

    def test_load_builder_empty_with_name(self):
        self.assertEqual(Builder.load_builder({}, name="test_builder"), Builder("test_builder"))

    def test_load_builder_empty_no_name(self):
        with self.assertRaises(PackerBuildError):
            Builder.load_builder({})

    def test_load_builder_valid_config(self):
        actual = Builder.load_builder(
            {
                "build": [
                    {
                        "name": "test_builder",
                        "sources": ["source.empty.builder_source_name"],
                        "provisioner": [{"empty": {}}],
                        "post-processors": [{"post-processor": {"empty": [{}]}}],
                    }
                ]
            }
        )
        expected = Builder("test_builder")
        expected.add_source(EmptyBuilderSourceConfig("builder_source_name"))
        expected.add_provisioner(EmptyProvisioner())
        expected.add_post_processor(EmptyPostProcessor())
        self.assertEqual(actual, expected)


class TestPackerConfig(BasePackerTest):
    def setUp(self):
        self.config = PackerConfig("test_config")
        self.config.requirements.add_plugin(Plugin("test_plugin", "1.0.1", "=", "github.com/user/repo"))
        self.config.add_builder_source(
            BuilderSourceConfig("test_bsc_type_1", "test_bsc_name_1"),
            BuilderSourceConfig("test_bsc_type_2", "test_bsc_name_2"),
        )
        self.config.builder.add_provisioner(Provisioner("test_provisioner"))
        self.config.builder.add_post_processor(PostProcessor("test_post_processor"))

    def test_str(self):
        self.assertEqual(str(self.config), "test_config")

    def test_is_empty(self):
        self.assertFalse(self.config.is_empty())

    def test_json(self):
        self.assertDictEqual(
            self.config.json(),
            {
                "packer": [
                    {"required_plugins": [{"test_plugin": {"version": "= 1.0.1", "source": "github.com/user/repo"}}]}
                ],
                "source": [{"test_bsc_type_1": {"test_bsc_name_1": {}}}, {"test_bsc_type_2": {"test_bsc_name_2": {}}}],
                "build": [
                    {
                        "name": "test_config",
                        "sources": [
                            "source.test_bsc_type_1.test_bsc_name_1",
                            "source.test_bsc_type_2.test_bsc_name_2",
                        ],
                        "provisioner": [{"test_provisioner": {}}],
                        "post-processors": [{"post-processor": {"test_post_processor": [{}]}}],
                    }
                ],
            },
        )

    def test_load_config(self):
        config_data = {
            "packer": [
                {
                    "required_plugins": [
                        {
                            "test_plugin": {
                                "version": "= 1.0.1",
                                "source": "github.com/user/repo",
                            }
                        }
                    ]
                }
            ],
            "source": [{"empty": {"test_bsc_name_1": {}}}],
            "build": [
                {
                    "name": "test_config",
                    "sources": ["source.empty.test_bsc_name_1"],
                    "provisioner": [{"empty": {}}],
                    "post-processors": [{"post-processor": {"empty": [{}]}}],
                }
            ],
        }
        expected = PackerConfig("test_config")
        expected.requirements.add_plugin(Plugin("test_plugin", "1.0.1", "=", "github.com/user/repo"))
        bsc1 = EmptyBuilderSourceConfig("test_bsc_name_1")
        expected.add_builder_source(bsc1)
        expected.builder.add_provisioner(EmptyProvisioner())
        expected.builder.add_post_processor(EmptyPostProcessor())
        actual = PackerConfig.load_config("test_config", config_content=config_data)
        self.assertEqual(actual, expected)


class _ConcreteBuilder(PackerBuilder):
    """Minimal concrete subclass for testing PackerBuilder."""

    def configure(self) -> None:
        pass


class TestPackerClient(BasePackerTest):
    def setUp(self):
        with patch.object(PackerClient, "verify_packer_installation"):
            self.client = PackerClient("test.pkr.json")

    def test_invalid_command_raises_error(self):
        with self.assertRaises(PackerClientError):
            self.client.run("notacommand")

    def test_run_returns_process(self):
        mock_proc = MagicMock()
        mock_proc.stdout = []
        mock_proc.returncode = 0
        with patch("packerpy.client.subprocess.Popen", return_value=mock_proc):
            result = self.client.run("validate")
        self.assertIs(result, mock_proc)

    def test_run_streams_output_to_logger(self):
        mock_proc = MagicMock()
        mock_proc.stdout = ["line1\n", "line2\n"]
        mock_proc.returncode = 0
        with patch("packerpy.client.subprocess.Popen", return_value=mock_proc):
            with self.assertLogs("PackerClient", level="INFO") as cm:
                self.client.run("validate")
        self.assertIn("INFO:PackerClient:line1", cm.output)
        self.assertIn("INFO:PackerClient:line2", cm.output)

    def test_run_writes_stream_file(self):
        mock_proc = MagicMock()
        mock_proc.stdout = ["line1\n"]
        mock_proc.returncode = 0
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(PackerClient, "verify_packer_installation"):
                client = PackerClient("test.pkr.json", stream_file_dir=tmpdir)
            with patch("packerpy.client.subprocess.Popen", return_value=mock_proc):
                client.run("validate")
            log_path = os.path.join(tmpdir, "packer-validate.log")
            self.assertTrue(os.path.exists(log_path))
            with open(log_path) as f:
                self.assertEqual(f.read(), "line1\n")

    def test_verify_packer_installation_success(self):
        with patch("packerpy.client.subprocess.check_call") as mock_check:
            PackerClient.verify_packer_installation()
            mock_check.assert_called_once_with(["packer", "version"])

    def test_verify_packer_not_installed_called_process_error(self):
        with patch("packerpy.client.subprocess.check_call", side_effect=subprocess.CalledProcessError(1, "packer")):
            with self.assertRaises(EnvironmentError):
                PackerClient.verify_packer_installation()

    def test_verify_packer_not_installed_file_not_found(self):
        with patch("packerpy.client.subprocess.check_call", side_effect=FileNotFoundError):
            with self.assertRaises(EnvironmentError):
                PackerClient.verify_packer_installation()


class TestPackerBuilder(BasePackerTest):
    def setUp(self):
        with patch("packerpy.builder.PackerClient"):
            self.builder = _ConcreteBuilder("test-build")
        self.mock_client = self.builder.client

    def _make_proc(self, returncode: int = 0) -> MagicMock:
        proc = MagicMock()
        proc.returncode = returncode
        return proc

    def test_artifact_exists_no_file(self):
        self.builder.manifest_file = "/nonexistent/path/manifest.json"
        self.assertFalse(self.builder.artifact_exists())

    def test_artifact_exists_with_artifact(self):
        manifest = {"builds": [{"artifact_id": "ami-12345"}]}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(manifest, f)
            self.builder.manifest_file = f.name
        try:
            self.assertTrue(self.builder.artifact_exists())
        finally:
            os.unlink(self.builder.manifest_file)

    def test_artifact_exists_without_artifact_id(self):
        manifest = {"builds": [{}]}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(manifest, f)
            self.builder.manifest_file = f.name
        try:
            self.assertFalse(self.builder.artifact_exists())
        finally:
            os.unlink(self.builder.manifest_file)

    def test_build_init_failure_raises_error(self):
        self.mock_client.run.return_value = self._make_proc(returncode=1)
        with self.assertRaises(PackerBuildError):
            self.builder.build()

    def test_build_validate_failure_raises_error(self):
        def run_side_effect(command, *args):
            return self._make_proc(returncode=0 if command == "init" else 1)

        self.mock_client.run.side_effect = run_side_effect
        with self.assertRaises(PackerBuildError):
            self.builder.build()

    def test_build_failure_raises_error(self):
        def run_side_effect(command, *args):
            return self._make_proc(returncode=0 if command in ("init", "validate") else 1)

        self.mock_client.run.side_effect = run_side_effect
        self.builder.manifest_file = "/nonexistent/manifest.json"
        with self.assertRaises(PackerBuildError):
            self.builder.build()

    def test_build_no_artifact_raises_error(self):
        self.mock_client.run.return_value = self._make_proc(returncode=0)
        self.builder.manifest_file = "/nonexistent/manifest.json"
        with self.assertRaises(PackerBuildError):
            self.builder.build()

    def test_build_success(self):
        self.mock_client.run.return_value = self._make_proc(returncode=0)
        manifest = {"builds": [{"artifact_id": "ami-12345"}]}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(manifest, f)
            self.builder.manifest_file = f.name
        try:
            self.builder.build()  # should not raise
        finally:
            os.unlink(self.builder.manifest_file)
