"""V5.2 helper : parse JSON tolerant aux strings deja decodees."""
from __future__ import annotations

import json
from typing import Any


def parse_jsonb(value: Any) -> Any:
    """asyncpg peut retourner jsonb soit en str soit en dict. Normalise."""
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        # La valeur n'est pas du JSON valide -> on la retourne telle quelle
        # (ex: ancien format, string brute legacy)
        return value
