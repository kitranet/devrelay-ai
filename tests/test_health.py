import asyncio
import httpx

from app.main import app


def test_application_startup_and_health(client):
    async def request():
        async with client.router.lifespan_context(client):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=client), base_url="http://test"
            ) as test_client:
                return await test_client.get("/health")

    response = asyncio.run(request())
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert app.title == "DevRelay AI API"


def test_mock_inference_status_is_safe(client):
    async def request():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=client), base_url="http://test"
        ) as test_client:
            return await test_client.get("/api/v1/inference/status")

    response = asyncio.run(request())
    assert response.status_code == 200
    assert response.json() == {
        "provider": "mock", "live_inference_enabled": False,
        "credentials_configured": False, "quota_status": "not_applicable",
        "quota_total": None, "quota_used": None, "quota_remaining": None,
    }
    assert "api_key" not in response.text.lower()
