"""PDF document parser using PyMuPDF and pdfplumber."""

import hashlib
import io
import re
from typing import Any

import fitz  # PyMuPDF
import pdfplumber

from .base import (
    Block,
    DocumentIR,
    DocumentParser,
    Page,
    ParseQuality,
    Section,
)


class PDFParser(DocumentParser):
    """Parser for PDF documents."""
    
    @property
    def supported_types(self) -> list[str]:
        return ["pdf"]
    
    def parse(self, raw_bytes: bytes, doc_ref: dict[str, Any]) -> DocumentIR:
        """Parse PDF into DocumentIR."""
        pages: list[Page] = []
        sections: list[Section] = []
        total_offset = 0
        section_stack: list[Section] = []
        block_count = 0
        tables_found = 0
        tables_confident = 0
        
        # Use PyMuPDF for text extraction
        pdf_doc = fitz.open(stream=raw_bytes, filetype="pdf")
        
        # Also open with pdfplumber for table detection
        pdf_plumber = pdfplumber.open(io.BytesIO(raw_bytes))
        
        title = None
        
        for page_num in range(len(pdf_doc)):
            page_blocks: list[Block] = []
            
            # Get PyMuPDF page
            fitz_page = pdf_doc[page_num]
            
            # Get pdfplumber page for tables
            plumber_page = pdf_plumber.pages[page_num] if page_num < len(pdf_plumber.pages) else None
            
            # Extract tables from pdfplumber
            tables = []
            table_bboxes = []
            if plumber_page:
                for table in plumber_page.extract_tables():
                    if table and len(table) > 0:
                        tables_found += 1
                        # Clean table data
                        cleaned = [[cell or "" for cell in row] for row in table]
                        tables.append(cleaned)
                        tables_confident += 1
                
                # Get table bounding boxes
                table_settings = {}
                detected = plumber_page.find_tables(table_settings)
                for t in detected:
                    table_bboxes.append(t.bbox)
            
            # Extract text blocks from PyMuPDF
            text_dict = fitz_page.get_text("dict", sort=True)
            
            for block_data in text_dict.get("blocks", []):
                if block_data.get("type") == 0:  # Text block
                    lines = []
                    for line in block_data.get("lines", []):
                        line_text = ""
                        for span in line.get("spans", []):
                            line_text += span.get("text", "")
                        if line_text.strip():
                            lines.append(line_text.strip())
                    
                    if not lines:
                        continue
                    
                    text = "\n".join(lines)
                    start_offset = total_offset
                    end_offset = total_offset + len(text)
                    total_offset = end_offset + 1
                    
                    # Check if this looks like a heading
                    first_span = None
                    if block_data.get("lines"):
                        first_line = block_data["lines"][0]
                        if first_line.get("spans"):
                            first_span = first_line["spans"][0]
                    
                    is_heading = False
                    heading_level = None
                    
                    if first_span:
                        font_size = first_span.get("size", 12)
                        font_flags = first_span.get("flags", 0)
                        is_bold = bool(font_flags & 2 ** 4)
                        
                        # Heuristic: large or bold text at start of line
                        if font_size >= 14 or (is_bold and font_size >= 12):
                            is_heading = True
                            if font_size >= 20:
                                heading_level = 1
                            elif font_size >= 16:
                                heading_level = 2
                            elif font_size >= 14:
                                heading_level = 3
                            else:
                                heading_level = 4
                    
                    bbox = {
                        "x0": block_data.get("bbox", [0, 0, 0, 0])[0],
                        "y0": block_data.get("bbox", [0, 0, 0, 0])[1],
                        "x1": block_data.get("bbox", [0, 0, 0, 0])[2],
                        "y1": block_data.get("bbox", [0, 0, 0, 0])[3],
                    }
                    
                    if is_heading:
                        block = Block(
                            type="heading",
                            text=text,
                            level=heading_level,
                            bbox=bbox,
                            start_offset=start_offset,
                            end_offset=end_offset,
                        )
                        
                        # Update section tracking
                        section_id = hashlib.md5(
                            f"{page_num}:{block_count}:{text[:50]}".encode()
                        ).hexdigest()[:8]
                        
                        # Pop sections that are at same or lower level
                        while section_stack and section_stack[-1].level >= heading_level:
                            section_stack.pop()
                        
                        section_path = [s.heading for s in section_stack] + [text]
                        
                        section = Section(
                            section_id=section_id,
                            heading=text,
                            level=heading_level,
                            block_refs=[block_count],
                            section_path=section_path,
                        )
                        sections.append(section)
                        section_stack.append(section)
                        
                        # Capture title from first h1
                        if heading_level == 1 and title is None:
                            title = text
                    else:
                        block = Block(
                            type="paragraph",
                            text=text,
                            bbox=bbox,
                            start_offset=start_offset,
                            end_offset=end_offset,
                        )
                        
                        # Add to current section
                        if section_stack:
                            section_stack[-1].block_refs.append(block_count)
                    
                    page_blocks.append(block)
                    block_count += 1
            
            # Add extracted tables as blocks
            for table_cells in tables:
                # Convert table to text for offset calculation
                table_text = "\n".join(["\t".join(row) for row in table_cells])
                start_offset = total_offset
                end_offset = total_offset + len(table_text)
                total_offset = end_offset + 1
                
                block = Block(
                    type="table",
                    cells=table_cells,
                    start_offset=start_offset,
                    end_offset=end_offset,
                )
                page_blocks.append(block)
                
                if section_stack:
                    section_stack[-1].block_refs.append(block_count)
                block_count += 1
            
            pages.append(Page(page_num=page_num + 1, blocks=page_blocks))
        
        pdf_doc.close()
        pdf_plumber.close()
        
        # Calculate quality metrics
        table_confidence = (
            tables_confident / tables_found if tables_found > 0 else None
        )
        
        quality = ParseQuality(
            parse_confidence=0.85,  # Reasonable default for PDF
            ocr_used=False,
            table_confidence=table_confidence,
        )
        
        return DocumentIR(
            doc_ref=doc_ref,
            title=title,
            language=None,  # Could add language detection
            pages=pages,
            sections=sections,
            quality=quality,
        )
