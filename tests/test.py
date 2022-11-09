import unittest

from packerpy.models import *


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
        self.assertDictEqual(self.plugin.json(), {
            "test": {
                "version": "= test_version",
                "source": "test_source",
            }
        })

    def test_is_empty(self):
        self.assertFalse(self.plugin.is_empty())

    def test_load_plugin(self):
        plugin_json = {
            "version": "> 1.0.6",
            "source": "github.com/user/repo",
        }
        self.assertEqual(Plugin.load_plugin("test_plugin", plugin_json),
                         Plugin("test_plugin", "1.0.6", ">", "github.com/user/repo"))


class TestRequirements(BasePackerTest):
    def setUp(self):
        self.requirements = Requirements()

    def test_is_empty(self):
        self.assertTrue(self.requirements.is_empty())

    def test_json_1(self):
        self.requirements.set_version_constraint(">=1")
        self.assertDictEqual(self.requirements.json(), {
            "packer": [
                {
                    "required_version": self.requirements.version_constraint,
                }
            ]
        })

    def test_json_2(self):
        plugin = Plugin("test", "1", ">", "test_source")
        self.requirements.add_plugin(plugin)
        self.assertDictEqual(self.requirements.json(), {
            "packer": [
                {
                    "required_plugins": [
                        plugin.json(),
                    ],
                },
            ],
        })

    def test_json_3(self):
        plugin = Plugin("test", "1", ">", "test_source")
        self.requirements.add_plugin(plugin)
        self.requirements.set_version_constraint(">=1.0.1")
        self.assertDictEqual(self.requirements.json(), {
            "packer": [
                {
                    "required_version": self.requirements.version_constraint,
                    "required_plugins": [
                        plugin.json(),
                    ]
                }
            ]
        })

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
                    ]
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
        self.assertDictEqual(self.builder_source.json(), {
            "test_type": {
                "test_name": {}
            }
        })

    def test_json_with_supporting_type(self):
        amazon_builder = AmazonEbs("amazon-ami",
                                   "ami-name",
                                   "us-east-1",
                                   "test-key",
                                   "test-secret",
                                   launch_block_device_mappings={
                                       "delete_on_termination": True,
                                       "device_name": "some-device",
                                       "encrypted": False,
                                   })
        self.assertDictEqual(amazon_builder.json(), {
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
        })

    def test_is_empty(self):
        self.assertFalse(self.builder_source.is_empty())

    def test_merge_builder_source_json(self):
        builder_sources = [
            self.builder_source,
            BuilderSourceConfig("test_type_2", "test_name_2")
        ]
        self.assertDictEqual(BuilderSourceConfig.merge_builder_source_json(*builder_sources),
                             {"source": [builder_source.json() for builder_source in builder_sources]})

    def test_load_builder_source_config_empty(self):
        self.assertDictEqual(BuilderSourceConfig.load_builder_source_config({}).json(),
                             EmptyBuilderSourceConfig().json())

    def test_load_builder_source_config(self):
        builder_source_json = {"test_name": {"type": "test_type"}}
        self.assertDictEqual(BuilderSourceConfig.load_builder_source_config(builder_source_json).json(),
                             BuilderSourceConfig("test_type", "test_name").json())


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
        self.assertDictEqual(Provisioner.merge_provisioner_json(self.provisioner), {
            "provisioner": [
                {
                    "test_provisioner": {
                        "only": ["test_type.test_name"]
                    }
                }
            ]
        })

    def test_json_with_multiple_only(self):
        self.provisioner.add_only_sources(BuilderSourceConfig("test_type", "test_name"),
                                          BuilderSourceConfig("test_type_2", "test_name_2"))
        self.assertDictEqual(Provisioner.merge_provisioner_json(self.provisioner), {
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
        })

    def test_json_without_only(self):
        self.assertDictEqual(Provisioner.merge_provisioner_json(self.provisioner),
                             {"provisioner": [{"test_provisioner": {}}]})

    def test_merge_provisioner_json(self):
        self.assertDictEqual(
            Provisioner.merge_provisioner_json(*[self.provisioner, Provisioner("test_provisioner_2")]),
            {
                "provisioner": [
                    {"test_provisioner": {}},
                    {"test_provisioner_2": {}},
                ]
            }
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
            }
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
        self.assertDictEqual(self.builder.json(), {
            "build": [
                {
                    "name": "test_builder",
                    "sources": ["source.builder_source_type.builder_source_name"],
                    "provisioner": [
                        {
                            "test_provisioner": {}
                        }
                    ],
                    "post-processors": [
                        {
                            "post-processor": {
                                "test_post_processor": [{}]
                            }
                        }
                    ]
                }
            ]
        })

    def test_load_builder_empty_with_name(self):
        self.assertEqual(Builder.load_builder({}, name="test_builder"), Builder("test_builder"))

    def test_load_builder_empty_no_name(self):
        with self.assertRaises(PackerBuildError):
            Builder.load_builder({})

    def test_load_builder_valid_config(self):
        actual = Builder.load_builder({
            "build": [
                {
                    "name": "test_builder",
                    "sources": ["source.empty.builder_source_name"],
                    "provisioner": [
                        {
                            "empty": {}
                        }
                    ],
                    "post-processors": [
                        {
                            "post-processor": {
                                "empty": [{}]
                            }
                        }
                    ]
                }
            ]
        })
        expected = Builder("test_builder")
        expected.add_source(EmptyBuilderSourceConfig("builder_source_name"))
        expected.add_provisioner(EmptyProvisioner())
        expected.add_post_processor(EmptyPostProcessor())
        self.assertEqual(actual, expected)


