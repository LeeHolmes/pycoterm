import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


class PycoLoaderTests(unittest.TestCase):
    def setUp(self):
        source = Path(__file__).parents[1] / "app/src/main/python/pyco_loader.py"
        spec = importlib.util.spec_from_file_location("pyco_loader", source)
        self.loader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.loader)
        self.modules = patch.dict(sys.modules)
        self.modules.start()
        sys.modules.pop("pyco", None)
        self.addCleanup(self.modules.stop)

    def test_bundled_module_is_used_without_download(self):
        bundled = types.ModuleType("pyco")
        with patch.object(self.loader.importlib, "import_module", return_value=bundled) as load:
            self.assertIs(self.loader.load_pyco(), bundled)
        load.assert_called_once_with("pyco")

    def test_downloaded_source_is_loaded_instead_of_bundle(self):
        self.loader.configure("value = 42", "private/pyco.py")
        module = self.loader.load_pyco()
        self.assertEqual(module.value, 42)
        self.assertEqual(module.__file__, "private/pyco.py")
        self.assertIs(module, sys.modules["pyco"])

    def test_update_does_not_replace_running_module(self):
        self.loader.configure("value = 1", "private/pyco.py")
        running = self.loader.load_pyco()
        self.loader.configure("value = 2", "private/pyco.py")
        self.assertIs(self.loader.load_pyco(), running)
        self.assertEqual(running.value, 1)

    def test_restart_loads_latest_source_without_stale_bytecode(self):
        self.loader.configure("value = 1", "private/pyco.py")
        self.loader.load_pyco()
        del sys.modules["pyco"]
        self.loader.configure("value = 2", "private/pyco.py")
        self.assertEqual(self.loader.load_pyco().value, 2)

    def test_syntax_error_does_not_install_module(self):
        self.loader.configure("value =", "private/pyco.py")
        with self.assertRaises(SyntaxError):
            self.loader.load_pyco()
        self.assertNotIn("pyco", sys.modules)

    def test_execution_failure_does_not_leave_partial_module(self):
        self.loader.configure("raise RuntimeError('broken update')", "private/pyco.py")
        with self.assertRaisesRegex(RuntimeError, "broken update"):
            self.loader.load_pyco()
        self.assertNotIn("pyco", sys.modules)


if __name__ == "__main__":
    unittest.main()
