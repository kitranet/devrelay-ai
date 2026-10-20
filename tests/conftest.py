import shutil
from pathlib import Path

import pytest

from app.main import create_app


@pytest.fixture
def client():
    return create_app()


@pytest.fixture
def sample_repository(tmp_path: Path) -> Path:
    source = Path(__file__).parent / "fixtures" / "sample_repo"
    destination = tmp_path / "sample-repository"
    shutil.copytree(source, destination)
    return destination
