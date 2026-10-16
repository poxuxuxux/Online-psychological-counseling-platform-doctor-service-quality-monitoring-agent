"""Keep legacy empty-catalog fixtures independent of installed production packages.

Delivered-package integration tests explicitly pass their real package directory.
Tests of configured packages may override this environment variable themselves.
"""

import pytest


@pytest.fixture(autouse=True)
def isolated_default_metric_directory(tmp_path, monkeypatch):
    directory = tmp_path / "empty-metric-packages"
    directory.mkdir()
    monkeypatch.setenv("METRIC_SKILLS_DIR", str(directory))
