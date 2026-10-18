import importlib
import importlib.util
import sys

_source = None
_filename = None


def configure(source, filename):
    global _source, _filename
    _source = source
    _filename = filename


def load_pyco():
    if "pyco" in sys.modules:
        return sys.modules["pyco"]
    if _source is None:
        return importlib.import_module("pyco")

    compiled = compile(_source, _filename, "exec")
    spec = importlib.util.spec_from_loader("pyco", loader=None, origin=_filename)
    module = importlib.util.module_from_spec(spec)
    module.__file__ = _filename
    sys.modules["pyco"] = module
    try:
        exec(compiled, module.__dict__)
    except BaseException:
        del sys.modules["pyco"]
        raise
    return module
