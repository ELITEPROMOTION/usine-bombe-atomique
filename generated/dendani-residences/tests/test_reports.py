from decimal import Decimal

from fastapi.testclient import TestClient


def test_rapport_encaissements_vide(client: TestClient) -> None:
    resp = client.get("/reports/encaissements")
    assert resp.status_code == 200
    data = resp.json()
    assert data["residences"] == []
    assert data["total_global_encaisse"] == "0.00"
    assert data["total_global_reste"] == "0.00"


def test_rapport_encaissements_sans_paiement(
    client: TestClient, created_reservation: dict
) -> None:
    resp = client.get("/reports/encaissements")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["residences"]) == 1
    residence = data["residences"][0]
    assert residence["residence_nom"] == "IRENE"
    assert residence["total_encaisse"] == "0.00"
    assert float(residence["total_reste"]) > 0


def test_rapport_encaissements_avec_paiements(
    client: TestClient, created_reservation: dict
) -> None:
    rid = created_reservation["id"]
    echeancier = client.get(f"/reservations/{rid}/echeancier").json()

    premier = echeancier["paiements"][0]
    pid = premier["id"]
    montant_du = premier["montant_du"]
    client.post(f"/paiements/{pid}/regler")

    resp = client.get("/reports/encaissements")
    assert resp.status_code == 200
    data = resp.json()
    residence = data["residences"][0]
    assert residence["total_encaisse"] == montant_du
    assert float(data["total_global_encaisse"]) > 0


def test_rapport_agregation_multiple_reservations(
    client: TestClient,
    created_client: dict,
) -> None:
    for lot in ["A-101", "A-102"]:
        payload = {
            "client_id": created_client["id"],
            "residence_nom": "AUREA",
            "num_lot": lot,
            "prix_ht": "5000000.00",
        }
        client.post("/reservations", json=payload)

    resp = client.get("/reports/encaissements")
    assert resp.status_code == 200
    data = resp.json()
    aurea = next(
        (r for r in data["residences"] if r["residence_nom"] == "AUREA"), None
    )
    assert aurea is not None
    ttc_une = Decimal("5000000") * Decimal("1.21")
    total_attendu = ttc_une * 2
    assert Decimal(aurea["total_reste"]) == total_attendu
