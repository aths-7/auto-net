"""配置模块测试。"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from campusnet import config as config_mod


class TestConfig(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "config.json"
        self._old_home = os.environ.get("CAMPUSNET_HOME")
        os.environ["CAMPUSNET_HOME"] = self.tmp.name

    def tearDown(self) -> None:
        if self._old_home is None:
            os.environ.pop("CAMPUSNET_HOME", None)
        else:
            os.environ["CAMPUSNET_HOME"] = self._old_home
        self.tmp.cleanup()

    def test_deep_merge_keeps_defaults(self) -> None:
        merged = config_mod.deep_merge(config_mod.DEFAULT_CONFIG, {"srun": {"ac_id": "9"}})
        self.assertEqual(merged["srun"]["ac_id"], "9")
        self.assertEqual(merged["srun"]["n"], "200")  # 默认值得保留
        self.assertEqual(merged["daemon"]["interval"], 30)

    def test_save_and_load_roundtrip(self) -> None:
        cfg = config_mod.deep_merge(config_mod.DEFAULT_CONFIG, {})
        cfg.update({"username": "20230001", "password": "secret", "portal": "http://10.1.2.3"})
        config_mod.save(cfg, self.path)

        loaded = config_mod.load(self.path)
        self.assertEqual(loaded["username"], "20230001")
        self.assertEqual(loaded["portal"], "http://10.1.2.3")
        # 缺省的嵌套键要被补回来
        self.assertIn("check", loaded)
        self.assertTrue(loaded["check"]["urls"])

    def test_missing_file_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            config_mod.load(self.path)

    def test_env_password_overrides(self) -> None:
        config_mod.save({"username": "u", "password": "fromfile"}, self.path)
        os.environ["CAMPUSNET_PASSWORD"] = "fromenv"
        try:
            self.assertEqual(config_mod.load(self.path)["password"], "fromenv")
        finally:
            os.environ.pop("CAMPUSNET_PASSWORD", None)

    def test_mask(self) -> None:
        self.assertEqual(config_mod.mask(""), "(未设置)")
        self.assertEqual(config_mod.mask("ab"), "**")
        self.assertEqual(config_mod.mask("abcdef"), "a****f")

    def test_saved_file_is_utf8_json(self) -> None:
        config_mod.save({"username": "张三"}, self.path)
        raw = self.path.read_text(encoding="utf-8")
        self.assertIn("张三", raw)
        json.loads(raw)

    def test_app_dir_respects_env(self) -> None:
        self.assertEqual(config_mod.app_dir(), Path(self.tmp.name))


if __name__ == "__main__":
    unittest.main()
