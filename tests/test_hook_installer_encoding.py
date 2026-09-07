from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


class HookInstallerEncodingTests(unittest.TestCase):
    def test_installers_use_utf8_with_legacy_stdio(self):
        # Reproduce a non-UTF-8 Windows pipe even on macOS/Linux.
        environment = {**os.environ, "PYTHONIOENCODING": "cp1252",
                       "PYTHONUTF8": "0", "PYTHONDONTWRITEBYTECODE": "1"}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "취업"
            (root / ".chwippohaja").mkdir(parents=True)
            (root / ".chwippohaja/workspace.json").write_text("{}", encoding="utf-8")
            for kind in ("essay", "research"):
                command = [sys.executable, str(SCRIPTS / f"install_{kind}_hooks.py")]
                with self.subTest(kind=kind, operation="dry-run"):
                    result = subprocess.run(command + [str(root), "--dry-run"],
                                            capture_output=True, encoding="utf-8", env=environment)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    spec = json.loads(result.stdout)["hooks"]["Stop"][-1]["hooks"][0]
                    self.assertIn("완료 조건 검사 중", spec["statusMessage"])
                    self.assertFalse((root / ".codex/hooks.json").exists())
                with self.subTest(kind=kind, operation="install"):
                    result = subprocess.run(command + [str(root)], capture_output=True,
                                            encoding="utf-8", env=environment)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    destination = root / ".codex/hooks.json"
                    self.assertEqual(Path(result.stdout.strip()), destination.resolve())
                    self.assertIn("hooks", json.loads(destination.read_text(encoding="utf-8")))
                    destination.unlink()
                with self.subTest(kind=kind, operation="error"):
                    result = subprocess.run(command + [str(root / "없는경로")],
                                            capture_output=True, encoding="utf-8", env=environment)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("워크스페이스", result.stderr)
                    self.assertNotIn("charmap", result.stderr)


if __name__ == "__main__":
    unittest.main()
