"""Tests E2E Phase 9R — pipelines transverses.

Strategie : pas de DB reelle (PostgreSQL-specifique : JSONB,
gen_random_uuid, INTERVAL...). Pas de SQLite shim non plus (rewrite trop
lourd). On utilise des **side_effects sequences** sur le mock asyncpg pour
verifier que les **contracts entre modules** tiennent.

Objectif : prouver que les modules s'enchainent correctement :
- Les outputs d'un engine alimentent l'input du suivant
- Les UUIDs/IDs propagent
- Les exceptions remontent en preservant le contexte
- Les flags de gating (live, payment_id) sont effectivement honores

Ces tests sont COMPLEMENTAIRES aux tests unitaires (491 deja en place,
98% coverage). Ils ne dupliquent pas la couverture mais valident les
**boundaries**.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

# 9D
from app.saas_factory.ai_orchestrator.cost_guard import CostGuard, CostLimits
from app.saas_factory.ai_orchestrator.loop_detector import LoopDetector
from app.saas_factory.ai_orchestrator.providers import StubAIProvider
from app.saas_factory.ai_orchestrator.qualification_adapter import (
    RouterBackedClaudeProvider,
)
from app.saas_factory.ai_orchestrator.router import AIRouter, RoutingPolicy

# 9H
from app.saas_factory.billing.checkout import (
    CheckoutManager,
)
from app.saas_factory.billing.invoice_generator import InvoiceGenerator
from app.saas_factory.billing.paywall_trigger import PaywallTrigger
from app.saas_factory.billing.stripe_client import StubStripeClient
from app.saas_factory.billing.webhook_handler import WebhookHandler

# 9F
from app.saas_factory.client_onboarding.defaults import (
    sample_branding,
    sample_identity,
    sample_pack_selection,
    sample_project_brief,
    sample_review,
    sample_technical,
)
from app.saas_factory.client_onboarding.onboarding_engine import (
    ONBOARDING_STEP_ORDER,
    ClientStepKey,
    OnboardingEngine,
)
from app.saas_factory.client_onboarding.project_factory import ProjectFactory

# 9A
from app.saas_factory.direct_links.action_card_generator import ActionCardGenerator
from app.saas_factory.direct_links.catalog import load_default_catalog
from app.saas_factory.direct_links.direct_link_generator import (
    DirectLinkGenerator,
    hash_token,
)
from app.saas_factory.direct_links.validation_engine import (
    ValidationEngine,
)

# 9E
from app.saas_factory.handoff.orchestrator import HandoffOrchestrator
from app.saas_factory.handoff.state_machine import HandoffState

# 9C
from app.saas_factory.intelligence.assembly_engine import (
    AssemblyEngine,
    AssemblyOutcome,
)
from app.saas_factory.intelligence.packs.catalog import load_default_pack_catalog
from app.saas_factory.intelligence.pricing_engine import (
    PricingEngine,
    PricingStatus,
)
from app.saas_factory.intelligence.progression_engine import (
    PROGRESSION_PHASES,
    ProgressionEngine,
)
from app.saas_factory.intelligence.qualification_engine import (
    QualificationConfidence,
    QualificationEngine,
)

# 9-BOOT
from app.saas_factory.self_bootstrap.account_creator_orchestrator import (
    AccountCreatorOrchestrator,
    StepKind,
)
from app.saas_factory.self_bootstrap.handoff_kyc_orchestrator import (
    HandoffKycOrchestrator,
)
from app.saas_factory.self_bootstrap.mandate_engine import MandateEngine
from app.saas_factory.self_bootstrap.service_priority_queue import ServiceTier


# ===========================================================================
# Helpers
# ===========================================================================
def _fake_pool(side_effects: list | None = None) -> tuple[MagicMock, MagicMock]:
    """Build a fake asyncpg pool. fetchrow.side_effect is sequenced."""
    pool = MagicMock()
    conn = MagicMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.acquire = MagicMock(return_value=cm)
    tx_cm = MagicMock()
    tx_cm.__aenter__ = AsyncMock(return_value=None)
    tx_cm.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=tx_cm)
    conn.fetchrow = AsyncMock(side_effect=side_effects)
    conn.fetch = AsyncMock(return_value=[])
    conn.execute = AsyncMock(return_value="UPDATE 1")
    conn.executemany = AsyncMock()
    return pool, conn


def _signed_webhook(payload: str, secret: str = "whsec_e2e_test") -> str:
    ts = int(time.time())
    sig = hmac.new(
        secret.encode(), f"{ts}.{payload}".encode(), hashlib.sha256,
    ).hexdigest()
    return f"t={ts},v1={sig}"


# ===========================================================================
# E2E-1 : Onboarding → ProjectFactory → QualificationTrigger
# ===========================================================================
class TestE2E_OnboardingToQualification:
    """Le 6-step onboarding 9F submit → projects row + appel
    QualificationTrigger avec bons args (cdc_text + project_id + meta).
    """

    @pytest.mark.asyncio
    async def test_full_onboarding_to_qualification_trigger(self) -> None:
        # === Setup ===
        sid = uuid4()
        proj_id = uuid4()
        completed: list[str] = []
        partial: dict = {}
        payloads = [
            (ClientStepKey.IDENTITY, sample_identity()),
            (ClientStepKey.PROJECT_BRIEF, sample_project_brief()),
            (ClientStepKey.PACK_SELECTION, sample_pack_selection()),
            (ClientStepKey.BRANDING, sample_branding()),
            (ClientStepKey.TECHNICAL_PREFERENCES, sample_technical()),
            (ClientStepKey.REVIEW_SUBMIT, sample_review()),
        ]

        # Programme fetchrow : start + 6 saves (1 each) + final factory (2 fetchrow)
        seq: list = [
            # 1. start session
            {"session_id": sid, "started_at": datetime.now(UTC)},
        ]
        # 6 saves
        for step, _ in payloads:
            snapshot = {
                "session_id": sid, "current_step": step.value,
                "completed_steps": list(completed),
                "partial_data_json": json.dumps(partial, default=str),
                "status": "in_progress",
                "started_at": datetime.now(UTC),
                "submitted_at": None, "project_id": None,
            }
            seq.append(snapshot)
            completed.append(step.value)
            partial[step.value] = payloads[
                next(i for i, (s, _) in enumerate(payloads) if s == step)
            ][1].model_dump(mode="json")
        # 7. ProjectFactory.create_from_session : get_state + INSERT projects
        seq.append({
            "session_id": sid, "current_step": ClientStepKey.REVIEW_SUBMIT.value,
            "completed_steps": [s.value for s in ONBOARDING_STEP_ORDER],
            "partial_data_json": partial,
            "status": "in_progress",
            "started_at": datetime.now(UTC),
            "submitted_at": None, "project_id": None,
        })
        seq.append({"project_id": proj_id, "created_at": datetime.now(UTC)})

        pool, conn = _fake_pool(seq)
        engine = OnboardingEngine(pool, enabled_packs=("saas_small",))

        # Capture trigger calls
        trigger_calls: list[dict] = []

        class _CapturingTrigger:
            async def __call__(self, *, project_id, cdc_text, owner_email, metadata):
                trigger_calls.append({
                    "project_id": project_id,
                    "cdc_text": cdc_text,
                    "owner_email": owner_email,
                    "metadata": metadata,
                })

        factory = ProjectFactory(pool, engine, qualification_trigger=_CapturingTrigger())

        # === Run pipeline ===
        await engine.start()
        for step, payload in payloads:
            await engine.save_step(sid, step, payload.model_dump(mode="json"))
        record = await factory.create_from_session(sid)

        # === Verify contract ===
        assert record.project_id == proj_id
        assert len(trigger_calls) == 1
        call = trigger_calls[0]
        # Le project_id passe au trigger doit etre celui retourne par le factory
        assert call["project_id"] == proj_id
        # Le cdc_text doit etre la description du brief (input du QualificationEngine)
        assert call["cdc_text"] == sample_project_brief().description
        assert call["owner_email"] == sample_identity().email
        # Le metadata contient le pack_id_hint qui sera utilise par AssemblyEngine
        assert call["metadata"]["pack_id_hint"] == "saas_small"
        assert call["metadata"]["country"] == "FR"
        assert call["metadata"]["locale"] == "fr"


# ===========================================================================
# E2E-2 : QualificationEngine + RouterBackedClaudeProvider (9C + 9D)
# ===========================================================================
class TestE2E_QualificationViaRouter:
    """Le RouterBackedClaudeProvider satisfait le Protocol ClaudeProvider de
    9C en routant via AIRouter 9D. Pipeline : adapter -> router -> stub
    provider -> JSON parsing -> Pydantic schema.
    """

    @pytest.mark.asyncio
    async def test_qualification_via_router_with_stub_provider(self) -> None:
        # Stub AIProvider qui retourne un JSON Claude-shaped
        canned_json = json.dumps({
            "pack_hint": "saas_small",
            "facets": {
                "complexity": 3, "domain_specialty": 2, "urgency": 2,
                "support_level": 2, "compliance_overhead": 1,
                "i18n_locales": 2, "integration_count": 3,
                "design_intensity": 3, "data_migration": 1,
                "training_included": 2, "sla_tier": 1,
                "scaling_factor": 2, "geographic_spread": 1,
                "audit_required": 0, "post_launch_window": 3,
            },
            "detected_domain": "saas-internal",
            "detected_locales": ["en", "fr"],
            "risks": [],
            "confidence": "high",
            "rationale": "Brief decrit un dashboard interne SaaS classique avec 2 langues.",
        })
        stub_provider = StubAIProvider(
            canned_text=canned_json, provider_name="claude",
            provider_for_pricing="claude",
        )

        # Build AIRouter with weight=100 on stub
        pool, conn = _fake_pool()
        cg = CostGuard(pool, limits=CostLimits(
            per_call_cap_usd=10.0, per_project_cap_usd=100.0, daily_cap_usd=1000.0,
        ))
        ld = LoopDetector(threshold=10)
        dlog = MagicMock()
        dlog.log = AsyncMock(return_value=uuid4())
        router = AIRouter(
            pool, {"claude": stub_provider},
            cost_guard=cg, loop_detector=ld, decisions_logger=dlog,
            policy=RoutingPolicy(weights={"claude": 100}, fallback_order=("claude",),
                                  base_delay_s=0.0),
        )

        # Adapt to 9C ClaudeProvider Protocol
        adapter = RouterBackedClaudeProvider(router, project_id="proj-e2e")

        # 9C QualificationEngine using the adapter
        cat = load_default_pack_catalog()
        # fetchrow for INSERT intelligence_qualifications RETURNING
        new_qid = uuid4()
        conn.fetchrow = AsyncMock(return_value={
            "qualification_id": new_qid, "created_at": datetime.now(UTC),
        })

        engine = QualificationEngine(pool, cat, adapter)
        result = await engine.qualify(
            project_id="proj-e2e",
            cdc_text="Build a small SaaS dashboard with auth and billing",
        )

        # === Verify contract ===
        assert result.qualification_id == new_qid
        assert result.pack_hint == "saas_small"
        assert result.confidence is QualificationConfidence.HIGH
        assert result.facets.complexity == 3
        # Le router a ete appele 1 fois
        assert stub_provider.call_count == 1
        # DecisionsLogger a recu 1 log
        dlog.log.assert_awaited_once()
        log_kw = dlog.log.await_args.kwargs
        assert log_kw["status"] == "ok"
        assert log_kw["project_id"] == "proj-e2e"


# ===========================================================================
# E2E-3 : Pricing → Assembly → Progression (chaine interne 9C)
# ===========================================================================
class TestE2E_PricingAssemblyProgression:
    """A partir d'une qualification donnee, run pricing -> assembly -> progression
    init. Verifier que les phase_weights de l'assembly sont compatibles avec
    ProgressionEngine.initialize.
    """

    @pytest.mark.asyncio
    async def test_pricing_assembly_progression_chain(self) -> None:
        from app.saas_factory.intelligence.pricing_engine import ProjectFacets
        from app.saas_factory.intelligence.qualification_engine import Qualification

        cat = load_default_pack_catalog()
        facets = ProjectFacets(
            complexity=3, domain_specialty=2, urgency=2, support_level=2,
            compliance_overhead=1, i18n_locales=2, integration_count=3,
            design_intensity=3, data_migration=1, training_included=2,
            sla_tier=1, scaling_factor=2, geographic_spread=1,
            audit_required=0, post_launch_window=3,
        )
        # Pricing
        pool, conn = _fake_pool()
        new_pricing = uuid4()
        new_assembly = uuid4()
        conn.fetchrow = AsyncMock(side_effect=[
            {"pricing_id": new_pricing},        # PricingEngine._persist
            {"assembly_id": new_assembly,        # AssemblyEngine.assemble
             "created_at": datetime.now(UTC)},
        ])

        pricing_engine = PricingEngine(pool, cat)
        weights = {k: 1.0 for k in facets.model_fields}
        pricing = await pricing_engine.quote(
            project_id="proj-e2e", pack_id="saas_small",
            facets=facets, coefficients=weights,
        )
        assert pricing.status is PricingStatus.OK
        assert pricing.pricing_id == new_pricing

        # Assembly
        qualification = Qualification(
            qualification_id=uuid4(), project_id="proj-e2e",
            pack_hint="saas_small", facets=facets,
            detected_domain="saas-internal",
            detected_locales=("en", "fr"), risks=(),
            confidence=QualificationConfidence.HIGH,
            rationale="x", cdc_text_hash="0" * 64,
            created_at=datetime.now(UTC),
        )
        assembly_engine = AssemblyEngine(pool, cat)
        assembled = await assembly_engine.assemble(
            qualification=qualification, pricing=pricing,
        )
        assert assembled.outcome is AssemblyOutcome.AUTO
        assert assembled.assembly_id == new_assembly
        # phase_weights doit sommer a 100 (validation pack catalog)
        assert sum(assembled.phase_weights.values()) == 100

        # Progression init avec les weights de l'assembly
        progression_engine = ProgressionEngine(pool)
        await progression_engine.initialize(
            project_id="proj-e2e",
            pack_phase_weights=assembled.phase_weights,
        )
        # executemany appele avec 6 lignes (1 par phase)
        call = conn.executemany.await_args_list[0]
        rows = call.args[1]
        assert len(rows) == 6
        # Les phases inserees correspondent aux 6 canoniques
        inserted_phases = {r[1] for r in rows}
        assert inserted_phases == {p.value for p in PROGRESSION_PHASES}


# ===========================================================================
# E2E-4 : Progression → Paywall → Checkout
# ===========================================================================
class TestE2E_ProgressionPaywallCheckout:
    """Quand la progression atteint 20%, PaywallTrigger.maybe_trigger() doit
    creer un Checkout via le Stub Stripe. Verif: le bon montant + currency
    sont passes a Stripe.
    """

    @pytest.mark.asyncio
    async def test_paywall_at_20pct_creates_checkout(self) -> None:
        # Programme fetchrow:
        # 1. PaywallTrigger checks paywall_triggered_at
        # 2. PaywallTrigger reads project row
        # 3. PaywallTrigger reads pricing
        # 4. PaywallTrigger checks existing payment (None)
        # 5. CheckoutManager INSERT payments
        seq = [
            {"triggered_at": datetime.now(UTC) - timedelta(minutes=5)},
            {"pid": "proj-uuid", "owner_email": "ahmed@example.com",
             "country": "FR", "locale": "fr", "currency": "EUR"},
            {"gross_price": 5400.00, "currency": "EUR"},  # SaaS small + small VAT
            None,  # no existing payment
            {"payment_id": uuid4(), "created_at": datetime.now(UTC)},
        ]
        pool, conn = _fake_pool(seq)

        # Stub Stripe : retourne une session valide
        stub = StubStripeClient()
        stub.set_response(
            "POST", "/checkout/sessions",
            json_body={
                "id": "cs_e2e_paywall",
                "url": "https://checkout.stripe.com/c/cs_e2e_paywall",
            },
        )
        cm = CheckoutManager(pool, stub)
        pt = PaywallTrigger(pool, cm)
        result = await pt.maybe_trigger("proj-uuid")
        assert result is not None
        assert result.stripe_session_id == "cs_e2e_paywall"
        # Le montant TTC = 5400 EUR = 540000 cents
        assert result.amount_cents == 540000
        assert result.currency == "EUR"
        # Stripe a recu un POST /checkout/sessions avec line_items
        assert stub.calls[0][0:2] == ("POST", "/checkout/sessions")
        form = stub.calls[0][2]
        assert form["line_items"][0]["price_data"]["unit_amount"] == 540000

    @pytest.mark.asyncio
    async def test_paywall_blocked_when_existing_payment_exists(self) -> None:
        seq = [
            {"triggered_at": datetime.now(UTC)},
            {"pid": "p1", "owner_email": "x@y.com", "country": "FR",
             "locale": "fr", "currency": "EUR"},
            {"gross_price": 100.0, "currency": "EUR"},
            {"1": 1},  # existing payment found
        ]
        pool, _ = _fake_pool(seq)
        cm = CheckoutManager(pool, StubStripeClient())
        result = await PaywallTrigger(pool, cm).maybe_trigger("p1")
        assert result is None  # short-circuited


# ===========================================================================
# E2E-4 : Webhook → Mark paid → Invoice
# ===========================================================================
class TestE2E_WebhookToInvoice:
    """Stripe webhook checkout.session.completed → marks payment paid →
    invoke project_resume_callback → callback creates invoice.
    Aussi : verifie qu'AUCUN terme AI ne fuit dans l'HTML invoice rendu.
    """

    @pytest.mark.asyncio
    async def test_webhook_marks_paid_and_invoice_no_leak(self) -> None:
        secret = "whsec_e2e_test"
        uba_payment = uuid4()

        # Programme fetchrow :
        # 1. WebhookHandler INSERT webhook_events RETURNING (idempotent ok)
        # 2. (apres dispatch _mark_paid) — pas de fetchrow direct
        # Pour le callback resume -> InvoiceGenerator :
        # 3. SELECT payments
        # 4. SELECT MAX seq invoices
        # 5. INSERT invoices RETURNING
        new_invoice = uuid4()
        seq_calls = [
            # webhook insert
            {"event_db_id": uuid4()},
            # invoice generator (3 fetchrow internes)
            {
                "project_id": "p-e2e", "amount_cents": 12000,
                "currency": "EUR", "owner_email": "client@example.com",
                "country": "FR", "locale": "fr", "status": "succeeded",
            },
            {"next_seq": 1},
            {"invoice_id": new_invoice, "issued_at": datetime.now(UTC)},
        ]
        pool, conn = _fake_pool(seq_calls)

        invoice_gen = InvoiceGenerator(pool)
        captured_invoice: list = []

        async def resume_callback(payment_id, project_id, amount_cents, currency):
            # Ce callback recoit les params du webhook et cree l'invoice
            inv = await invoice_gen.issue_for_payment(
                payment_id=payment_id, description=f"UBA Studio ({project_id})",
            )
            captured_invoice.append(inv)

        handler = WebhookHandler(
            pool, webhook_secret=secret, project_resume=resume_callback,
        )

        # Build a signed Stripe webhook payload
        payload = json.dumps({
            "id": "evt_e2e_1",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_e2e_1",
                    "payment_intent": "pi_e2e_1",
                    "amount_total": 12000,
                    "currency": "eur",
                    "metadata": {
                        "uba_payment_id": str(uba_payment),
                        "uba_project_id": "p-e2e",
                    },
                },
            },
        })
        sig = _signed_webhook(payload, secret)

        evt = await handler.process(raw_payload=payload, signature_header=sig)
        assert evt.payment_id == uba_payment
        assert len(captured_invoice) == 1
        invoice = captured_invoice[0]
        assert invoice.invoice_id == new_invoice
        # Verif HT/TTC : 12000 TTC FR (20% VAT) -> 10000 HT + 2000 VAT
        assert invoice.gross_amount_cents == 12000
        assert invoice.net_amount_cents == 10000
        assert invoice.vat_amount_cents == 2000

        # === No AI leak in rendered HTML ===
        html = InvoiceGenerator.render_html(invoice)
        forbidden = ("claude", "perplexity", "manus", "tokens_in", "cost_usd",
                     "ai_decisions", "anthropic", "provider")
        for term in forbidden:
            assert term.lower() not in html.lower(), f"LEAK: {term}"


# ===========================================================================
# E2E-5 : Service activation (9-BOOT account_creator orchestrator)
# ===========================================================================
class TestE2E_ServiceActivation:
    """AccountCreatorOrchestrator.plan_all chains :
    ServicePriorityQueue → MandateEngine.issue (8 mandats) →
    HandoffKycOrchestrator.open_handoff (3 handoffs : 2 tier 2 + 1 tier 3).
    """

    @pytest.mark.asyncio
    async def test_account_creator_plan_chains_correctly(self) -> None:
        # Programme fetchrow par service (dans l'ordre de plan_all loop) :
        #   tier 1 (5 services) : [last_chain_hash, mandate_insert] x 5
        #   tier 2/3 (3 services) : [last_chain_hash, mandate_insert, handoff_insert] x 3
        seq: list = []
        for _ in range(5):  # 5 tier 1 services : 2 fetchrow chacun (mandate)
            seq.append({"chain_hash": "0" * 64})
            seq.append({"mandate_id": uuid4(), "signed_at": datetime.now(UTC)})
        for _ in range(3):  # 3 tier 2/3 services : 2 fetchrow mandate + 1 handoff
            seq.append({"chain_hash": "0" * 64})
            seq.append({"mandate_id": uuid4(), "signed_at": datetime.now(UTC)})
            seq.append({"handoff_id": uuid4()})

        pool, conn = _fake_pool(seq)
        mandate_engine = MandateEngine(pool)
        handoff = HandoffKycOrchestrator(pool, base_url="https://app.uba.studio")

        orchestrator = AccountCreatorOrchestrator(
            pool, mandate_engine, handoff,
        )
        plan = await orchestrator.plan_all(
            principal_id="ahmed",
            target_email="ahmed@example.com",
            locale="en",
        )

        # === Verify ===
        # 8 services au total (5 tier 1 + 2 tier 2 + 1 tier 3)
        assert len(plan.steps) == 8
        # Tier order strict
        tiers = [int(s.tier) for s in plan.steps]
        assert tiers == sorted(tiers), "tier order broken"
        # 5 tier 1 = AUTOMATED, sans handoff
        tier1 = [s for s in plan.steps if s.tier == ServiceTier.NO_KYC]
        assert len(tier1) == 5
        for s in tier1:
            assert s.kind is StepKind.AUTOMATED
            assert s.handoff_id is None
        # 2 tier 2 = REQUIRES_CARD avec handoff
        tier2 = [s for s in plan.steps if s.tier == ServiceTier.CARD_REQUIRED]
        assert len(tier2) == 2
        for s in tier2:
            assert s.kind is StepKind.REQUIRES_CARD
            assert s.handoff_id is not None
        # 1 tier 3 = REQUIRES_KYC avec handoff (stripe)
        tier3 = [s for s in plan.steps if s.tier == ServiceTier.KYC_BUSINESS]
        assert len(tier3) == 1
        assert tier3[0].kind is StepKind.REQUIRES_KYC
        assert tier3[0].service == "stripe"
        # Mandates emis : 8 (1 par service)
        assert all(s.mandate_id is not None for s in plan.steps)


# ===========================================================================
# E2E-6 : Direct link → Handoff resolve flow (9A + 9E)
# ===========================================================================
class TestE2E_DirectLinkHandoffFlow:
    """HandoffOrchestrator.request → DirectLinkGenerator.issue token →
    user clicks → ValidationEngine.validate → acknowledge →
    user completes → ValidationEngine.consume → resolve → callback fires.
    """

    @pytest.mark.asyncio
    async def test_direct_link_handoff_full_resolve(self) -> None:
        cat = load_default_catalog()
        callbacks_fired: list = []

        async def cb(handoff_id, action_type, project_id, payload):
            callbacks_fired.append({
                "handoff_id": handoff_id,
                "action_type": action_type,
                "project_id": project_id,
                "payload": payload,
            })

        # === Step 1 : request handoff ===
        # Mocks separes par etape pour clarte
        request_seq = [
            # DirectLinkGenerator.issue : INSERT direct_links
            {"link_id": uuid4()},
            # HandoffOrchestrator INSERT handoff_requests
            {"handoff_id": uuid4(), "created_at": datetime.now(UTC)},
        ]
        pool, conn = _fake_pool(request_seq)
        gen = DirectLinkGenerator(pool, cat, base_url="https://app.uba.studio")
        val = ValidationEngine(pool, cat)
        cards = ActionCardGenerator(cat)

        orch = HandoffOrchestrator(
            pool, link_generator=gen, validation_engine=val,
            action_card_generator=cards, catalog=cat,
        )
        orch.register_resolution_callback("payment_confirm", cb)

        request = await orch.request(
            project_id="proj-X",
            action_type="payment_confirm",
            target_email="user@example.com",
            locale="fr",
            payload={"project_name": "MonSaaS"},
        )
        token = request.issued_token
        assert token is not None
        assert request.state is HandoffState.REQUESTED

        # === Step 2 : user clicks → validate (acknowledge) ===
        # Validation seq :
        # 1. validate (SELECT direct_links by hash)
        # 2. audit insert (no fetchrow)
        # 3. _transition fetchrow current state
        # 4. UPDATE handoff_requests
        # 5. get() for return value
        ack_seq = [
            # validate : SELECT direct_links
            {
                "link_id": request.direct_link_id,
                "action_type": "payment_confirm",
                "target_id": str(request.handoff_id),
                "principal_id": None, "metadata_json": {},
                "single_use": True,
                "expires_at": datetime.now(UTC) + timedelta(hours=1),
                "consumed_at": None, "revoked_at": None,
            },
            # _transition : SELECT current state
            {"state": "requested"},
            # get() : SELECT handoff_requests
            {
                "handoff_id": request.handoff_id, "project_id": "proj-X",
                "action_type": "payment_confirm", "state": "acknowledged",
                "target_email": "user@example.com", "locale": "fr",
                "direct_link_id": request.direct_link_id,
                "payload_json": {"project_name": "MonSaaS"},
                "title": "x", "body": "y", "cta_url": request.cta_url,
                "expires_at": datetime.now(UTC) + timedelta(hours=1),
                "created_at": datetime.now(UTC),
                "resolved_at": None,
                "resolution_payload_json": {},
            },
        ]
        # On reutilise le meme pool, side_effect doit etre re-set.
        conn.fetchrow.side_effect = ack_seq
        # Mais REQUESTED -> ACKNOWLEDGED n'est pas valide directement (on
        # passe par NOTIFIED). allow_idempotent=True dans acknowledge() fait
        # un noop silent. On observe que la fonction retourne le state actuel.
        ack_result = await orch.acknowledge(token)
        assert ack_result is not None  # idempotent silent noop OK

        # === Step 3 : user completes → consume → resolve callback fires ===
        # consume seq :
        # 1. UPDATE direct_links RETURNING (consume)
        # 2. INSERT direct_links_audit (no fetchrow)
        # 3. UPDATE handoff_requests SET state=resolved RETURNING
        # 4. get() for return value
        resolve_seq = [
            # consume : UPDATE direct_links RETURNING
            {
                "link_id": request.direct_link_id,
                "action_type": "payment_confirm",
                "target_id": str(request.handoff_id),
                "principal_id": None, "metadata_json": {},
                "single_use": True,
                "expires_at": datetime.now(UTC) + timedelta(hours=1),
            },
            # UPDATE handoff_requests RETURNING
            {"action_type": "payment_confirm", "project_id": "proj-X"},
            # get() : SELECT handoff_requests
            {
                "handoff_id": request.handoff_id, "project_id": "proj-X",
                "action_type": "payment_confirm", "state": "resolved",
                "target_email": "user@example.com", "locale": "fr",
                "direct_link_id": request.direct_link_id,
                "payload_json": {}, "title": "x", "body": "y",
                "cta_url": request.cta_url,
                "expires_at": datetime.now(UTC) + timedelta(hours=1),
                "created_at": datetime.now(UTC),
                "resolved_at": datetime.now(UTC),
                "resolution_payload_json": {"paid": True},
            },
        ]
        conn.fetchrow.side_effect = resolve_seq
        resolved = await orch.resolve(token, resolution_payload={"paid": True})
        assert resolved is not None
        assert resolved.state is HandoffState.RESOLVED
        # Callback a ete appele exactement 1 fois avec les bons args
        assert len(callbacks_fired) == 1
        c = callbacks_fired[0]
        assert c["handoff_id"] == request.handoff_id
        assert c["action_type"] == "payment_confirm"
        assert c["project_id"] == "proj-X"
        assert c["payload"] == {"paid": True}


# ===========================================================================
# Smoke : le hash_token est deterministe et compatible cross-engine
# ===========================================================================
def test_hash_token_contract_stability() -> None:
    """Le hash_token de 9A doit etre stable (sha256). Si quelqu'un change
    l'algo, tous les tokens existants en DB deviennent unreachable.
    """
    h = hash_token("known-token-abc")
    expected = hashlib.sha256(b"known-token-abc").hexdigest()
    assert h == expected
    assert len(h) == 64
