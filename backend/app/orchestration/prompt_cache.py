"""Upgrade 17 - Prompt cache Anthropic.

Wrapper minimaliste autour de l'API Anthropic pour activer le prompt caching :
on envoie le system prompt comme un bloc cacheable via cache_control, et
on reutilise le prefix a chaque appel. Economie moyenne ~50% tokens in.

Le cache n'est pas gere par nous : il est pris en charge cote serveur
Anthropic (beta/stable selon modele). Ici on fournit l'en-tete + le
formatage du system prompt.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def build_cached_system(base_prompt: str, shared_suffix: str | None = None) -> list[dict[str, Any]]:
    """Fabrique un system prompt en blocs cacheables.

    Le premier bloc (`base_prompt`) est marque cache_control=ephemeral pour
    etre reutilise entre appels identiques. Le suffixe, s'il change, n'est
    pas cache.
    """
    blocks: list[dict[str, Any]] = [
        {"type": "text", "text": base_prompt,
         "cache_control": {"type": "ephemeral"}},
    ]
    if shared_suffix:
        blocks.append({"type": "text", "text": shared_suffix})
    return blocks


async def create_message_with_cache(
    client: Any, *, model: str, max_tokens: int,
    system_blocks: list[dict[str, Any]],
    messages: list[dict[str, Any]],
) -> Any:
    """Appelle Anthropic en envoyant le system prompt sous forme de blocs
    cacheables. Retourne la reponse brute + les stats de cache si dispo."""
    msg = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_blocks,
        messages=messages,
    )
    usage = getattr(msg, "usage", None)
    cache_read = getattr(usage, "cache_read_input_tokens", 0) if usage else 0
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) if usage else 0
    logger.info("anthropic cache: read=%s write=%s tokens", cache_read, cache_write)
    return msg


def estimate_savings(tokens_in: int, cache_read: int) -> float:
    """Retourne le % de tokens input epargnes par le cache."""
    if tokens_in <= 0:
        return 0.0
    return (cache_read / tokens_in) * 100 if cache_read else 0.0
