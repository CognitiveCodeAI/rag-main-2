"""OCR prompt templates for DeepSeek-OCR via Ollama.

Prompts are versioned to ensure deterministic behavior and allow
tracking which prompt version was used for each extraction.
"""

PROMPT_VERSION = "v1"


class OCRPrompts:
    """OCR prompt templates."""
    
    # Prompt A: Full page OCR to markdown
    FULL_PAGE = """Extract all text from this document page as clean markdown.

Rules:
- Preserve headings using # syntax
- Preserve lists using - or 1. syntax
- Preserve tables as markdown tables with | delimiters
- Preserve paragraphs with blank lines between them
- Do NOT describe the image - only output the actual text content
- Do NOT add any commentary or explanation
- Output ONLY the extracted text in markdown format"""

    # Prompt B: Figure/table region OCR to markdown
    REGION = """Extract text from this figure or table region as markdown.

Rules:
- For tables: output as markdown table with | delimiters
- For charts/graphs: extract axis labels, legend text, and visible numbers
- For figures: extract any visible text, labels, or annotations
- Keep output concise - only the text content visible in the image
- Do NOT describe what you see - only output the actual text
- Output ONLY the extracted text"""

    # Prompt C: Caption extraction (for when we just need to find captions)
    CAPTION = """Find and extract any figure or table caption visible in this image.

Look for text like:
- "Figure X: ..."
- "Fig. X: ..."
- "Table X: ..."
- Captions typically appear below figures or above tables

Output ONLY the caption text, or "NO_CAPTION" if none found."""

    @classmethod
    def get_full_page_prompt(cls) -> str:
        """Get the full page OCR prompt."""
        return cls.FULL_PAGE
    
    @classmethod
    def get_region_prompt(cls) -> str:
        """Get the region OCR prompt."""
        return cls.REGION
    
    @classmethod
    def get_caption_prompt(cls) -> str:
        """Get the caption extraction prompt."""
        return cls.CAPTION
