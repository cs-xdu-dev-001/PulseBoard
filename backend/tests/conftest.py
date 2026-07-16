import shutil
import uuid
from pathlib import Path

import pytest


@pytest.fixture
def tmp_path():
    workspace = Path.cwd().resolve()
    root = workspace / "tmp-pytest-fixtures"
    root.mkdir(exist_ok=True)
    path = root / f"test-{uuid.uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
        try:
            root.rmdir()
        except OSError:
            pass
