"""HTML document parser using BeautifulSoup."""

import hashlib
import re
from typing import Any

from bs4 import BeautifulSoup, NavigableString, Tag

from .base import (
    Block,
    DocumentIR,
    DocumentParser,
    Page,
    ParseQuality,
    Section,
)


class HTMLParser(DocumentParser):
    """Parser for HTML documents."""
    
    HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
    CODE_TAGS = {"code", "pre"}
    LIST_TAGS = {"ul", "ol"}
    
    @property
    def supported_types(self) -> list[str]:
        return ["html"]
    
    def parse(self, raw_bytes: bytes, doc_ref: dict[str, Any]) -> DocumentIR:
        """Parse HTML into DocumentIR."""
        # Decode HTML
        try:
            html_text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            html_text = raw_bytes.decode("latin-1")
        
        soup = BeautifulSoup(html_text, "lxml")
        
        # Extract title
        title = None
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)
        
        # Extract language
        language = None
        html_tag = soup.find("html")
        if html_tag and isinstance(html_tag, Tag):
            language = html_tag.get("lang")
        
        blocks: list[Block] = []
        sections: list[Section] = []
        section_stack: list[Section] = []
        total_offset = 0
        block_count = 0
        
        # Find the main content area
        main_content = soup.find("main") or soup.find("article") or soup.find("body") or soup
        
        if main_content:
            self._process_element(
                main_content,
                blocks,
                sections,
                section_stack,
                total_offset,
                block_count,
            )
        
        pages = [Page(page_num=1, blocks=blocks)]
        
        quality = ParseQuality(
            parse_confidence=0.90,
            ocr_used=False,
        )
        
        return DocumentIR(
            doc_ref=doc_ref,
            title=title,
            language=language,
            pages=pages,
            sections=sections,
            quality=quality,
        )
    
    def _process_element(
        self,
        element: Tag | NavigableString,
        blocks: list[Block],
        sections: list[Section],
        section_stack: list[Section],
        offset: int,
        block_idx: int,
    ) -> tuple[int, int]:
        """Recursively process HTML elements."""
        if isinstance(element, NavigableString):
            return offset, block_idx
        
        if not isinstance(element, Tag):
            return offset, block_idx
        
        tag_name = element.name.lower() if element.name else ""
        
        # Skip script, style, and other non-content tags
        if tag_name in {"script", "style", "nav", "footer", "header", "aside"}:
            return offset, block_idx
        
        # Handle heading tags
        if tag_name in self.HEADING_TAGS:
            text = element.get_text(strip=True)
            if text:
                level = int(tag_name[1])
                start_offset = offset
                end_offset = offset + len(text)
                
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
                    f"{block_idx}:{text[:50]}".encode()
                ).hexdigest()[:8]
                
                while section_stack and section_stack[-1].level >= level:
                    section_stack.pop()
                
                section_path = [s.heading for s in section_stack] + [text]
                
                section = Section(
                    section_id=section_id,
                    heading=text,
                    level=level,
                    block_refs=[block_idx],
                    section_path=section_path,
                )
                sections.append(section)
                section_stack.append(section)
                
                return end_offset + 1, block_idx + 1
        
        # Handle code blocks
        if tag_name == "pre":
            code_elem = element.find("code")
            text = code_elem.get_text() if code_elem else element.get_text()
            if text.strip():
                start_offset = offset
                end_offset = offset + len(text)
                
                # Try to detect language from class
                code_lang = None
                if code_elem and isinstance(code_elem, Tag):
                    classes = code_elem.get("class", [])
                    for cls in classes:
                        if cls.startswith("language-"):
                            code_lang = cls.replace("language-", "")
                            break
                
                block = Block(
                    type="code",
                    text=text,
                    code_lang=code_lang,
                    start_offset=start_offset,
                    end_offset=end_offset,
                )
                blocks.append(block)
                
                if section_stack:
                    section_stack[-1].block_refs.append(block_idx)
                
                return end_offset + 1, block_idx + 1
        
        # Handle tables
        if tag_name == "table":
            cells: list[list[str]] = []
            for row in element.find_all("tr"):
                row_cells = []
                for cell in row.find_all(["td", "th"]):
                    row_cells.append(cell.get_text(strip=True))
                if row_cells:
                    cells.append(row_cells)
            
            if cells:
                table_text = "\n".join(["\t".join(row) for row in cells])
                start_offset = offset
                end_offset = offset + len(table_text)
                
                block = Block(
                    type="table",
                    cells=cells,
                    start_offset=start_offset,
                    end_offset=end_offset,
                )
                blocks.append(block)
                
                if section_stack:
                    section_stack[-1].block_refs.append(block_idx)
                
                return end_offset + 1, block_idx + 1
        
        # Handle lists
        if tag_name in self.LIST_TAGS:
            items = []
            for li in element.find_all("li", recursive=False):
                items.append(li.get_text(strip=True))
            
            if items:
                list_text = "\n".join(items)
                start_offset = offset
                end_offset = offset + len(list_text)
                
                block = Block(
                    type="list",
                    list_items=items,
                    start_offset=start_offset,
                    end_offset=end_offset,
                )
                blocks.append(block)
                
                if section_stack:
                    section_stack[-1].block_refs.append(block_idx)
                
                return end_offset + 1, block_idx + 1
        
        # Handle paragraphs
        if tag_name == "p":
            text = element.get_text(strip=True)
            if text:
                start_offset = offset
                end_offset = offset + len(text)
                
                block = Block(
                    type="paragraph",
                    text=text,
                    start_offset=start_offset,
                    end_offset=end_offset,
                )
                blocks.append(block)
                
                if section_stack:
                    section_stack[-1].block_refs.append(block_idx)
                
                return end_offset + 1, block_idx + 1
        
        # Recurse into child elements
        for child in element.children:
            offset, block_idx = self._process_element(
                child, blocks, sections, section_stack, offset, block_idx
            )
        
        return offset, block_idx
