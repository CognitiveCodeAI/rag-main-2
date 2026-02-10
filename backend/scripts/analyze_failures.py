"""Analyze Final Boss evaluation failures."""

import json
from pathlib import Path

report_path = Path(__file__).parent.parent / "tests" / "eval" / "report_finalboss.md"

with open(report_path, 'r') as f:
    content = f.read()

# Extract all rows from tables  
lines = content.split('\n')
failures = []

for line in lines:
    if line.startswith('| fb_'):
        parts = line.split('|')
        if len(parts) >= 6:
            pass_col = parts[5].strip()
            if pass_col != '✓':
                failures.append(line.strip())

print("=== ALL NON-PASS ROWS ===")
for f in failures:
    print(f)
    print()
