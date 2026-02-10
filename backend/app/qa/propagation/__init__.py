"""TRACK-inspired Propagation Safety Mode for multi-step reasoning.

This module provides components for decomposing complex questions,
verifying sub-answers with citations, and synthesizing answers
from verified facts only.
"""

from app.qa.propagation.types import (
    SubQuestion,
    EvidenceSnippet,
    EvidencePacket,
    SubAnswer,
    PropagationSafetyAudit,
    PropagationSafetyConfig,
)
from app.qa.propagation.planner import Planner
from app.qa.propagation.verifier import Verifier
from app.qa.propagation.synthesizer import Synthesizer

__all__ = [
    "SubQuestion",
    "EvidenceSnippet",
    "EvidencePacket",
    "SubAnswer",
    "PropagationSafetyAudit",
    "PropagationSafetyConfig",
    "Planner",
    "Verifier",
    "Synthesizer",
]
