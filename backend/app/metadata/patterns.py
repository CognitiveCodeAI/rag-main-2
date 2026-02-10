"""Regex patterns and keywords for metadata extraction.

This module contains all the patterns used by MetadataExtractor to
detect dates, departments, doc types, and authority tiers from:
- Filenames
- First-page text
- PDF metadata
"""

import re
from typing import Dict, List, Pattern, Set, Tuple

# =============================================================================
# DATE PATTERNS (for first-page text extraction)
# =============================================================================

# Matches various date formats in document text
DATE_PATTERNS: List[Tuple[Pattern, str]] = [
    # ISO format: 2024-01-15, 2024/01/15
    (re.compile(r'\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b'), 'iso'),
    
    # US format: 01/15/2024, 01-15-2024
    (re.compile(r'\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b'), 'us'),
    
    # Long format: January 15, 2024; Jan 15, 2024; January 15th, 2024
    (re.compile(
        r'\b(January|February|March|April|May|June|July|August|September|October|November|December|'
        r'Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b',
        re.IGNORECASE
    ), 'long'),
    
    # European format: 15 January 2024, 15th January 2024
    (re.compile(
        r'\b(\d{1,2})(?:st|nd|rd|th)?\s+(January|February|March|April|May|June|July|August|September|October|November|December|'
        r'Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?,?\s+(\d{4})\b',
        re.IGNORECASE
    ), 'european'),
    
    # Month Year only: January 2024, Jan 2024
    (re.compile(
        r'\b(January|February|March|April|May|June|July|August|September|October|November|December|'
        r'Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+(\d{4})\b',
        re.IGNORECASE
    ), 'month_year'),
]

# Month name to number mapping
MONTH_MAP: Dict[str, int] = {
    'january': 1, 'jan': 1,
    'february': 2, 'feb': 2,
    'march': 3, 'mar': 3,
    'april': 4, 'apr': 4,
    'may': 5,
    'june': 6, 'jun': 6,
    'july': 7, 'jul': 7,
    'august': 8, 'aug': 8,
    'september': 9, 'sep': 9,
    'october': 10, 'oct': 10,
    'november': 11, 'nov': 11,
    'december': 12, 'dec': 12,
}

# =============================================================================
# FILENAME DATE PATTERNS
# =============================================================================

# Patterns to extract dates/years from filenames
FILENAME_DATE_PATTERNS: List[Tuple[Pattern, str]] = [
    # Full date in filename: 2024-01-15, 20240115
    (re.compile(r'(\d{4})[-_]?(\d{2})[-_]?(\d{2})'), 'full_date'),
    
    # Year-month: 2024-01, 2024_01
    (re.compile(r'(\d{4})[-_](\d{2})(?!\d)'), 'year_month'),
    
    # Quarter format: Q1_2024, 2024_Q1, Q1-2024
    (re.compile(r'[Qq]([1-4])[-_]?(\d{4})|(\d{4})[-_]?[Qq]([1-4])'), 'quarter'),
    
    # FY format: FY2024, FY24, FY_2024
    (re.compile(r'[Ff][Yy][-_]?(\d{2,4})'), 'fiscal_year'),
    
    # Year only: 2024, _2024_, (2024)
    (re.compile(r'(?:^|[^0-9])(\d{4})(?:[^0-9]|$)'), 'year_only'),
]

# =============================================================================
# DEPARTMENT KEYWORDS
# =============================================================================

# Department detection keywords (lowercase)
# Maps keyword -> canonical department name
DEPARTMENT_KEYWORDS: Dict[str, str] = {
    # Legal
    'legal': 'legal',
    'law': 'legal',
    'counsel': 'legal',
    'attorney': 'legal',
    'compliance': 'legal',
    'regulatory': 'legal',
    
    # Marketing
    'marketing': 'marketing',
    'brand': 'marketing',
    'advertising': 'marketing',
    'campaign': 'marketing',
    'creative': 'marketing',
    'communications': 'marketing',
    'pr': 'marketing',
    'public relations': 'marketing',
    
    # HR / Human Resources
    'hr': 'hr',
    'human resources': 'hr',
    'people': 'hr',
    'talent': 'hr',
    'recruiting': 'hr',
    'recruitment': 'hr',
    'benefits': 'hr',
    'payroll': 'hr',
    'employee': 'hr',
    
    # Engineering
    'engineering': 'engineering',
    'development': 'engineering',
    'technical': 'engineering',
    'technology': 'engineering',
    'software': 'engineering',
    'architecture': 'engineering',
    'infrastructure': 'engineering',
    'devops': 'engineering',
    'it': 'engineering',
    
    # Finance
    'finance': 'finance',
    'financial': 'finance',
    'accounting': 'finance',
    'treasury': 'finance',
    'budget': 'finance',
    'tax': 'finance',
    'audit': 'finance',
    
    # Operations
    'operations': 'operations',
    'ops': 'operations',
    'logistics': 'operations',
    'supply chain': 'operations',
    'procurement': 'operations',
    'facilities': 'operations',
    
    # Sales
    'sales': 'sales',
    'revenue': 'sales',
    'business development': 'sales',
    'account': 'sales',
    
    # Product
    'product': 'product',
    'product management': 'product',
    'pm': 'product',
    
    # Research
    'research': 'research',
    'r&d': 'research',
    'innovation': 'research',
    'science': 'research',
}

