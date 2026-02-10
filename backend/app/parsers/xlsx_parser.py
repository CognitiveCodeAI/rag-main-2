"""Excel (XLSX) document parser using pandas and openpyxl."""

import hashlib
import io
from typing import Any

import pandas as pd

from .base import (
    Block,
    DocumentIR,
    DocumentParser,
    Page,
    ParseQuality,
    Section,
)


class XLSXParser(DocumentParser):
    """Parser for Excel XLSX documents."""
    
    @property
    def supported_types(self) -> list[str]:
        return ["xlsx"]
    
    def parse(self, raw_bytes: bytes, doc_ref: dict[str, Any]) -> DocumentIR:
        """Parse XLSX into DocumentIR."""
        # Read all sheets
        xlsx = pd.ExcelFile(io.BytesIO(raw_bytes))
        
        blocks: list[Block] = []
        sections: list[Section] = []
        total_offset = 0
        block_count = 0
        
        for sheet_name in xlsx.sheet_names:
            # Add sheet as section heading
            heading_text = f"Sheet: {sheet_name}"
            start_offset = total_offset
            end_offset = total_offset + len(heading_text)
            total_offset = end_offset + 1
            
            heading_block = Block(
                type="heading",
                text=heading_text,
                level=1,
                start_offset=start_offset,
                end_offset=end_offset,
            )
            blocks.append(heading_block)
            
            section_id = hashlib.md5(
                f"{block_count}:{sheet_name}".encode()
            ).hexdigest()[:8]
            
            section = Section(
                section_id=section_id,
                heading=heading_text,
                level=1,
                block_refs=[block_count],
                section_path=[heading_text],
            )
            sections.append(section)
            block_count += 1
            
            # Read sheet data
            df = pd.read_excel(xlsx, sheet_name=sheet_name)
            
            if df.empty:
                continue
            
            # Convert DataFrame to table cells
            cells: list[list[str]] = []
            
            # Add header row
            headers = [str(col) for col in df.columns]
            cells.append(headers)
            
            # Add data rows
            for _, row in df.iterrows():
                row_cells = [str(val) if pd.notna(val) else "" for val in row]
                cells.append(row_cells)
            
            # Create table block
            table_text = "\n".join(["\t".join(row) for row in cells])
            start_offset = total_offset
            end_offset = total_offset + len(table_text)
            total_offset = end_offset + 1
            
            table_block = Block(
                type="table",
                cells=cells,
                start_offset=start_offset,
                end_offset=end_offset,
            )
            blocks.append(table_block)
            
            # Add table to section
            section.block_refs.append(block_count)
            block_count += 1
        
        # Each sheet becomes a "page"
        pages = [Page(page_num=1, blocks=blocks)]
        
        # Extract title from filename
        source_uri = doc_ref.get("source_uri", "")
        title = source_uri.split("/")[-1] if "/" in source_uri else source_uri
        
        quality = ParseQuality(
            parse_confidence=0.95,
            ocr_used=False,
            table_confidence=0.95,
        )
        
        return DocumentIR(
            doc_ref=doc_ref,
            title=title,
            language=None,
            pages=pages,
            sections=sections,
            quality=quality,
        )
