"""Thin setup.py shim.

All metadata lives in pyproject.toml. This file exists for two narrow
reasons that need imperative Python code:

1. **Platform-specific wheel tag.** pylibobs bundles the libobs shared
   library (`.dll` / `.so` / `.dylib`) plus its plugin DLLs and data
   files, so a single universal `py3-none-any` wheel is wrong — the
   binaries differ per OS / architecture. Overriding
   `Distribution.has_ext_modules()` to return True makes setuptools
   tag the wheel with the host's platform string (e.g. `win_amd64`,
   `manylinux_2_31_x86_64`, `macosx_11_0_arm64`).

2. **Python-version-agnostic tag.** The Python code itself is pure
   Python (no compiled C extension specific to one CPython ABI), so
   we want the wheel tagged `py3-none-<platform>` instead of the
   default `cpXY-cpXY-<platform>`. Overriding `bdist_wheel.get_tag()`
   does this.

Together these produce wheels like:
    pylibobs-0.1.0-py3-none-win_amd64.whl
    pylibobs-0.1.0-py3-none-manylinux_2_31_x86_64.whl
    pylibobs-0.1.0-py3-none-macosx_11_0_arm64.whl
"""
from setuptools import setup
from setuptools.dist import Distribution

try:                              # setuptools >= 70
    from setuptools.command.bdist_wheel import bdist_wheel as _BdistWheel
except ImportError:               # older setuptools
    from wheel.bdist_wheel import bdist_wheel as _BdistWheel  # type: ignore


class BinaryDistribution(Distribution):
    """Force a platform-specific wheel because we bundle libobs binaries."""
    def has_ext_modules(self):
        return True
    def is_pure(self):
        return False


class BdistWheel(_BdistWheel):
    """Re-tag as `py3-none-<plat>` (pure-Python code + platform-specific data)."""
    def finalize_options(self):
        super().finalize_options()
        self.root_is_pure = False
    def get_tag(self):
        _py, _abi, plat = super().get_tag()
        return "py3", "none", plat


setup(
    distclass=BinaryDistribution,
    cmdclass={"bdist_wheel": BdistWheel},
)
