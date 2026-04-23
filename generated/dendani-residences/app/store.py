from datetime import datetime
from typing import Optional

from app.models import Client, Paiement, Reservation, Residence, ResidenceNom


class InMemoryStore:
    def __init__(self) -> None:
        self._clients: dict[int, Client] = {}
        self._client_counter: int = 0

        self._reservations: dict[int, Reservation] = {}
        self._reservation_counter: int = 0

        self._paiements: dict[int, Paiement] = {}
        self._paiement_counter: int = 0

        self._residences: dict[ResidenceNom, Residence] = {
            ResidenceNom.IRENE: Residence(
                nom=ResidenceNom.IRENE, ville="Alger", nb_lots_total=120
            ),
            ResidenceNom.AUREA: Residence(
                nom=ResidenceNom.AUREA, ville="Oran", nb_lots_total=80
            ),
            ResidenceNom.MAGNOLIA: Residence(
                nom=ResidenceNom.MAGNOLIA, ville="Constantine", nb_lots_total=100
            ),
            ResidenceNom.ASTERIA: Residence(
                nom=ResidenceNom.ASTERIA, ville="Annaba", nb_lots_total=60
            ),
        }

    # --- Residences ---

    def get_all_residences(self) -> list[Residence]:
        return list(self._residences.values())

    def get_residence(self, nom: ResidenceNom) -> Optional[Residence]:
        return self._residences.get(nom)

    # --- Clients ---

    def create_client(self, client: Client) -> Client:
        self._client_counter += 1
        client = client.model_copy(update={"id": self._client_counter})
        self._clients[self._client_counter] = client
        return client

    def get_all_clients(self) -> list[Client]:
        return list(self._clients.values())

    def get_client(self, client_id: int) -> Optional[Client]:
        return self._clients.get(client_id)

    def update_client(self, client_id: int, updated: Client) -> Optional[Client]:
        if client_id not in self._clients:
            return None
        self._clients[client_id] = updated
        return updated

    def delete_client(self, client_id: int) -> bool:
        if client_id not in self._clients:
            return False
        del self._clients[client_id]
        return True

    def next_client_id(self) -> int:
        return self._client_counter + 1

    # --- Reservations ---

    def create_reservation(self, reservation: Reservation) -> Reservation:
        self._reservation_counter += 1
        reservation = reservation.model_copy(
            update={"id": self._reservation_counter}
        )
        self._reservations[self._reservation_counter] = reservation
        return reservation

    def get_reservation(self, reservation_id: int) -> Optional[Reservation]:
        return self._reservations.get(reservation_id)

    def next_reservation_id(self) -> int:
        return self._reservation_counter + 1

    # --- Paiements ---

    def create_paiement(self, paiement: Paiement) -> Paiement:
        self._paiement_counter += 1
        paiement = paiement.model_copy(
            update={"id": self._paiement_counter}
        )
        self._paiements[self._paiement_counter] = paiement
        return paiement

    def get_paiement(self, paiement_id: int) -> Optional[Paiement]:
        return self._paiements.get(paiement_id)

    def update_paiement(self, paiement_id: int, updated: Paiement) -> Optional[Paiement]:
        if paiement_id not in self._paiements:
            return None
        self._paiements[paiement_id] = updated
        return updated

    def get_paiements_by_reservation(
        self, reservation_id: int
    ) -> list[Paiement]:
        return [
            p
            for p in self._paiements.values()
            if p.reservation_id == reservation_id
        ]

    def get_all_paiements(self) -> list[Paiement]:
        return list(self._paiements.values())

    def get_all_reservations(self) -> list[Reservation]:
        return list(self._reservations.values())


store = InMemoryStore()
