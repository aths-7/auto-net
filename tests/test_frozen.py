"""打包（PyInstaller）相关行为的测试：冻结模式下的自启动命令、无控制台日志。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from campusnet import autostart, logging_setup

FAKE_EXE = r"D:\apps\auto-net\campusnet.exe"


class TestFrozenAutostart(unittest.TestCase):
    def test_detects_frozen(self) -> None:
        with mock.patch.object(autostart.sys, "frozen", True, create=True):
            self.assertTrue(autostart.is_frozen())
        self.assertFalse(autostart.is_frozen())

    def test_command_points_at_exe_when_frozen(self) -> None:
        with mock.patch.object(autostart, "is_frozen", return_value=True), \
                mock.patch.object(autostart.sys, "executable", FAKE_EXE):
            cmd = autostart.command()
        # 打包后不能再出现 `-m campusnet` + PYTHONPATH 那套
        self.assertNotIn("-m campusnet", cmd)
        self.assertIn("campusnet.exe", cmd)
        self.assertIn("daemon", cmd)
        self.assertIn("--quiet", cmd)

    def test_exec_argv_when_frozen(self) -> None:
        with mock.patch.object(autostart, "is_frozen", return_value=True), \
                mock.patch.object(autostart.sys, "executable", FAKE_EXE):
            argv = autostart.exec_argv()
        self.assertEqual(argv[0], FAKE_EXE)
        self.assertEqual(argv[1:], ["daemon", "--quiet"])

    def test_command_uses_module_when_source(self) -> None:
        with mock.patch.object(autostart, "is_frozen", return_value=False):
            cmd = autostart.command()
        self.assertIn("-m campusnet", cmd)

    def test_windows_registry_value_when_frozen(self) -> None:
        if autostart.os.name != "nt":
            self.skipTest("仅 Windows")
        with mock.patch.object(autostart, "is_frozen", return_value=True), \
                mock.patch.object(autostart.sys, "executable", FAKE_EXE):
            value = autostart._win_value()
        self.assertIn("campusnet.exe", value)
        self.assertNotIn("autostart_entry.py", value)

    def test_summary_reports_frozen(self) -> None:
        with mock.patch.object(autostart, "is_frozen", return_value=True), \
                mock.patch.object(autostart.sys, "executable", FAKE_EXE):
            info = autostart.summary()
        self.assertTrue(info["frozen"])


class TestNoConsoleLogging(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.log = Path(self.tmp.name) / "t.log"

    def tearDown(self) -> None:
        logging_setup.setup(quiet=True)  # 复原全局 logger，别影响其他用例
        self.tmp.cleanup()

    def test_setup_without_stderr(self) -> None:
        """无控制台的 exe 里 sys.stderr 是 None，不能因此崩。"""
        with mock.patch("sys.stderr", None):
            logger = logging_setup.setup(quiet=False, log_file=self.log)
        self.assertEqual(len(logger.handlers), 1)  # 只剩文件 handler
        logger.info("中文日志也要能写进去")
        for handler in logger.handlers:
            handler.flush()
        self.assertIn("中文日志", self.log.read_text(encoding="utf-8"))

    def test_setup_with_stderr(self) -> None:
        logger = logging_setup.setup(quiet=False, log_file=self.log)
        self.assertEqual(len(logger.handlers), 2)  # 文件 + 控制台

    def test_quiet_only_file(self) -> None:
        logger = logging_setup.setup(quiet=True, log_file=self.log)
        self.assertEqual(len(logger.handlers), 1)


if __name__ == "__main__":
    unittest.main()
