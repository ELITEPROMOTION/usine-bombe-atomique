"""Tests Phase 9E — Handoff Orchestrator unifie."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.saas_factory.direct_links.catalog import load_default_catalog
from app.saas_factory.direct_links.direct_link_generator import IssuedLink
from app.saas_factory.direct_links.validation_engine import (
    LinkResolution,
    LinkStatus,
)
from app.saas_factory.handoff.inbox_bridge import InboxItem, LoggingInboxBridge
from app.saas_factory.handoff.orchestrator import (
    HandoffNotFoundError,
    HandoffOrchestrator,
    HandoffRequest,
    InvalidTransitionError,
    _row_to_request,
)
from app.saas_factory.handoff.state_machine import (
    TERMINAL_STATES,
    HandoffState,
    is_terminal,
    is_valid_transition,
    next_states,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _mock_pool() -> tuple[MagicMock, MagicMock]:
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
    conn.fetchrow = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.execute = AsyncMock()
    return pool, conn


def _make_orchestrator(
    *,
    inbox: LoggingInboxBridge | None = None,
) -> tuple[HandoffOrchestrator, MagicMock, MagicMock]:
    pool, conn = _mock_pool()
    cat = load_default_catalog()
    gen = MagicMock()
    val = MagicMock()
    cards = MagicMock()
    # Default: gen.issue retourne un IssuedLink simule
    gen.issue = AsyncMock(side_effect=_default_issue)
    val.validate = AsyncMock()
    val.consume = AsyncMock()
    # cards.render retourne un objet avec title/body/locale
    def _render(link, *, locale="en", context=None):
        rendered = MagicMock()
        rendered.title = f"title:{link.action_type}"
        rendered.body = f"body:{link.action_type}"
        rendered.locale = locale
        return rendered
    cards.render = MagicMock(side_effect=_render)

    orch = HandoffOrchestrator(
        pool, link_generator=gen, validation_engine=val,
        action_card_generator=cards, catalog=cat,
        inbox_bridge=inbox or LoggingInboxBridge(),
    )
    return orch, pool, conn


async def _default_issue(*, action_type, target_id, principal_id=None,
                          metadata=None, ttl=None):
    return IssuedLink(
        link_id=uuid4(),
        token="tok-" + "x" * 40,
        url=f"https://t.example/{action_type}?t=tok",
        action_type=action_type,
        target_id=target_id or "",
        expires_at=datetime.now(UTC) + (ttl or timedelta(days=3)),
        single_use=True,
    )


# ===========================================================================
# State machine
# ===========================================================================
class TestStateMachine:
    def test_terminal_states_have_no_transitions(self) -> None:
        for s in TERMINAL_STATES:
            assert next_states(s) == frozenset()

    def test_valid_transitions(self) -> None:
        assert is_valid_transition(HandoffState.REQUESTED, HandoffState.NOTIFIED)
        assert is_valid_transition(HandoffState.NOTIFIED, HandoffState.ACKNOWLEDGED)
        assert is_valid_transition(HandoffState.ACKNOWLEDGED, HandoffState.RESOLVED)
        assert is_valid_transition(HandoffState.NOTIFIED, HandoffState.ESCALATED)
        assert is_valid_transition(HandoffState.ESCALATED, HandoffState.RESOLVED)
        assert is_valid_transition(HandoffState.NOTIFIED, HandoffState.CANCELLED)

    def test_invalid_transitions(self) -> None:
        assert not is_valid_transition(HandoffState.RESOLVED, HandoffState.NOTIFIED)
        assert not is_valid_transition(HandoffState.REQUESTED, HandoffState.RESOLVED)
        assert not is_valid_transition(HandoffState.EXPIRED, HandoffState.RESOLVED)
        assert not is_valid_transition(HandoffState.CANCELLED, HandoffState.NOTIFIED)

    def test_is_terminal(self) -> None:
        assert is_terminal(HandoffState.RESOLVED)
        assert is_terminal(HandoffState.EXPIRED)
        assert is_terminal(HandoffState.CANCELLED)
        assert not is_terminal(HandoffState.REQUESTED)
        assert not is_terminal(HandoffState.NOTIFIED)


# ===========================================================================
# Inbox bridge
# ===========================================================================
class TestInboxBridge:
    @pytest.mark.asyncio
    async def test_logging_bridge_records_posts(self) -> None:
        b = LoggingInboxBridge()
        item = InboxItem(
            project_id="p", handoff_id="h", action_type="kyc_validation",
            title="t", body="b", cta_url="u", locale="en",
        )
        await b.post(item)
        assert len(b.posted) == 1
        assert b.posted[0].title == "t"


# ===========================================================================
# Orchestrator — request
# ===========================================================================
class TestOrchestratorRequest:
    @pytest.mark.asyncio
    async def test_request_creates_handoff_with_link(self) -> None:
        orch, _pool, conn = _make_orchestrator()
        new_id = uuid4()
        now = datetime.now(UTC)
        conn.fetchrow.return_value = {"handoff_id": new_id, "created_at": now}

        req = await orch.request(
            project_id="proj-1",
            action_type="kyc_validation",
            target_email="ahmed@example.com",
            locale="fr",
            payload={"service": "stripe"},
        )
        assert isinstance(req, HandoffRequest)
        assert req.handoff_id == new_id
        assert req.action_type == "kyc_validation"
        assert req.state is HandoffState.REQUESTED
        assert req.issued_token is not None
        assert req.title.startswith("title:")
        # INSERT + UPDATE direct_links target_id
        assert any("INSERT INTO handoff_requests" in c.args[0]
                   for c in conn.fetchrow.await_args_list)
        assert any("UPDATE direct_links" in c.args[0]
                   for c in conn.execute.await_args_list)

    @pytest.mark.asyncio
    async def test_request_unknown_action_type_raises(self) -> None:
        orch, *_ = _make_orchestrator()
        with pytest.raises(ValueError, match="action_type"):
            await orch.request(
                project_id="p", action_type="ghost",
                target_email="x@y.z",
            )


# ===========================================================================
# Orchestrator — transitions
# ===========================================================================
class TestOrchestratorTransitions:
    @pytest.mark.asyncio
    async def test_notify_sets_state_and_posts_inbox(self) -> None:
        bridge = LoggingInboxBridge()
        orch, _pool, conn = _make_orchestrator(inbox=bridge)
        # _transition lit l'etat actuel = REQUESTED
        conn.fetchrow.side_effect = [
            {"state": "requested"},  # pour _transition
            {                          # pour get() utilise dans notify
                "handoff_id": uuid4(), "project_id": "p",
                "action_type": "kyc_validation", "state": "notified",
                "target_email": "x@y.z", "locale": "en",
                "direct_link_id": uuid4(), "payload_json": {},
                "title": "T", "body": "B", "cta_url": "u",
                "expires_at": datetime.now(UTC) + timedelta(hours=1),
                "created_at": datetime.now(UTC),
                "resolved_at": None,
                "resolution_payload_json": {},
            },
        ]
        await orch.notify(uuid4())
        # UPDATE state = 'notified' execute
        update_call = conn.execute.await_args_list[0]
        assert "UPDATE handoff_requests" in update_call.args[0]
        # InboxItem post
        assert len(bridge.posted) == 1

    @pytest.mark.asyncio
    async def test_notify_unknown_handoff_raises(self) -> None:
        orch, _pool, conn = _make_orchestrator()
        conn.fetchrow.return_value = None
        with pytest.raises(HandoffNotFoundError):
            await orch.notify(uuid4())

    @pytest.mark.asyncio
    async def test_invalid_transition_raises(self) -> None:
        orch, _pool, conn = _make_orchestrator()
        # Etat actuel = resolved (terminal) ; tentative -> notified
        conn.fetchrow.return_value = {"state": "resolved"}
        with pytest.raises(InvalidTransitionError):
            await orch.notify(uuid4())

    @pytest.mark.asyncio
    async def test_idempotent_transition_noop(self) -> None:
        orch, _pool, conn = _make_orchestrator()
        # acknowledge utilise allow_idempotent ; etat deja acknowledged -> noop
        # Le acknowledge code path : 1er fetchrow (validate token retourne LinkResolution),
        # puis _transition fetchrow l'etat
        # Pour ce test on appelle directement _transition via notify d'un etat terminal alt :
        # On verifie l'idempotence via le path acknowledge.
        # On cree un handoff_id et on simule validate + _transition state=acknowledged
        link_target = str(uuid4())
        orch._val.validate.return_value = LinkResolution(
            status=LinkStatus.VALID,
            link_id=uuid4(), action_type="kyc_validation",
            target_id=link_target, principal_id=None, metadata={},
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            single_use=True,
        )
        conn.fetchrow.side_effect = [
            {"state": "acknowledged"},   # pour _transition (deja acknowledged)
            {                              # pour get()
                "handoff_id": UUID(link_target),
                "project_id": "p", "action_type": "kyc_validation",
                "state": "acknowledged", "target_email": "x@y.z",
                "locale": "en", "direct_link_id": uuid4(),
                "payload_json": {}, "title": "T", "body": "B",
                "cta_url": "u", "expires_at": datetime.now(UTC) + timedelta(hours=1),
                "created_at": datetime.now(UTC),
                "resolved_at": None,
                "resolution_payload_json": {},
            },
        ]
        result = await orch.acknowledge("a-token-xxxxxxxxxx")
        assert result is not None  # idempotent : on retourne l'etat actuel

    @pytest.mark.asyncio
    async def test_acknowledge_invalid_link_returns_none(self) -> None:
        orch, _pool, _conn = _make_orchestrator()
        orch._val.validate.return_value = LinkResolution(
            status=LinkStatus.EXPIRED,
            link_id=None, action_type=None, target_id=None,
            principal_id=None, metadata={}, expires_at=None, single_use=False,
        )
        result = await orch.acknowledge("expired-token")
        assert result is None

    @pytest.mark.asyncio
    async def test_acknowledge_link_without_target_returns_none(self) -> None:
        orch, _pool, _conn = _make_orchestrator()
        orch._val.validate.return_value = LinkResolution(
            status=LinkStatus.VALID,
            link_id=uuid4(), action_type="x", target_id=None,
            principal_id=None, metadata={}, expires_at=None, single_use=True,
        )
        result = await orch.acknowledge("a-token-xxxxxxxxxx")
        assert result is None

    @pytest.mark.asyncio
    async def test_acknowledge_invalid_uuid_target_returns_none(self) -> None:
        orch, _pool, _conn = _make_orchestrator()
        orch._val.validate.return_value = LinkResolution(
            status=LinkStatus.VALID,
            link_id=uuid4(), action_type="x", target_id="not-a-uuid",
            principal_id=None, metadata={}, expires_at=None, single_use=True,
        )
        result = await orch.acknowledge("a-token-xxxxxxxxxx")
        assert result is None


# ===========================================================================
# Orchestrator — resolve + callback
# ===========================================================================
class TestOrchestratorResolve:
    @pytest.mark.asyncio
    async def test_resolve_consumes_link_and_calls_callback(self) -> None:
        orch, _pool, conn = _make_orchestrator()
        target = uuid4()
        orch._val.consume.return_value = LinkResolution(
            status=LinkStatus.CONSUMED,
            link_id=uuid4(), action_type="kyc_validation",
            target_id=str(target), principal_id=None, metadata={},
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            single_use=True,
        )
        conn.fetchrow.side_effect = [
            {"action_type": "kyc_validation", "project_id": "p"},  # UPDATE RETURNING
            {                                                        # get()
                "handoff_id": target, "project_id": "p",
                "action_type": "kyc_validation", "state": "resolved",
                "target_email": "x@y.z", "locale": "en",
                "direct_link_id": uuid4(),
                "payload_json": {}, "title": "T", "body": "B",
                "cta_url": "u",
                "expires_at": datetime.now(UTC) + timedelta(hours=1),
                "created_at": datetime.now(UTC),
                "resolved_at": datetime.now(UTC),
                "resolution_payload_json": '{"who": "ahmed"}',
            },
        ]

        called: list[tuple] = []

        async def cb(handoff_id, action_type, project_id, payload):
            called.append((handoff_id, action_type, project_id, payload))

        orch.register_resolution_callback("kyc_validation", cb)
        result = await orch.resolve(
            "good-token-xxxxxxxxxx",
            resolution_payload={"who": "ahmed"},
        )
        assert result is not None
        assert result.state is HandoffState.RESOLVED
        assert len(called) == 1
        assert called[0][1] == "kyc_validation"
        assert called[0][2] == "p"

    @pytest.mark.asyncio
    async def test_resolve_callback_exception_does_not_break_resolve(self) -> None:
        orch, _pool, conn = _make_orchestrator()
        target = uuid4()
        orch._val.consume.return_value = LinkResolution(
            status=LinkStatus.CONSUMED,
            link_id=uuid4(), action_type="kyc_validation",
            target_id=str(target), principal_id=None, metadata={},
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            single_use=True,
        )
        conn.fetchrow.side_effect = [
            {"action_type": "kyc_validation", "project_id": "p"},
            {
                "handoff_id": target, "project_id": "p",
                "action_type": "kyc_validation", "state": "resolved",
                "target_email": "x@y.z", "locale": "en",
                "direct_link_id": uuid4(),
                "payload_json": {}, "title": "T", "body": "B",
                "cta_url": "u",
                "expires_at": datetime.now(UTC) + timedelta(hours=1),
                "created_at": datetime.now(UTC),
                "resolved_at": datetime.now(UTC),
                "resolution_payload_json": {},
            },
        ]

        async def bad_cb(*args):
            raise RuntimeError("callback boom")

        orch.register_resolution_callback("kyc_validation", bad_cb)
        # resolve doit completer malgre l'echec du callback
        result = await orch.resolve("good-token-xxxxxxxxxx")
        assert result is not None
        assert result.state is HandoffState.RESOLVED

    @pytest.mark.asyncio
    async def test_resolve_link_not_consumed_returns_none(self) -> None:
        orch, _pool, _conn = _make_orchestrator()
        # validate inside consume retourne CONSUMED-deja
        orch._val.consume.return_value = LinkResolution(
            status=LinkStatus.CONSUMED,
            link_id=uuid4(), action_type="x",
            target_id=None,    # pas de target
            principal_id=None, metadata={}, expires_at=None, single_use=True,
        )
        result = await orch.resolve("token-xxxxxxxxxx")
        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_unknown_handoff_returns_none(self) -> None:
        orch, _pool, conn = _make_orchestrator()
        target = uuid4()
        orch._val.consume.return_value = LinkResolution(
            status=LinkStatus.CONSUMED,
            link_id=uuid4(), action_type="kyc_validation",
            target_id=str(target), principal_id=None, metadata={},
            expires_at=None, single_use=True,
        )
        # UPDATE retourne None (handoff inexistant ou deja resolu)
        conn.fetchrow.return_value = None
        assert await orch.resolve("tok-xxxxxxxxxx") is None

    def test_register_callback_unknown_action_type_raises(self) -> None:
        orch, *_ = _make_orchestrator()
        async def cb(*a): return None
        with pytest.raises(ValueError):
            orch.register_resolution_callback("ghost_action", cb)


# ===========================================================================
# Orchestrator — escalate / cancel / tick / get
# ===========================================================================
class TestOrchestratorOps:
    @pytest.mark.asyncio
    async def test_escalate(self) -> None:
        orch, _pool, conn = _make_orchestrator()
        conn.fetchrow.return_value = {"state": "notified"}
        await orch.escalate(uuid4())
        # UPDATE state = escalated
        sql = conn.execute.await_args_list[0].args[0]
        assert "UPDATE handoff_requests" in sql
        # On verifie que le 2eme parametre (state) = 'escalated'
        assert conn.execute.await_args_list[0].args[2] == "escalated"

    @pytest.mark.asyncio
    async def test_cancel_with_reason(self) -> None:
        orch, _pool, conn = _make_orchestrator()
        conn.fetchrow.return_value = {"state": "notified"}
        await orch.cancel(uuid4(), reason="user request")
        # UPDATE applique avec extra_payload (cancel_reason dans payload_json)
        # On verifie que le SQL inclut payload_json || $3
        sql = conn.execute.await_args_list[0].args[0]
        assert "payload_json" in sql

    @pytest.mark.asyncio
    async def test_tick_returns_counts(self) -> None:
        orch, _pool, conn = _make_orchestrator()
        conn.fetch.side_effect = [
            [{"handoff_id": uuid4()}, {"handoff_id": uuid4()}],   # escalated
            [{"handoff_id": uuid4()}],                              # expired
        ]
        result = await orch.tick()
        assert result == {"escalated": 2, "expired": 1}

    @pytest.mark.asyncio
    async def test_get_unknown_raises(self) -> None:
        orch, _pool, conn = _make_orchestrator()
        conn.fetchrow.return_value = None
        with pytest.raises(HandoffNotFoundError):
            await orch.get(uuid4())

    @pytest.mark.asyncio
    async def test_get_parses_string_payloads(self) -> None:
        orch, _pool, conn = _make_orchestrator()
        new_id = uuid4()
        conn.fetchrow.return_value = {
            "handoff_id": new_id, "project_id": "p",
            "action_type": "kyc_validation", "state": "notified",
            "target_email": "x@y.z", "locale": "en",
            "direct_link_id": uuid4(),
            # payloads en string JSON (asyncpg peut les renvoyer ainsi)
            "payload_json": '{"k":"v"}',
            "title": "T", "body": "B", "cta_url": "u",
            "expires_at": datetime.now(UTC) + timedelta(hours=1),
            "created_at": datetime.now(UTC),
            "resolved_at": None,
            "resolution_payload_json": '{"r":"v"}',
        }
        req = await orch.get(new_id)
        assert req.payload == {"k": "v"}
        assert req.resolution_payload == {"r": "v"}


def test_row_to_request_helper_with_dict_payloads() -> None:
    new_id = uuid4()
    link_id = uuid4()
    row = {
        "handoff_id": new_id, "project_id": "p",
        "action_type": "kyc_validation", "state": "resolved",
        "target_email": "x@y.z", "locale": "fr",
        "direct_link_id": link_id,
        "payload_json": {"a": 1},   # dict directement
        "title": "T", "body": "B", "cta_url": "u",
        "expires_at": datetime.now(UTC),
        "created_at": datetime.now(UTC),
        "resolved_at": datetime.now(UTC),
        "resolution_payload_json": {"r": 1},
    }
    r = _row_to_request(row)
    assert r.payload == {"a": 1}
    assert r.resolution_payload == {"r": 1}
    assert r.state is HandoffState.RESOLVED
    assert r.issued_token is None


# ===========================================================================
# Couverture supplementaire : edge cases
# ===========================================================================
class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_acknowledge_handoff_not_found_returns_none(self) -> None:
        """Le link est valide mais le handoff a ete supprime entre-temps."""
        orch, _pool, conn = _make_orchestrator()
        orch._val.validate.return_value = LinkResolution(
            status=LinkStatus.VALID,
            link_id=uuid4(), action_type="kyc_validation",
            target_id=str(uuid4()), principal_id=None, metadata={},
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            single_use=True,
        )
        # _transition cherche le handoff -> None -> HandoffNotFoundError
        conn.fetchrow.return_value = None
        result = await orch.acknowledge("a-token-xxxxxxxxxx")
        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_invalid_uuid_target_returns_none(self) -> None:
        orch, _pool, _conn = _make_orchestrator()
        orch._val.consume.return_value = LinkResolution(
            status=LinkStatus.CONSUMED,
            link_id=uuid4(), action_type="kyc_validation",
            target_id="not-a-uuid",  # invalid UUID
            principal_id=None, metadata={}, expires_at=None, single_use=True,
        )
        result = await orch.resolve("good-token-xxxxxxxxxx")
        assert result is None

    @pytest.mark.asyncio
    async def test_notify_when_already_notified_raises_invalid(self) -> None:
        """notify() sans allow_idempotent : si deja notified -> InvalidTransitionError."""
        orch, _pool, conn = _make_orchestrator()
        conn.fetchrow.return_value = {"state": "notified"}
        with pytest.raises(InvalidTransitionError):
            await orch.notify(uuid4())

    @pytest.mark.asyncio
    async def test_transition_idempotent_advanced_state_silent_noop(self) -> None:
        """acknowledge() sur un handoff REQUESTED (notify pas encore appele).

        Transition REQUESTED -> ACKNOWLEDGED n'est pas valide (REQUESTED va
        vers NOTIFIED). allow_idempotent=True dans acknowledge -> noop silent
        plutot que InvalidTransitionError.
        """
        orch, _pool, conn = _make_orchestrator()
        target = uuid4()
        orch._val.validate.return_value = LinkResolution(
            status=LinkStatus.VALID,
            link_id=uuid4(), action_type="kyc_validation",
            target_id=str(target), principal_id=None, metadata={},
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            single_use=True,
        )
        conn.fetchrow.side_effect = [
            {"state": "requested"},   # _transition trouve REQUESTED
            {                            # get() apres
                "handoff_id": target, "project_id": "p",
                "action_type": "kyc_validation", "state": "requested",
                "target_email": "x@y.z", "locale": "en",
                "direct_link_id": uuid4(), "payload_json": {},
                "title": "T", "body": "B", "cta_url": "u",
                "expires_at": datetime.now(UTC) + timedelta(hours=1),
                "created_at": datetime.now(UTC),
                "resolved_at": None,
                "resolution_payload_json": {},
            },
        ]
        result = await orch.acknowledge("a-token-xxxxxxxxxx")
        # Pas d'erreur : noop silencieux. result = state actuel (requested)
        assert result is not None
        assert result.state is HandoffState.REQUESTED
