import os
import shutil
import socket
from ipaddress import ip_address
from pathlib import Path

import httpx
import pytest

# Override developer and CI shell configuration before importing app.main.
# This affects only the pytest process; it never reads or edits the root .env.
_SAFE_TEST_ENV = {
    "NEBIUS_API_KEY": "",
    "INFERENCE_PROVIDER": "mock",
    "NEBIUS_BASE_URL": "https://api.tokenfactory.test.nebius.com/v1/",
    "NEBIUS_MODEL": "nvidia/Nemotron-3_5-Lightning",
    "NEBIUS_PLANNING_DISABLE_THINKING": "false",
    "NEBIUS_LIVE_INFERENCE_ENABLED": "false",
    "NEBIUS_TOTAL_INFERENCE_QUOTA": "0",
    "NEBIUS_QUOTA_DB_PATH": ".pytest-tmp/inference-quota.sqlite3",
    "AUTHORIZED_REPOSITORIES": "{}",
    "ENABLE_LOCAL_REVIEWS": "false",
    "ENABLE_ISOLATED_RUNTIME_VALIDATION": "false",
}
os.environ.update(_SAFE_TEST_ENV)

from app.core.config import get_settings
from app.main import create_app


@pytest.fixture(autouse=True)
def isolate_settings_and_external_network(monkeypatch):
    for name, value in _SAFE_TEST_ENV.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()

    original_async_http = httpx.AsyncHTTPTransport.handle_async_request
    original_sync_http = httpx.HTTPTransport.handle_request
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def block_external_host(host: str) -> None:
        if host.lower() == "localhost":
            return
        try:
            if ip_address(host).is_loopback:
                return
        except ValueError:
            pass
        raise AssertionError("Pytest network safety guard blocked an unmocked outbound request.")

    async def guarded_async_http(transport, request):
        block_external_host(request.url.host)
        return await original_async_http(transport, request)

    def guarded_sync_http(transport, request):
        block_external_host(request.url.host)
        return original_sync_http(transport, request)

    def guarded_connect(sock, address):
        if isinstance(address, tuple) and address and isinstance(address[0], str):
            block_external_host(address[0])
        return original_connect(sock, address)

    def guarded_connect_ex(sock, address):
        if isinstance(address, tuple) and address and isinstance(address[0], str):
            block_external_host(address[0])
        return original_connect_ex(sock, address)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", guarded_async_http)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", guarded_sync_http)
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    yield
    get_settings.cache_clear()


@pytest.fixture
def client():
    return create_app(get_settings())


@pytest.fixture
def sample_repository(tmp_path: Path) -> Path:
    source = Path(__file__).parent / "fixtures" / "sample_repo"
    destination = tmp_path / "sample-repository"
    shutil.copytree(source, destination)
    return destination
