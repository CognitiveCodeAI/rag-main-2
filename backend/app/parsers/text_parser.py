"""Plain text document parser."""

import hashlib
import re
from typing import Any

from .base import (
    Block,
    DocumentIR,
    DocumentParser,
    Page,
    ParseQuality,
    Section,
)


class TextParser(DocumentParser):
    """Parser for plain text documents."""
    
    @property
    def supported_types(self) -> list[str]:
        return ["txt"]
    
    def parse(self, raw_bytes: bytes, doc_ref: dict[str, Any]) -> DocumentIR:
        """Parse plain text into DocumentIR."""
        # Decode text
        try:
            text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text = raw_bytes.decode("latin-1")
        
        blocks: list[Block] = []
        sections: list[Section] = []
        total_offset = 0
        block_count = 0
        
        # Split into paragraphs by double newlines
        paragraphs = re.split(r"\n\s*\n", text)
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            start_offset = total_offset
            end_offset = total_offset + len(para)
            total_offset = end_offset + 1
            
            # Heuristic: check if it looks like a heading
            # (short line, possibly uppercase or followed by underline)
            lines = para.split("\n")
            is_heading = False
            heading_level = 2
            
            if len(lines) == 1:
                line = lines[0].strip()
                # All caps short line
                if line.isupper() and len(line) < 80:
                    is_heading = True
                    heading_level = 1
                # Or ends with colon
                elif line.endswith(":") and len(line) < 80:
                    is_heading = True
                    heading_level = 2
            elif len(lines) == 2:
                # Underlined headings: Title\n=====
                if re.match(r"^[=]+$", lines[1].strip()):
                    is_heading = True
                    heading_level = 1
                    para = lines[0].strip()
                elif re.match(r"^[-]+$", lines[1].strip()):
                    is_heading = True
                    heading_level = 2
                    para = lines[0].strip()
            
            if is_heading:
                block = Block(
                    type="heading",
                    text=para,
                    level=heading_level,
                    start_offset=start_offset,
                    end_offset=end_offset,
                )
                
                section_id = hashlib.md5(
                    f"{block_count}:{para[:50]}".encode()
                ).hexdigest()[:8]
                
                section = Section(
                    section_id=section_id,
                    heading=para,
                    level=heading_level,
                    block_refs=[block_count],
                    section_path=[para],
                )
                sections.append(section)
            else:
                block = Block(
                    type="paragraph",
                    text=para,
                    start_offset=start_offset,
                    end_offset=end_offset,
                )
            
            blocks.append(block)
            block_count += 1
        
        pages = [Page(page_num=1, blocks=blocks)]
        
        quality = ParseQuality(
            parse_confidence=0.80,  # Less confident due to minimal structure
            ocr_used=False,
        )
        
        return DocumentIR(
            doc_ref=doc_ref,
            title=None,
            language=None,
            pages=pages,
            sections=sections,
            quality=quality,
        )
