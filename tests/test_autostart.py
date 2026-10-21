"""自启动开关 & CLI 的测试（不动真实系统配置）。"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from campusnet import autostart, cli, config as config_mod


class TestAutostart(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("CAMPUSNET_HOME")
        os.environ["CAMPUSNET_HOME"] = self.tmp.name
        os.environ["CAMPUSNET_AUTOSTART_NAME"] = "CampusNetAutoLoginTest"

    def tearDown(self) -> None:
        os.environ.pop("CAMPUSNET_AUTOSTART_NAME", None)
        if self._old is None:
            os.environ.pop("CAMPUSNET_HOME", None)
        else:
            os.environ["CAMPUSNET_HOME"] = self._old
        self.tmp.cleanup()

    def test_command_contains_module(self) -> None:
        self.assertIn("-m campusnet daemon", autostart.command())

    def test_pkg_parent_points_at_repo_root(self) -> None:
        parent = Path(autostart.pkg_parent())
        self.assertTrue((parent / "campusnet" / "__init__.py").exists())

    def test_dry_run_enable(self) -> None:
        ok, detail = autostart.enable(dry_run=True)
        self.assertTrue(ok)
        self.assertTrue(detail)
        # dry-run 不能真的写入
        enabled, _ = autostart.is_enabled()
        self.assertFalse(enabled)

    def test_status_returns_tuple(self) -> None:
        enabled, detail = autostart.is_enabled()
        self.assertIsInstance(enabled, bool)
        self.assertIsInstance(detail, str)

    def test_summary_shape(self) -> None:
        info = autostart.summary()
        for key in ("platform", "enabled", "detail", "command"):
            self.assertIn(key, info)


class TestCli(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg_path = Path(self.tmp.name) / "config.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_init_with_flags(self) -> None:
        code = cli.main([
            "-c", str(self.cfg_path), "init", "-y",
            "--provider", "srun", "--portal", "http://10.0.0.55/",
            "--username", "20230001", "--password", "pw",
        ])
        self.assertEqual(code, 0)
        cfg = config_mod.load(self.cfg_path)
        self.assertEqual(cfg["provider"], "srun")
        self.assertEqual(cfg["portal"], "http://10.0.0.55")  # 尾部斜杠被规整
        self.assertEqual(cfg["username"], "20230001")

    def test_init_rejects_unknown_provider(self) -> None:
        with self.assertRaises(SystemExit):
            cli.main(["-c", str(self.cfg_path), "init", "-y", "--provider", "unknown"])

    def test_config_get_set(self) -> None:
        config_mod.save({"username": "u", "password": "secret"}, self.cfg_path)
        code = cli.main(["-c", str(self.cfg_path), "config", "daemon.interval", "60"])
        self.assertEqual(code, 0)
        self.assertEqual(config_mod.load(self.cfg_path)["daemon"]["interval"], 60)

        code = cli.main(["-c", str(self.cfg_path), "config", "username"])
        self.assertEqual(code, 0)

    def test_validate_catches_missing_fields(self) -> None:
        problems = cli._validate({"provider": "srun"}, raise_error=False)
        self.assertTrue(any("portal" in p for p in problems))
        self.assertTrue(any("username" in p for p in problems))
        self.assertTrue(any("password" in p for p in problems))

    def test_redact_hides_password(self) -> None:
        red = cli._redact({"password": "secret123", "nested": {"password": "abc"}})
        self.assertNotIn("secret123", str(red))
        self.assertEqual(red["password"], "s*******3")
        self.assertEqual(red["nested"]["password"], "a*c")

    def test_status_reports_the_config_actually_used(self) -> None:
        import io
        from contextlib import redirect_stdout
        from unittest import mock

        config_mod.save({"username": "u", "password": "p", "portal": "http://10.1.1.1"}, self.cfg_path)
        buf = io.StringIO()
        with mock.patch("campusnet.cli.netcheck.is_online", return_value=(True, [])), \
                redirect_stdout(buf):
            cli.main(["-c", str(self.cfg_path), "status"])
        # 回归：曾经这里硬编码打印默认路径，-c 被无视
        self.assertIn(str(self.cfg_path), buf.getvalue())

    def test_doctor_without_config_does_not_crash(self) -> None:
        import io
        from contextlib import redirect_stdout
        from unittest import mock

        buf = io.StringIO()
        with mock.patch("campusnet.cli.netcheck.is_online", return_value=(False, [])), \
                redirect_stdout(buf):
            code = cli.main(["-c", str(self.cfg_path), "doctor"])
        output = buf.getvalue()
        self.assertEqual(code, 1)  # 有配置问题 -> 1，但不应该是异常
        self.assertIn("不存在", output)

    def test_doctor_with_complete_config(self) -> None:
        import io
        from contextlib import redirect_stdout
        from unittest import mock

        config_mod.save({"username": "u", "password": "p", "portal": "http://10.1.1.1",
                         "provider": "srun"}, self.cfg_path)
        buf = io.StringIO()
        with mock.patch("campusnet.cli.netcheck.is_online", return_value=(True, [])), \
                redirect_stdout(buf):
            code = cli.main(["-c", str(self.cfg_path), "doctor"])
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
