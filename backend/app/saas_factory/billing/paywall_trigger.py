"""PaywallTrigger : 20% progression -> creation Checkout Session.

Lecture pure : ne mute pas la progression. Il ne fait QUE :
1. Verifier que `paywall_triggered_at IS NOT NULL` pour le projet
2. Lire le pricing actif (intelligence_pricings) pour le montant
3. Creer la Checkout Session via CheckoutManager (gated)

Le declenchement effectif (l'envoi du link au client) passe par 9E
HandoffOrchestrator avec action_type='payment_confirm'.
"""
from __future__ import annotations

import logging

import asyncpg

from app.saas_factory.billing.checkout import (
    CheckoutManager,
    CheckoutSession,
    CheckoutSessionRequest,
)

logger = logging.getLogger(__name__)


class PaywallNotReadyError(RuntimeError):
    """Le projet n'a pas encore atteint le seuil paywall (20%)."""


class PaywallTrigger:
    def __init__(
        self,
        pool: asyncpg.Pool,
        checkout_manager: CheckoutManager,
        *,
        success_url_template: str = "https://app.uba.studio/projects/{project_id}/paid",
        cancel_url_template: str = "https://app.uba.studio/projects/{project_id}/cancel",
    ) -> None:
        self._pool = pool
        self._checkout = checkout_manager
        self._success_template = success_url_template
        self._cancel_template = cancel_url_template

    async def maybe_trigger(self, project_id: str) -> CheckoutSession | None:
        """Cree une session Checkout SI le projet est ready, sinon retourne None.

        Conditions :
        - project_progression a au moins une ligne avec paywall_triggered_at NOT NULL
        - intelligence_pricings retourne un pricing 'ok' avec gross_price > 0
        - projects existe avec owner_email + country + locale
        - aucun payment 'pending' ou 'succeeded' actif sur ce projet
        """
        async with self._pool.acquire() as conn:
            paywall_row = await conn.fetchrow(
                """
                SELECT MIN(paywall_triggered_at) AS triggered_at
                  FROM project_progression
                 WHERE project_id = $1 AND paywall_triggered_at IS NOT NULL
                """,
                project_id,
            )
            if paywall_row is None or paywall_row["triggered_at"] is None:
                raise PaywallNotReadyError(
                    f"project {project_id} : paywall pas encore declenche",
                )

            project_row = await conn.fetchrow(
                """
                SELECT project_id::text AS pid, owner_email, country, locale, currency
                  FROM projects WHERE project_id::text = $1
                """,
                project_id,
            )
            if project_row is None:
                raise PaywallNotReadyError(
                    f"project {project_id} introuvable dans projects",
                )

            pricing_row = await conn.fetchrow(
                """
                SELECT gross_price, currency
                  FROM intelligence_pricings
                 WHERE project_id = $1 AND status = 'ok'
                 ORDER BY created_at DESC LIMIT 1
                """,
                project_id,
            )
            if pricing_row is None:
                raise PaywallNotReadyError(
                    f"aucun pricing 'ok' pour project {project_id}",
                )
            gross_price = float(pricing_row["gross_price"])
            if gross_price <= 0:
                raise PaywallNotReadyError(
                    f"gross_price={gross_price} (manual_quote ?)",
                )

            existing = await conn.fetchrow(
                """
                SELECT 1 FROM payments
                 WHERE project_id = $1 AND status IN ('pending', 'succeeded')
                """,
                project_id,
            )
            if existing is not None:
                logger.info(
                    "paywall.skipped project=%s — payment deja existant",
                    project_id,
                )
                return None

        amount_cents = int(round(gross_price * 100))
        currency = (pricing_row["currency"] or project_row["currency"]).upper()
        req = CheckoutSessionRequest(
            project_id=project_id,
            amount_cents=amount_cents,
            currency=currency,
            owner_email=project_row["owner_email"],
            country=project_row["country"],
            locale=project_row["locale"],
            success_url=self._success_template.format(project_id=project_id),
            cancel_url=self._cancel_template.format(project_id=project_id),
            description=f"UBA Studio Project {project_id[:8]}",
        )
        return await self._checkout.create_session(req)
