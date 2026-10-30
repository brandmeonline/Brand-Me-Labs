"""
Five A/B experiment definitions with flag wiring (Ultra plan 02, item 8).
None of them runs without founder approval.

Each definition states:
* the question it answers and its arms;
* the **default arm**, which is what every member gets today;
* where it is wired, the metrics that decide it and the guardrails that stop it;
* which arms are built.

``arm(experiment_id, member_id)`` is the one flag read at each wired decision
point. It returns the default arm unless all of these hold:
1. the founder approved this exact definition version (``APPROVALS``);
2. foundation's flag primitive is installed (``install_primitive``); it does
   not exist yet;
3. the primitive assigns a built arm.

A definition change bumps its version, which voids an earlier approval. A
member is never put in an arm whose behaviour is not built.

Two experiments have both arms built and read their flag in code:
``curator_verbosity`` in ``persona/service.py`` and
``decision_thread_persistence`` in ``social/decisions.py``. The other three have
only their default (today's behaviour) built. Each names where its read goes,
and none can run until its other arm exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple

Primitive = Callable[[str, int, str, Tuple[str, ...]], Optional[str]]


@dataclass(frozen=True)
class Experiment:
    id: str
    version: int
    question: str
    arms: Tuple[str, ...]
    default: str
    built: Tuple[str, ...]
    wired_at: str
    metrics: Tuple[str, ...]
    guardrails: Tuple[str, ...]


EXPERIMENTS: Dict[str, Experiment] = {e.id: e for e in (
    Experiment("closet_memory", 1, "Does a dated diary of an archived piece's life keep members curating, compared with a clean archive?",
               ("clean_archive", "diary"), "clean_archive", ("clean_archive",),
               "to wire at wardrobe/service.py list_items(collection='archive') when the diary arm is built",
               ("archive revisits per member per week", "pieces restored from archive"),
               ("deletion and export requests do not rise", "no increase in pieces hidden from friends")),
    Experiment("curator_verbosity", 1, "Do members act more on recommendations with the full why (today) or a one-line reason?",
               ("detailed", "concise"), "detailed", ("detailed", "concise"),
               "persona/service.py recommendations()",
               ("recommendations saved or tried on", "'not me' rate"),
               ("time to first action does not grow by more than 10%",)),
    Experiment("the_reveal", 1, "Does a short anticipation pause before a Now result, adapted to how close the friends are, feel better than an instant reveal?",
               ("instant", "anticipation_pause"), "instant", ("instant",),
               "to wire at social/decisions.py get() for the asker when the pause arm is built",
               ("asker returns to the result", "follow-up decisions within 7 days"),
               ("no rise in decisions cancelled before close", "pause never longer than 3 s")),
    Experiment("visitor_traces", 1, "Do soft signals that friends visited a closet (counts only, never who) bring owners back to curate?",
               ("off", "soft_signals"), "off", ("off",),
               "to wire at wardrobe/visibility.py closet() when the signals arm is built",
               ("owner curation sessions per week",),
               ("no rise in pieces set back to private", "never reveals which member visited")),
    Experiment("decision_thread_persistence", 1, "Should a Now comment thread stay readable after the window closes, or fade with it?",
               ("persist", "fade_after_close"), "persist", ("persist", "fade_after_close"),
               "social/decisions.py comments()",
               ("comments per decision", "repeat askers"),
               ("no rise in comment reports", "the asker's own result is never hidden")),
)}

APPROVALS: Dict[str, int] = {}  # experiment id → founder-approved definition version; none yet
_primitive: Optional[Primitive] = None


def install_primitive(primitive: Optional[Primitive]) -> None:
    """Foundation's flag primitive: (experiment_id, version, member_id, built arms) → arm or None."""
    global _primitive
    _primitive = primitive


def arm(experiment_id: str, member_id: str) -> str:
    e = EXPERIMENTS[experiment_id]
    if APPROVALS.get(experiment_id) != e.version or _primitive is None:
        return e.default
    chosen = _primitive(e.id, e.version, member_id, e.built)
    return chosen if chosen in e.built else e.default


def definitions() -> Dict[str, Dict[str, object]]:
    """Read-only listing for review: each definition and whether it may run."""
    return {e.id: {"version": e.version, "question": e.question, "arms": list(e.arms), "default": e.default, "built": list(e.built),
                   "wired_at": e.wired_at, "metrics": list(e.metrics), "guardrails": list(e.guardrails),
                   "approved": APPROVALS.get(e.id) == e.version, "running": APPROVALS.get(e.id) == e.version and _primitive is not None}
            for e in EXPERIMENTS.values()}
