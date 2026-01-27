"""
File Processor Module for AI Translator.
Handles text extraction and translation for supported file formats.
"""
import os
import logging
from typing import List, Dict, Optional, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.api_manager import AIAPIManager

try:
    import docx
except ImportError:
    docx = None

try:
    import pysrt
except ImportError:
    pysrt = None

try:
    import chardet
except ImportError:
    chardet = None

try:
    import PyPDF2
except ImportError:
    PyPDF2 = None

# Import PDFOCRProcessor for scanned PDF support
try:
    from src.core.pdf_ocr import PDFOCRProcessor, HAS_PYMUPDF
except ImportError:
    PDFOCRProcessor = None
    HAS_PYMUPDF = False


class FileProcessor:
    """Handles text extraction and translation for files."""

    MAX_CHUNK_SIZE: int = 4000

    def __init__(self, api_manager: 'AIAPIManager') -> None:
        self.api_manager = api_manager
        self.logger = logging.getLogger(__name__)

        # Initialize PDF OCR processor if available
        if PDFOCRProcessor:
            self.pdf_ocr = PDFOCRProcessor(api_manager)
        else:
            self.pdf_ocr = None

    def extract_text(self, file_path: str) -> str:
        """Extract text content from supported file formats."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        ext = os.path.splitext(file_path)[1].lower()

        if ext == '.txt':
            return self._extract_txt(file_path)
        elif ext == '.docx':
            return self._extract_docx(file_path)
        elif ext == '.srt':
            return self._extract_srt(file_path)
        elif ext == '.pdf':
            return self._extract_pdf(file_path)
        else:
            raise ValueError(f"Unsupported file format: {ext}")

    def _extract_txt(self, file_path: str) -> str:
        """Extract text from .txt file with encoding detection."""
        encoding = 'utf-8'
        if chardet:
            with open(file_path, 'rb') as f:
                raw = f.read()
                result = chardet.detect(raw)
                encoding = result['encoding'] or 'utf-8'
            
        with open(file_path, 'r', encoding=encoding, errors='replace') as f:
            return f.read()

    def _extract_docx(self, file_path: str) -> str:
        """Extract text from .docx file."""
        if not docx:
            raise ImportError("python-docx is not installed. Please install it to process .docx files.")
        doc = docx.Document(file_path)
        return '\n'.join([p.text for p in doc.paragraphs])

    def _extract_srt(self, file_path: str) -> str:
        """Extract text from .srt file, preserving structure."""
        if not pysrt:
            raise ImportError("pysrt is not installed. Please install it to process .srt files.")

        # Detect encoding first
        encoding = 'utf-8'
        if chardet:
            with open(file_path, 'rb') as f:
                raw = f.read()
                result = chardet.detect(raw)
                encoding = result['encoding'] or 'utf-8'

        subs = pysrt.open(file_path, encoding=encoding)
        # Return formatted SRT string to preserve timestamps
        return '\n'.join([str(sub) for sub in subs])

    def _extract_pdf(self, file_path: str) -> str:
        """Extract text from .pdf file.

        Uses PDFOCRProcessor which:
        - Tries PyPDF2 text extraction first (fast, no API cost)
        - Falls back to Gemini Vision OCR for scanned PDFs
        """
        if not PyPDF2:
            raise ImportError("PyPDF2 is not installed. Please install it to process .pdf files.")

        # Use PDFOCRProcessor if available (handles both text-based and scanned PDFs)
        if self.pdf_ocr:
            try:
                return self.pdf_ocr.extract_text(file_path)
            except ImportError as e:
                # PyMuPDF not installed, fall back to basic extraction
                self.logger.warning(f"OCR not available: {e}. Using basic text extraction.")
            except Exception as e:
                self.logger.error(f"PDF OCR failed: {e}. Using basic text extraction.")

        # Fallback to basic PyPDF2 extraction
        text_parts = []
        try:
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                for i, page in enumerate(reader.pages):
                    text = page.extract_text()
                    if text and text.strip():
                        text_parts.append(f"--- Page {i + 1} ---\n{text}")
        except Exception as e:
            raise ValueError(f"Failed to extract text from PDF: {e}")

        if not text_parts:
            return "[PDF contains no extractable text - may be scanned/image-based. Install PyMuPDF for OCR support: pip install PyMuPDF]"

        return '\n\n'.join(text_parts)

    def translate_file(self, file_path: str, target_lang: str, progress_callback: Optional[Callable[[int, int], None]] = None) -> str:
        """Translate file content with chunking."""
        text = self.extract_text(file_path)
        if not text.strip():
            return ""
            
        chunks = self._chunk_text(text)
        translated_chunks = []
        total = len(chunks)
        
        for i, chunk in enumerate(chunks):
            if progress_callback:
                progress_callback(i, total)
                
            # Prompt designed to preserve formatting (crucial for SRT/Docx structure)
            prompt = f"Translate the following text to {target_lang}. Preserve original formatting, line breaks, and timestamps (if any) exactly.\n\n{chunk}"
            try:
                translated = self.api_manager.translate(prompt)
                translated_chunks.append(translated)
            except Exception as e:
                translated_chunks.append(f"[Translation Error: {str(e)}]")
                
        return '\n'.join(translated_chunks)

    def _chunk_text(self, text: str) -> List[str]:
        """Split text into chunks respecting boundaries."""
        chunks = []
        current_chunk = ""
        
        # Split by newlines to preserve paragraph/subtitle structure
        lines = text.split('\n')
        
        for line in lines:
            if len(current_chunk) + len(line) < self.MAX_CHUNK_SIZE:
                current_chunk += line + "\n"
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = line + "\n"
                
                # If a single line is too huge (unlikely but possible), force split
                while len(current_chunk) > self.MAX_CHUNK_SIZE:
                    chunks.append(current_chunk[:self.MAX_CHUNK_SIZE])
                    current_chunk = current_chunk[self.MAX_CHUNK_SIZE:]
        
        if current_chunk:
            chunks.append(current_chunk)
            
        return chunks