import asyncio

import httpx

from app.core.config import Settings
from app.main import create_app


def test_analysis_api_returns_structured_traceable_data(sample_repository):
    application = create_app(Settings(_env_file=None, authorized_repositories={"sample": sample_repository}))

    async def request():
        async with application.router.lifespan_context(application):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=application), base_url="http://test"
            ) as test_client:
                return await test_client.post(
                    "/api/v1/repositories/analyze", json={"repository_id": "sample"}
                )

    response = asyncio.run(request())
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["repository_id"] == "sample"
    assert any(item["path"] == "package/core.py" for item in body["modules"])
    assert any(item["source"]["path"] == "package/core.py" for item in body["classes"])
    assert "snapshot_id" not in body and "content_hashes" not in body
    assert "C:\\" not in response.text


def test_analysis_api_rejects_path_as_repository_identifier(sample_repository):
    application = create_app(Settings(_env_file=None, authorized_repositories={"sample": sample_repository}))

    async def request():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application), base_url="http://test"
        ) as test_client:
            return await test_client.post(
                "/api/v1/repositories/analyze", json={"repository_id": "..\\outside"}
            )

    response = asyncio.run(request())
    assert response.status_code == 422


def test_analysis_api_hides_unconfigured_repository_ids(sample_repository):
    application = create_app(Settings(_env_file=None, authorized_repositories={"sample": sample_repository}))

    async def request():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application), base_url="http://test"
        ) as test_client:
            return await test_client.post(
                "/api/v1/repositories/analyze", json={"repository_id": "unlisted"}
            )

    response = asyncio.run(request())
    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "repository_not_found", "message": "Repository is not configured for analysis."}
    }
