import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class StaticAssetTests(unittest.TestCase):
    def test_static_imports_exports_ids_and_assets(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_static.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
