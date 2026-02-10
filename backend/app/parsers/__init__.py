# Document parsers module
from .base import DocumentParser, ParserRegistry
from .pdf_parser import PDFParser
from .docx_parser import DocxParser
from .html_parser import HTMLParser
from .markdown_parser import MarkdownParser
from .text_parser import TextParser
from .csv_parser import CSVParser
from .xlsx_parser import XLSXParser

# Register all parsers
ParserRegistry.register(PDFParser())
ParserRegistry.register(DocxParser())
ParserRegistry.register(HTMLParser())
ParserRegistry.register(MarkdownParser())
ParserRegistry.register(TextParser())
ParserRegistry.register(CSVParser())
ParserRegistry.register(XLSXParser())

__all__ = [
    "DocumentParser",
    "ParserRegistry",
    "PDFParser",
    "DocxParser",
    "HTMLParser",
    "MarkdownParser",
    "TextParser",
    "CSVParser",
    "XLSXParser",
]
