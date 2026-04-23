from fastapi.testclient import TestClient


def test_create_reservation_genere_5_paiements(
    client: TestClient, created_reservation: dict
) -> None:
    rid = created_reservation["id"]
    resp = client.get(f"/reservations/{rid}/echeancier")
    assert resp.status_code == 200
    data = resp.json()
    assert data["reservation_id"] == rid
    assert len(data["paiements"]) == 5


def test_create_reservation_calcul_fiscal(
    client: TestClient, reservation_payload: dict
) -> None:
    resp = client.post("/reservations", json=reservation_payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["tva_19pct"] == "1900000.00"
    assert data["tap_2pct"] == "200000.00"
    assert data["prix_ttc"] == "12100000.00"


def test_create_reservation_client_inexistant(client: TestClient) -> None:
    payload = {
        "client_id": 9999,
        "residence_nom": "AUREA",
        "num_lot": "B-202",
        "prix_ht": "5000000.00",
    }
    resp = client.post("/reservations", json=payload)
    assert resp.status_code == 404


def test_get_reservation(client: TestClient, created_reservation: dict) -> None:
    rid = created_reservation["id"]
    resp = client.get(f"/reservations/{rid}")
    assert resp.status_code == 200
    assert resp.json()["id"] == rid


def test_get_reservation_inexistante(client: TestClient) -> None:
    resp = client.get("/reservations/9999")
    assert resp.status_code == 404


def test_echeancier_pourcentages(
    client: TestClient, created_reservation: dict
) -> None:
    rid = created_reservation["id"]
    resp = client.get(f"/reservations/{rid}/echeancier")
    data = resp.json()
    pourcentages = [p["pourcentage"] for p in data["paiements"]]
    assert pourcentages == [20, 15, 35, 25, 5]


def test_echeancier_reservation_inexistante(client: TestClient) -> None:
    resp = client.get("/reservations/9999/echeancier")
    assert resp.status_code == 404
