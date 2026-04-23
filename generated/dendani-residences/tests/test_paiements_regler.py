from fastapi.testclient import TestClient


def test_regler_paiement(
    client: TestClient, created_reservation: dict
) -> None:
    rid = created_reservation["id"]
    echeancier = client.get(f"/reservations/{rid}/echeancier").json()
    premier_paiement = echeancier["paiements"][0]
    pid = premier_paiement["id"]

    resp = client.post(f"/paiements/{pid}/regler")
    assert resp.status_code == 200
    data = resp.json()
    assert data["statut"] == "paye"
    assert data["montant_paye"] == data["montant_du"]


def test_regler_paiement_deja_paye(
    client: TestClient, created_reservation: dict
) -> None:
    rid = created_reservation["id"]
    echeancier = client.get(f"/reservations/{rid}/echeancier").json()
    pid = echeancier["paiements"][0]["id"]

    client.post(f"/paiements/{pid}/regler")
    resp = client.post(f"/paiements/{pid}/regler")
    assert resp.status_code == 400


def test_regler_paiement_inexistant(client: TestClient) -> None:
    resp = client.post("/paiements/9999/regler")
    assert resp.status_code == 404


def test_regler_tous_les_paliers(
    client: TestClient, created_reservation: dict
) -> None:
    rid = created_reservation["id"]
    echeancier = client.get(f"/reservations/{rid}/echeancier").json()
    for paiement in echeancier["paiements"]:
        pid = paiement["id"]
        resp = client.post(f"/paiements/{pid}/regler")
        assert resp.status_code == 200
        assert resp.json()["statut"] == "paye"
