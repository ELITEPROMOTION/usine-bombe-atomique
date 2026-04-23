from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


class ResidenceNom(str, Enum):
    IRENE = "IRENE"
    AUREA = "AUREA"
    MAGNOLIA = "MAGNOLIA"
    ASTERIA = "ASTERIA"


class StatutReservation(str, Enum):
    active = "active"
    annulee = "annulee"
    completed = "completed"


class StatutPaiement(str, Enum):
    a_venir = "a_venir"
    a_jour = "a_jour"
    retard = "retard"
    paye = "paye"


# --- Residence ---


class Residence(BaseModel):
    nom: ResidenceNom
    ville: str
    nb_lots_total: int = Field(gt=0)


# --- Client ---


class ClientCreate(BaseModel):
    nom: str = Field(min_length=1)
    prenom: str = Field(min_length=1)
    nin: str
    telephone: str = Field(min_length=1)
    email: EmailStr
    adresse: str = Field(min_length=1)

    @field_validator("nin")
    @classmethod
    def nin_must_be_18_digits(cls, v: str) -> str:
        if not (v.isdigit() and len(v) == 18):
            raise ValueError("Le NIN doit contenir exactement 18 chiffres")
        return v


class ClientUpdate(BaseModel):
    nom: Optional[str] = None
    prenom: Optional[str] = None
    nin: Optional[str] = None
    telephone: Optional[str] = None
    email: Optional[EmailStr] = None
    adresse: Optional[str] = None

    @field_validator("nin")
    @classmethod
    def nin_must_be_18_digits(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not (v.isdigit() and len(v) == 18):
            raise ValueError("Le NIN doit contenir exactement 18 chiffres")
        return v


class Client(BaseModel):
    id: int
    nom: str
    prenom: str
    nin: str
    telephone: str
    email: EmailStr
    adresse: str
    created_at: datetime


# --- Reservation ---


class ReservationCreate(BaseModel):
    client_id: int
    residence_nom: ResidenceNom
    num_lot: str = Field(min_length=1)
    prix_ht: Decimal = Field(gt=Decimal("0"))
    date_reservation: Optional[datetime] = None


class Reservation(BaseModel):
    id: int
    client_id: int
    residence_nom: ResidenceNom
    num_lot: str
    prix_ht: Decimal
    tva_19pct: Decimal
    tap_2pct: Decimal
    prix_ttc: Decimal
    date_reservation: datetime
    statut: StatutReservation


# --- Paiement ---


class Paiement(BaseModel):
    id: int
    reservation_id: int
    palier: int = Field(ge=1, le=5)
    pourcentage: int
    montant_du: Decimal
    montant_paye: Decimal
    date_echeance: datetime
    statut: StatutPaiement


class Echeancier(BaseModel):
    reservation_id: int
    paiements: list[Paiement]


# --- Reports ---


class ResidenceEncaissement(BaseModel):
    residence_nom: str
    total_encaisse: Decimal
    total_reste: Decimal


class RapportEncaissements(BaseModel):
    residences: list[ResidenceEncaissement]
    total_global_encaisse: Decimal
    total_global_reste: Decimal


# --- Health ---


class HealthResponse(BaseModel):
    status: str
    version: str
