import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.store import InMemoryStore, store


@pytest.fixture(autouse=True)
def reset_store() -> None:
    """Remet a zero le store en memoire avant chaque test."""
    store._clients.clear()
    store._client_counter = 0
    store._reservations.clear()
    store._reservation_counter = 0
    store._paiements.clear()
    store._paiement_counter = 0


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def client_payload() -> dict:
    return {
        "nom": "Dendani",
        "prenom": "Karim",
        "nin": "123456789012345678",
        "telephone": "0555000000",
        "email": "karim.dendani@example.com",
        "adresse": "12 Rue des Roses, Alger",
    }


@pytest.fixture
def created_client(client: TestClient, client_payload: dict) -> dict:
    resp = client.post("/clients", json=client_payload)
    assert resp.status_code == 201
    return resp.json()


@pytest.fixture
def reservation_payload(created_client: dict) -> dict:
    return {
        "client_id": created_client["id"],
        "residence_nom": "IRENE",
        "num_lot": "A-101",
        "prix_ht": "10000000.00",
    }


@pytest.fixture
def created_reservation(client: TestClient, reservation_payload: dict) -> dict:
    resp = client.post("/reservations", json=reservation_payload)
    assert resp.status_code == 201
    return resp.json()
