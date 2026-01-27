"""
PDF OCR Module for AI Translator.
Handles text extraction from scanned PDFs using Gemini Vision OCR.
"""
import os
import tempfile
import logging
from typing import Optional, Callable, TYPE_CHECKING
from dataclasses import dataclass

if TYPE_CHECKING:
    from src.core.api_manager import AIAPIManager

# Optional imports
try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False
    fitz = None

try:
    import PyPDF2
    HAS_PYPDF2 = True
except ImportError:
    HAS_PYPDF2 = False
    PyPDF2 = None


@dataclass
class PDFInfo:
    """Information about a PDF file."""
    page_count: int
    is_scanned: bool
    has_text: bool
    text_density: float  # average chars per page


class PDFOCRProcessor:
    """
    Handles PDF text extraction with OCR fallback for scanned documents.

    Strategy:
    1. Try PyPDF2 text extraction first (fast, no API cost)
    2. If text density is low (scanned PDF), use Gemini Vision OCR
    3. Combine results and return

    Usage:
        processor = PDFOCRProcessor(api_manager)
        info = processor.analyze_pdf(file_path)
        if info.is_scanned:
            text = processor.extract_text(file_path, progress_callback)
    """

    # Threshold: if avg chars per page < this, consider scanned
    SCANNED_THRESHOLD = 50

    # OCR settings
    DEFAULT_DPI = 150  # Balance between quality and size
    MIN_DPI = 72       # Minimum for very large pages
    MAX_IMAGE_SIZE_MB = 4  # Gemini limit

    # OCR prompt for text extraction
    OCR_PROMPT = """Extract ALL text from this document image exactly as it appears.

Requirements:
- Preserve the original layout, paragraph breaks, and spacing
- Maintain any tables, lists, or structured formatting
- Read multi-column text from left to right, top to bottom
- Include headers, footers, page numbers if visible
- Mark unclear or illegible text as [unclear]

Output the extracted text only, no explanations or commentary."""

    def __init__(self, api_manager: 'AIAPIManager') -> None:
        """
        Initialize PDFOCRProcessor.

        Args:
            api_manager: AIAPIManager instance for Vision API calls
        """
        self.api_manager = api_manager
        self.logger = logging.getLogger(__name__)

    def analyze_pdf(self, file_path: str) -> PDFInfo:
        """
        Analyze PDF to determine if it's scanned or text-based.

        Args:
            file_path: Path to PDF file

        Returns:
            PDFInfo with analysis results

        Raises:
            ImportError: If PyPDF2 is not installed
            FileNotFoundError: If file doesn't exist
        """
        if not HAS_PYPDF2:
            raise ImportError(
                "PyPDF2 required for PDF analysis. "
                "Install with: pip install PyPDF2"
            )

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"PDF file not found: {file_path}")

        total_text = ""
        page_count = 0

        try:
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                page_count = len(reader.pages)

                for page in reader.pages:
                    text = page.extract_text() or ""
                    total_text += text.strip()

        except Exception as e:
            self.logger.error(f"Error analyzing PDF: {e}")
            raise ValueError(f"Failed to analyze PDF: {e}")

        text_density = len(total_text) / max(1, page_count)
        is_scanned = text_density < self.SCANNED_THRESHOLD
        has_text = len(total_text.strip()) > 0

        self.logger.info(
            f"PDF Analysis: {page_count} pages, "
            f"density={text_density:.1f} chars/page, "
            f"scanned={is_scanned}"
        )

        return PDFInfo(
            page_count=page_count,
            is_scanned=is_scanned,
            has_text=has_text,
            text_density=text_density
        )

    def extract_text(
        self,
        file_path: str,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> str:
        """
        Extract text from PDF, using OCR if necessary.

        Args:
            file_path: Path to PDF file
            progress_callback: Optional callback(current, total, status_message)

        Returns:
            Extracted text from all pages

        Raises:
            ImportError: If required libraries are not installed
            FileNotFoundError: If file doesn't exist
            ValueError: If PDF is corrupted or cannot be processed
        """
        info = self.analyze_pdf(file_path)

        if not info.is_scanned and info.has_text:
            # Text-based PDF - use PyPDF2
            self.logger.info("Using PyPDF2 text extraction for text-based PDF")
            return self._extract_text_pypdf2(file_path, progress_callback)
        else:
            # Scanned PDF - use OCR
            self.logger.info("Using Gemini Vision OCR for scanned PDF")
            if not HAS_PYMUPDF:
                raise ImportError(
                    "PyMuPDF required for scanned PDF OCR. "
                    "Install with: pip install PyMuPDF"
                )
            return self._extract_text_ocr(file_path, info.page_count, progress_callback)

    def _extract_text_pypdf2(
        self,
        file_path: str,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> str:
        """Extract text using PyPDF2 (for text-based PDFs)."""
        text_parts = []

        with open(file_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            total = len(reader.pages)

            for i, page in enumerate(reader.pages):
                if progress_callback:
                    progress_callback(i + 1, total, f"Extracting page {i + 1}/{total}")

                text = page.extract_text()
                if text and text.strip():
                    text_parts.append(f"--- Page {i + 1} ---\n{text}")

        return '\n\n'.join(text_parts)

    def _extract_text_ocr(
        self,
        file_path: str,
        page_count: int,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> str:
        """Extract text using Gemini Vision OCR (for scanned PDFs)."""
        text_parts = []
        doc = fitz.open(file_path)

        try:
            for i in range(page_count):
                if progress_callback:
                    progress_callback(i + 1, page_count, f"OCR page {i + 1}/{page_count}")

                page = doc[i]
                ocr_result = self._ocr_page(page, i + 1)
                text_parts.append(f"--- Page {i + 1} ---\n{ocr_result}")

        finally:
            doc.close()

        return '\n\n'.join(text_parts)

    def _ocr_page(self, page, page_num: int) -> str:
        """
        Perform OCR on a single PDF page.

        Args:
            page: PyMuPDF page object
            page_num: Page number (for logging)

        Returns:
            Extracted text from the page
        """
        # Calculate optimal DPI based on page size
        rect = page.rect
        page_area = rect.width * rect.height

        # Adjust DPI for large pages to stay under size limit
        dpi = self.DEFAULT_DPI
        if page_area > 500000:  # ~A4 at 72 DPI
            dpi = 120
        if page_area > 1000000:
            dpi = 100

        # Render page to image
        zoom = dpi / 72  # 72 is default PDF DPI
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)

        # Save to temp file
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                tmp.write(pix.tobytes("png"))
                tmp_path = tmp.name

            # Check file size and reduce if needed
            size_mb = os.path.getsize(tmp_path) / (1024 * 1024)
            if size_mb > self.MAX_IMAGE_SIZE_MB:
                self.logger.warning(
                    f"Page {page_num} image too large ({size_mb:.1f}MB), reducing quality"
                )
                # Re-render with lower DPI
                reduced_dpi = max(self.MIN_DPI, int(dpi * 0.7))
                zoom = reduced_dpi / 72
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)
                with open(tmp_path, 'wb') as f:
                    f.write(pix.tobytes("png"))

            # Call Gemini Vision for OCR
            ocr_text = self.api_manager.translate_image(self.OCR_PROMPT, tmp_path)

            if ocr_text and ocr_text.strip():
                return ocr_text.strip()
            else:
                return "[No text detected on this page]"

        except Exception as e:
            self.logger.error(f"OCR failed for page {page_num}: {e}")
            return f"[OCR Error: {str(e)}]"

        finally:
            # Cleanup temp file
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass  # Ignore cleanup errors

    def is_available(self) -> bool:
        """Check if OCR functionality is available."""
        return HAS_PYMUPDF and HAS_PYPDF2

    def get_missing_dependencies(self) -> list:
        """Get list of missing dependencies."""
        missing = []
        if not HAS_PYPDF2:
            missing.append("PyPDF2")
        if not HAS_PYMUPDF:
            missing.append("PyMuPDF")
        return missing
