import unittest

from .models import *


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
            PackerResource.check_exclusive_inputs(a="", b=None, c=[], d={}, e=False)

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
                         Plugin("test_plugin", "1.0.6", "=", "github.com/user/repo"))


class TestRequirements(BasePackerTest):
    def setUp(self):
        self.requirements = Requirements()

    def test_is_empty(self):
        self.assertTrue(self.requirements.is_empty())





