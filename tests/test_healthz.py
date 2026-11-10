import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check_endpoint(async_client: AsyncClient):
    """Test that /healthz endpoint returns 200 OK and unified envelope format."""
    response = await async_client.get("/healthz")
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True
    assert data["data"]["status"] == "healthy"
    assert "environment" in data["data"]
    assert "version" in data["data"]
    assert "timestamp" in data["data"]


@pytest.mark.asyncio
async def test_root_endpoint(async_client: AsyncClient):
    """Test that / endpoint returns API information."""
    response = await async_client.get("/")
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True
    assert data["data"]["docsUrl"] == "/docs"