# =============================================================================
# DOC TYPE KEYWORDS
# =============================================================================

# Document type detection keywords (lowercase)
# Maps keyword -> canonical doc type
DOC_TYPE_KEYWORDS: Dict[str, str] = {
    # Policy
    'policy': 'policy',
    'policies': 'policy',
    'guideline': 'policy',
    'guidelines': 'policy',
    'standard': 'policy',
    'standards': 'policy',
    'regulation': 'policy',
    'regulations': 'policy',
    'rule': 'policy',
    'rules': 'policy',
    
    # Procedure
    'procedure': 'procedure',
    'procedures': 'procedure',
    'process': 'procedure',
    'processes': 'procedure',
    'sop': 'procedure',
    'workflow': 'procedure',
    'instruction': 'procedure',
    'instructions': 'procedure',
    'manual': 'procedure',
    'handbook': 'procedure',
    'guide': 'procedure',
    
    # Contract
    'contract': 'contract',
    'contracts': 'contract',
    'agreement': 'contract',
    'agreements': 'contract',
    'nda': 'contract',
    'msa': 'contract',
    'sla': 'contract',
    'license': 'contract',
    'terms': 'contract',
    
    # Memo
    'memo': 'memo',
    'memorandum': 'memo',
    'notice': 'memo',
    'announcement': 'memo',
    'communication': 'memo',
    'bulletin': 'memo',
    
    # Report
    'report': 'report',
    'reports': 'report',
    'analysis': 'report',
    'assessment': 'report',
    'review': 'report',
    'summary': 'report',
    'findings': 'report',
    
    # Paper (academic/research)
    'paper': 'paper',
    'article': 'paper',
    'publication': 'paper',
    'research': 'paper',
    'study': 'paper',
    'whitepaper': 'paper',
    'white paper': 'paper',
    
    # Presentation
    'presentation': 'presentation',
    'deck': 'presentation',
    'slides': 'presentation',
    'ppt': 'presentation',
    
    # Invoice / Financial
    'invoice': 'invoice',
    'invoices': 'invoice',
    'receipt': 'invoice',
    'bill': 'invoice',
    'statement': 'invoice',
    
    # Form
    'form': 'form',
    'forms': 'form',
    'template': 'form',
    'templates': 'form',
    'application': 'form',
}

# =============================================================================
# AUTHORITY TIER KEYWORDS
# =============================================================================

# Authority tier inference from doc_type and keywords
# tier 1 = highest authority (policy, regulation)
# tier 2 = procedural (procedure, handbook)
# tier 3 = informational (notes, memo, presentation)

AUTHORITY_TIER_BY_DOC_TYPE: Dict[str, int] = {
    'policy': 1,
    'contract': 1,
    'procedure': 2,
    'report': 2,
    'memo': 3,
    'paper': 2,
    'presentation': 3,
    'invoice': 3,
    'form': 3,
}

# Additional keywords that can boost or lower authority tier
AUTHORITY_TIER_KEYWORDS: Dict[str, int] = {
    # High authority keywords (tier 1)
    'official': 1,
    'approved': 1,
    'mandatory': 1,
    'required': 1,
    'binding': 1,
    'final': 1,
    'executive': 1,
    'board': 1,
    
    # Medium authority keywords (tier 2)
    'recommended': 2,
    'best practice': 2,
    'suggested': 2,
    
    # Low authority keywords (tier 3)
    'draft': 3,
    'preliminary': 3,
    'working': 3,
    'informal': 3,
    'notes': 3,
    'internal': 3,
}

# =============================================================================
# HEADER PATTERNS (for first-page text)
# =============================================================================

# Patterns to find department/type info in document headers
HEADER_PATTERNS: List[Pattern] = [
    # "Department of X" or "X Department"
    re.compile(r'(?:department\s+of\s+|(\w+)\s+department)', re.IGNORECASE),
    
    # "From: Marketing" or "From: Legal Team"
    re.compile(r'from:\s*(\w+(?:\s+\w+)?)', re.IGNORECASE),
    
    # "Prepared by: X Department"
    re.compile(r'prepared\s+by:\s*(\w+(?:\s+\w+)?)', re.IGNORECASE),
    
    # "Policy:" or "Procedure:" at start of line
    re.compile(r'^(policy|procedure|memo|report|contract):', re.IGNORECASE | re.MULTILINE),
]

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def normalize_text(text: str) -> str:
    """Normalize text for keyword matching."""
    return ' '.join(text.lower().split())


def extract_first_n_chars(text: str, n: int = 2000) -> str:
    """Extract first N characters of text for header analysis."""
    return text[:n] if text else ""


# Valid year range for documents (prevents false positives)
MIN_VALID_YEAR = 1990
MAX_VALID_YEAR = 2100


def is_valid_year(year: int) -> bool:
    """Check if a year is within valid document range."""
    return MIN_VALID_YEAR <= year <= MAX_VALID_YEAR
