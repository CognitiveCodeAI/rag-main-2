"""Detect Figure/Table/Appendix/Section mentions in a question (E2 extraction).

Pure, deterministic string -> dict. Relocated verbatim from QARunner; the class
keeps aliasing attributes + a delegating method so behavior is unchanged.
"""

import re
from typing import Dict, List

# Regex patterns for structured object mentions
FIGURE_PATTERN = re.compile(r'(?:Figure|Fig\.?)\s*(\d+(?:\.\d+)?)', re.IGNORECASE)
TABLE_PATTERN = re.compile(r'(?:Table|Tab\.?)\s*(\d+(?:\.\d+)?)', re.IGNORECASE)
APPENDIX_PATTERN = re.compile(r'Appendix\s*([A-Za-z])', re.IGNORECASE)
SECTION_PATTERN = re.compile(
    r'\b(Conclusion|Methodology|Introduction|Discussion|Evaluation|Results|Appendix)\b',
    re.IGNORECASE,
)


def detect_structured_targets(question: str) -> Dict[str, List[str]]:
    """Detect Figure/Table/Appendix/Section mentions in a question.

    Returns a dict with keys 'figures', 'tables', 'appendices', 'sections'
    containing normalized target strings.
    """
    targets = {
        "figures": [],
        "tables": [],
        "appendices": [],
        "sections": [],
    }

    for match in FIGURE_PATTERN.finditer(question):
        targets["figures"].append(f"Figure {match.group(1)}")

    for match in TABLE_PATTERN.finditer(question):
        targets["tables"].append(f"Table {match.group(1)}")

    for match in APPENDIX_PATTERN.finditer(question):
        targets["appendices"].append(f"Appendix {match.group(1).upper()}")

    for match in SECTION_PATTERN.finditer(question):
        section = match.group(1).title()  # "conclusion" -> "Conclusion"
        if section not in targets["sections"]:
            targets["sections"].append(section)

    return targets
