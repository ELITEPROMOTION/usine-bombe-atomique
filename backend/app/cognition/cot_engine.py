"""V5.4 - Chain-of-Thought engine (5 modes).

Zero-shot / Few-shot / Program-aided / Self-consistent / Structured.
Implementation deterministe (pas d'appel LLM direct ; on fournit decider).
"""
from __future__ import annotations

import ast
import logging
import re
import statistics
from typing import Any, Callable

from app.cognition.reasoning_trace_models import ChainTrace, ReasoningStep

logger = logging.getLogger(__name__)


# Template d'etapes pour structured mode
STRUCTURED_SECTIONS = [
    "Given", "Assumptions", "Reasoning", "Verification", "Conclusion",
]


def zero_shot_cot(
    problem: str, *, decider: Callable[[str], list[str]] | None = None,
) -> ChainTrace:
    """Let's think step by step. Decider retourne list[str] etapes."""
    if decider is None:
        decider = _default_step_decider
    steps_text = decider(f"Let's think step by step: {problem}")
    steps = [ReasoningStep(index=i, content=s, confidence=0.75)
             for i, s in enumerate(steps_text)]
    final = steps_text[-1] if steps_text else "n/a"
    return ChainTrace(
        mode="zero_shot", steps=steps,
        intermediate_conclusions=steps_text[:-1] if len(steps_text) > 1 else [],
        final_answer=final, confidence=0.75,
    )


def few_shot_cot(
    problem: str, examples: list[dict[str, str]], *,
    decider: Callable[[str], list[str]] | None = None,
) -> ChainTrace:
    """Few-shot : utilise examples (Q/A pairs) pour guider."""
    if decider is None:
        decider = _default_step_decider
    context = "\n".join(f"Q: {e['question']}\nA: {e['answer']}"
                        for e in examples[:5])
    steps_text = decider(f"{context}\n\nQ: {problem}\nA:")
    steps = [ReasoningStep(index=i, content=s, confidence=0.80)
             for i, s in enumerate(steps_text)]
    final = steps_text[-1] if steps_text else "n/a"
    return ChainTrace(
        mode="few_shot", steps=steps,
        intermediate_conclusions=steps_text[:-1],
        final_answer=final, confidence=0.80,
    )


def program_aided_cot(problem: str) -> ChainTrace:
    """Program-Aided : extrait une expression numerique et l'evalue safe."""
    steps_text: list[str] = []
    final = ""
    confidence = 0.50
    m = re.search(r"(?:=|calcul[eé]+|equals?)\s*([-+*/().\s0-9]+)", problem, re.I)
    if m:
        expr = m.group(1).strip()
        try:
            node = ast.parse(expr, mode="eval")
            result = eval(compile(node, "<pa_cot>", "eval"),   # noqa: S307
                          {"__builtins__": {}}, {})
            steps_text = [
                f"Extracted expression: {expr}",
                f"Evaluated: {expr} = {result}",
            ]
            final = str(result)
            confidence = 0.95
        except Exception as exc:
            steps_text = [f"Expression extracted but eval failed: {exc}"]
            final = "eval_error"
    else:
        steps_text = ["No arithmetic expression detected"]
        final = "no_numeric"
    steps = [ReasoningStep(index=i, content=s, confidence=confidence)
             for i, s in enumerate(steps_text)]
    return ChainTrace(
        mode="program_aided", steps=steps,
        intermediate_conclusions=steps_text[:-1],
        final_answer=final, confidence=confidence,
        verification_trace={"method": "python_eval"},
    )


def self_consistent_cot(
    problem: str, n_samples: int = 5, *,
    decider: Callable[[str, float], list[str]] | None = None,
) -> ChainTrace:
    """Execute N chains avec temperature variable + vote majoritaire."""
    if decider is None:
        decider = _default_temperature_decider
    answers: list[str] = []
    all_chains: list[list[str]] = []
    for i in range(n_samples):
        temperature = 0.3 + (0.6 * i / max(1, n_samples - 1))
        chain = decider(problem, temperature)
        all_chains.append(chain)
        if chain:
            answers.append(chain[-1])
    # Vote majoritaire
    counts: dict[str, int] = {}
    for a in answers:
        counts[a] = counts.get(a, 0) + 1
    if counts:
        winner = max(counts, key=counts.get)
        confidence = counts[winner] / len(answers)
    else:
        winner, confidence = "no_answer", 0.0
    # Flatten steps
    steps: list[ReasoningStep] = []
    for ci, chain in enumerate(all_chains):
        for si, s in enumerate(chain):
            steps.append(ReasoningStep(
                index=len(steps),
                content=f"[sample {ci}] {s}", confidence=confidence,
                metadata={"sample": ci, "step": si}))
    # Alternatives rejected
    rejected = [
        {"answer": a, "reason": f"votes={n} < winner_votes={counts[winner]}"}
        for a, n in counts.items() if a != winner
    ]
    return ChainTrace(
        mode="self_consistent", steps=steps,
        intermediate_conclusions=[],
        alternatives_rejected=rejected,
        final_answer=winner, confidence=confidence,
        verification_trace={"n_samples": n_samples,
                             "vote_distribution": counts},
    )


def structured_cot(
    problem: str, *,
    decider: Callable[[str, str], str] | None = None,
) -> ChainTrace:
    """Structured CoT : 5 sections Given/Assumptions/Reasoning/Verification/Conclusion."""
    if decider is None:
        decider = _default_section_decider
    steps: list[ReasoningStep] = []
    answers: dict[str, str] = {}
    for i, section in enumerate(STRUCTURED_SECTIONS):
        content = decider(problem, section)
        answers[section] = content
        steps.append(ReasoningStep(
            index=i, content=f"{section}: {content}", confidence=0.80,
            metadata={"section": section}))
    return ChainTrace(
        mode="structured", steps=steps,
        intermediate_conclusions=[answers[s] for s in ("Given", "Assumptions",
                                                         "Reasoning", "Verification")],
        final_answer=answers.get("Conclusion", ""),
        confidence=0.80,
        verification_trace={"sections": list(answers.keys())},
    )


# ------------------------------------------------------------- default deciders

def _default_step_decider(prompt: str) -> list[str]:
    """Fallback deterministe : split la question en 3 etapes generiques."""
    return [
        f"1. Identify the question in : {prompt[:200]}",
        "2. Consider known constraints and relevant facts",
        "3. Produce a conservative answer based on available evidence",
    ]


def _default_temperature_decider(problem: str, temp: float) -> list[str]:
    """Simule variabilite par temperature (pour tests deterministes en CI)."""
    seed = hash((problem, round(temp, 2))) % 1000
    # 3 variants of answer based on seed
    variant = ["A", "B", "C"][seed % 3]
    return [
        f"[T={temp:.2f}] analyze {problem[:80]}",
        f"[T={temp:.2f}] intermediate reasoning",
        f"answer_{variant}",
    ]


def _default_section_decider(problem: str, section: str) -> str:
    return f"{section} for '{problem[:60]}...' (deterministic default)"
