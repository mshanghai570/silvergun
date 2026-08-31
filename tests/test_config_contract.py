from __future__ import annotations

from pathlib import Path
import sys
import types
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class FakeScope:
    SettingsUserScope = "user"


class FakeSettings:
    def __init__(self):
        self.values = {}

    def register_group(self, *_args):
        pass

    def register_setting(self, *_args):
        pass

    def contains(self, _key):
        return True

    def get_string(self, key):
        return self.values.get(key, "")

    def get_integer(self, _key):
        return 1

    def set_string(self, key, value, _scope):
        self.values[key] = value


class LegacySettings:
    def __init__(self):
        self.values = {}

    def set_string(self, key, value):
        self.values[key] = value


class FakeProvider:
    name = "test"

    def store_data(self, _key, _value):
        return None

    def delete_data(self, _key):
        return None

    def get_data(self, _key):
        return "stored"


class FakeProviders:
    def __iter__(self):
        return iter([FakeProvider()])

    def get(self, _name):
        return FakeProvider()


binaryninja = types.ModuleType("binaryninja")
binaryninja.Settings = FakeSettings
enums = types.ModuleType("binaryninja.enums")
enums.SettingsScope = FakeScope
secrets = types.ModuleType("binaryninja.secretsprovider")
secrets.SecretsProvider = FakeProviders()
sys.modules["binaryninja"] = binaryninja
sys.modules["binaryninja.enums"] = enums
sys.modules["binaryninja.secretsprovider"] = secrets

from _silvergun import config


class ConfigTests(unittest.TestCase):
    def test_none_secret_provider_result_is_success(self):
        self.assertTrue(config.store_api_key("https://provider.test/v1", "key"))

    def test_legacy_settings_write_signature_is_supported(self):
        original = config.SETTINGS
        config.SETTINGS = LegacySettings()
        try:
            config.set_provider("https://legacy.test/v1/", "model-b")
            self.assertEqual(config.SETTINGS.values["silvergun.model"], "model-b")
        finally:
            config.SETTINGS = original

    def test_user_settings_are_normalized(self):
        config.set_provider("https://provider.test/v1/", "model-a", "/tmp/ca.pem")
        self.assertEqual(config.SETTINGS.values["silvergun.baseUrl"], "https://provider.test/v1")
        self.assertEqual(config.SETTINGS.values["silvergun.model"], "model-a")
        self.assertEqual(config.SETTINGS.values["silvergun.caBundle"], "/tmp/ca.pem")


if __name__ == "__main__":
    unittest.main()
