"""CSV document parser using pandas."""

import io
from typing import Any

import pandas as pd

from .base import (
    Block,
    DocumentIR,
    DocumentParser,
    Page,
    ParseQuality,
)


class CSVParser(DocumentParser):
    """Parser for CSV documents."""
    
    @property
    def supported_types(self) -> list[str]:
        return ["csv"]
    
    def parse(self, raw_bytes: bytes, doc_ref: dict[str, Any]) -> DocumentIR:
        """Parse CSV into DocumentIR."""
        # Try to decode
        try:
            csv_text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            csv_text = raw_bytes.decode("latin-1")
        
        # Parse with pandas
        df = pd.read_csv(io.StringIO(csv_text))
        
        # Convert DataFrame to table cells
        cells: list[list[str]] = []
        
        # Add header row
        headers = [str(col) for col in df.columns]
        cells.append(headers)
        
        # Add data rows
        for _, row in df.iterrows():
            row_cells = [str(val) if pd.notna(val) else "" for val in row]
            cells.append(row_cells)
        
        # Create single table block
        table_text = "\n".join(["\t".join(row) for row in cells])
        
        block = Block(
            type="table",
            cells=cells,
            start_offset=0,
            end_offset=len(table_text),
        )
        
        pages = [Page(page_num=1, blocks=[block])]
        
        # Extract title from filename in source_uri if available
        source_uri = doc_ref.get("source_uri", "")
        title = source_uri.split("/")[-1] if "/" in source_uri else source_uri
        
        quality = ParseQuality(
            parse_confidence=0.98,  # CSV is very structured
            ocr_used=False,
            table_confidence=0.98,
        )
        
        return DocumentIR(
            doc_ref=doc_ref,
            title=title,
            language=None,
            pages=pages,
            sections=[],
            quality=quality,
        )
