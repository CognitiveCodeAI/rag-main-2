"""Markdown document parser."""

import hashlib
import re
from typing import Any

import markdown
from markdown.extensions.toc import TocExtension

from .base import (
    Block,
    DocumentIR,
    DocumentParser,
    Page,
    ParseQuality,
    Section,
)


class MarkdownParser(DocumentParser):
    """Parser for Markdown documents."""
    
    @property
    def supported_types(self) -> list[str]:
        return ["md"]
    
    def parse(self, raw_bytes: bytes, doc_ref: dict[str, Any]) -> DocumentIR:
        """Parse Markdown into DocumentIR."""
        # Decode markdown
        try:
            md_text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            md_text = raw_bytes.decode("latin-1")
        
        blocks: list[Block] = []
        sections: list[Section] = []
        section_stack: list[Section] = []
        total_offset = 0
        block_count = 0
        title = None
        
        # Process line by line for structure extraction
        lines = md_text.split("\n")
        i = 0
        
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            # Check for headings
            heading_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
            if heading_match:
                level = len(heading_match.group(1))
                text = heading_match.group(2).strip()
                
                start_offset = total_offset
                end_offset = total_offset + len(text)
                total_offset = end_offset + 1
                
                block = Block(
                    type="heading",
                    text=text,
                    level=level,
                    start_offset=start_offset,
                    end_offset=end_offset,
                )
                blocks.append(block)
                
                # Update sections
                section_id = hashlib.md5(
                    f"{block_count}:{text[:50]}".encode()
                ).hexdigest()[:8]
                
                while section_stack and section_stack[-1].level >= level:
                    section_stack.pop()
                
                section_path = [s.heading for s in section_stack] + [text]
                
                section = Section(
                    section_id=section_id,
                    heading=text,
                    level=level,
                    block_refs=[block_count],
                    section_path=section_path,
                )
                sections.append(section)
                section_stack.append(section)
                
                if level == 1 and title is None:
                    title = text
                
                block_count += 1
                i += 1
                continue
            
            # Check for code blocks
            if stripped.startswith("```"):
                code_lang = stripped[3:].strip() or None
                code_lines = []
                i += 1
                
                while i < len(lines) and not lines[i].strip().startswith("```"):
                    code_lines.append(lines[i])
                    i += 1
                
                if code_lines:
                    code_text = "\n".join(code_lines)
                    start_offset = total_offset
                    end_offset = total_offset + len(code_text)
                    total_offset = end_offset + 1
                    
                    block = Block(
                        type="code",
                        text=code_text,
                        code_lang=code_lang,
                        start_offset=start_offset,
                        end_offset=end_offset,
                    )
                    blocks.append(block)
                    
                    if section_stack:
                        section_stack[-1].block_refs.append(block_count)
                    
                    block_count += 1
                
                i += 1
                continue
            
            # Check for tables (pipe-delimited)
            if "|" in stripped and stripped.startswith("|"):
                table_lines = [stripped]
                i += 1
                
                while i < len(lines) and "|" in lines[i].strip():
                    table_lines.append(lines[i].strip())
                    i += 1
                
                if len(table_lines) >= 2:
                    cells: list[list[str]] = []
                    for tline in table_lines:
                        # Skip separator lines
                        if re.match(r"^\|[\s\-:]+\|$", tline):
                            continue
                        row_cells = [c.strip() for c in tline.split("|")[1:-1]]
                        if row_cells:
                            cells.append(row_cells)
                    
                    if cells:
                        table_text = "\n".join(["\t".join(row) for row in cells])
                        start_offset = total_offset
                        end_offset = total_offset + len(table_text)
                        total_offset = end_offset + 1
                        
                        block = Block(
                            type="table",
                            cells=cells,
                            start_offset=start_offset,
                            end_offset=end_offset,
                        )
                        blocks.append(block)
                        
                        if section_stack:
                            section_stack[-1].block_refs.append(block_count)
                        
                        block_count += 1
                
                continue
            
            # Check for list items
            list_match = re.match(r"^[\*\-\+]\s+(.+)$", stripped) or re.match(r"^\d+\.\s+(.+)$", stripped)
            if list_match:
                list_items = [list_match.group(1).strip()]
                i += 1
                
                while i < len(lines):
                    item_line = lines[i].strip()
                    item_match = re.match(r"^[\*\-\+]\s+(.+)$", item_line) or re.match(r"^\d+\.\s+(.+)$", item_line)
                    if item_match:
                        list_items.append(item_match.group(1).strip())
                        i += 1
                    elif not item_line:
                        break
                    else:
                        break
                
                list_text = "\n".join(list_items)
                start_offset = total_offset
                end_offset = total_offset + len(list_text)
                total_offset = end_offset + 1
                
                block = Block(
                    type="list",
                    list_items=list_items,
                    start_offset=start_offset,
                    end_offset=end_offset,
                )
                blocks.append(block)
                
                if section_stack:
                    section_stack[-1].block_refs.append(block_count)
                
                block_count += 1
                continue
            
            # Regular paragraph - collect consecutive non-empty lines
            if stripped:
                para_lines = [stripped]
                i += 1
                
                while i < len(lines):
                    next_line = lines[i].strip()
                    if not next_line:
                        break
                    # Stop if it looks like a special line
                    if next_line.startswith("#") or next_line.startswith("```") or next_line.startswith("|"):
                        break
                    if re.match(r"^[\*\-\+]\s+", next_line) or re.match(r"^\d+\.\s+", next_line):
                        break
                    para_lines.append(next_line)
                    i += 1
                
                text = " ".join(para_lines)
                start_offset = total_offset
                end_offset = total_offset + len(text)
                total_offset = end_offset + 1
                
                block = Block(
                    type="paragraph",
                    text=text,
                    start_offset=start_offset,
                    end_offset=end_offset,
                )
                blocks.append(block)
                
                if section_stack:
                    section_stack[-1].block_refs.append(block_count)
                
                block_count += 1
                continue
            
            i += 1
        
        pages = [Page(page_num=1, blocks=blocks)]
        
        quality = ParseQuality(
            parse_confidence=0.95,
            ocr_used=False,
        )
        
        return DocumentIR(
            doc_ref=doc_ref,
            title=title,
            language=None,
            pages=pages,
            sections=sections,
            quality=quality,
        )