class TestPackerConfig(BasePackerTest):
    def setUp(self):
        self.config = PackerConfig("test_config")
        self.config.requirements.add_plugin(Plugin("test_plugin", "1.0.1", "=", "github.com/user/repo"))
        self.config.add_builder_source(BuilderSourceConfig("test_bsc_type_1", "test_bsc_name_1"),
                                       BuilderSourceConfig("test_bsc_type_2", "test_bsc_name_2"))
        self.config.builder.add_provisioner(Provisioner("test_provisioner"))
        self.config.builder.add_post_processor(PostProcessor("test_post_processor"))

    def test_str(self):
        self.assertEqual(str(self.config), "test_config")

    def test_is_empty(self):
        self.assertFalse(self.config.is_empty())

    def test_json(self):
        self.assertDictEqual(self.config.json(), {
            "packer": [
                {
                    "required_plugins": [
                        {
                            "test_plugin": {
                                "version": "= 1.0.1",
                                "source": "github.com/user/repo"
                            }
                        }
                    ]
                }
            ],
            "source": [
                {
                    "test_bsc_type_1": {
                        "test_bsc_name_1": {}
                    }
                },
                {
                    "test_bsc_type_2": {
                        "test_bsc_name_2": {}
                    }
                }
            ],
            "build": [
                {
                    "name": "test_config",
                    "sources": [
                        "source.test_bsc_type_1.test_bsc_name_1",
                        "source.test_bsc_type_2.test_bsc_name_2",
                    ],
                    "provisioner": [
                        {
                            "test_provisioner": {}
                        }
                    ],
                    "post-processors": [
                        {
                            "post-processor": {
                                "test_post_processor": [{}]
                            }
                        }
                    ]
                }
            ]
        })

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
            "source": [
                {
                    "empty": {
                        "test_bsc_name_1": {}
                    }
                }
            ],
            "build": [
                {
                    "name": "test_config",
                    "sources": ["source.empty.test_bsc_name_1"],
                    "provisioner": [{"empty": {}}],
                    "post-processors": [{"post-processor": {"empty": [{}]}}]
                }
            ]
        }
        expected = PackerConfig("test_config")
        expected.requirements.add_plugin(Plugin("test_plugin", "1.0.1", "=", "github.com/user/repo"))
        bsc1 = EmptyBuilderSourceConfig("test_bsc_name_1")
        expected.add_builder_source(bsc1)
        expected.builder.add_provisioner(EmptyProvisioner())
        expected.builder.add_post_processor(EmptyPostProcessor())
        actual = PackerConfig.load_config("test_config", config_content=config_data)
        self.assertEqual(actual, expected)






