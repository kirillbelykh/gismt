import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_search_by_gtin_empty():
    response = client.get("/api/v1/orders-web/search-by-gtin",
                          params={"gtin": ""})
    assert response.status_code == 400
    assert response.json()["success"] is False


def test_search_by_gtin_found(monkeypatch):
    def fake_lookup(gtin: str):
        return "Полное наименование", "Упрощенно"

    monkeypatch.setattr("app.api.v1.orders_web.nomenclature_service.lookup_by_gtin",
                       fake_lookup)

    response = client.get("/api/v1/orders-web/search-by-gtin",
                          params={"gtin": "123123123123123123132"})

    assert response.status_code == 200
    assert response.json()["success"] is True