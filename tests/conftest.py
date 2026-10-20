import httpx
import pytest

from app.main import create_app


@pytest.fixture
def client():
    return create_app()
