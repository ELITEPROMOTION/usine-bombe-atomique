from fastapi.testclient import TestClient


def test_create_client(client: TestClient, client_payload: dict) -> None:
    resp = client.post("/clients", json=client_payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["nom"] == "Dendani"
    assert data["prenom"] == "Karim"
    assert data["nin"] == "123456789012345678"
    assert "id" in data
    assert "created_at" in data


def test_create_client_nin_invalide(client: TestClient, client_payload: dict) -> None:
    client_payload["nin"] = "123"
    resp = client.post("/clients", json=client_payload)
    assert resp.status_code == 422


def test_list_clients_vide(client: TestClient) -> None:
    resp = client.get("/clients")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_clients(client: TestClient, created_client: dict) -> None:
    resp = client.get("/clients")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_get_client(client: TestClient, created_client: dict) -> None:
    cid = created_client["id"]
    resp = client.get(f"/clients/{cid}")
    assert resp.status_code == 200
    assert resp.json()["id"] == cid


def test_get_client_inexistant(client: TestClient) -> None:
    resp = client.get("/clients/9999")
    assert resp.status_code == 404


def test_update_client(client: TestClient, created_client: dict) -> None:
    cid = created_client["id"]
    resp = client.put(f"/clients/{cid}", json={"nom": "NouveauNom"})
    assert resp.status_code == 200
    assert resp.json()["nom"] == "NouveauNom"
    assert resp.json()["prenom"] == "Karim"


def test_update_client_inexistant(client: TestClient) -> None:
    resp = client.put("/clients/9999", json={"nom": "X"})
    assert resp.status_code == 404


def test_delete_client(client: TestClient, created_client: dict) -> None:
    cid = created_client["id"]
    resp = client.delete(f"/clients/{cid}")
    assert resp.status_code == 204
    resp2 = client.get(f"/clients/{cid}")
    assert resp2.status_code == 404


def test_delete_client_inexistant(client: TestClient) -> None:
    resp = client.delete("/clients/9999")
    assert resp.status_code == 404
