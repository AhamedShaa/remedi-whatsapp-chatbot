import asyncio
import base64
import io
from functools import partial

import pdfplumber

from utils.logger import logger


class PDFExtractionError(Exception):
    pass


class PDFExtractor:
    async def extract_text(self, pdf_bytes: bytes) -> str:
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(None, partial(self._extract_sync, pdf_bytes))
        if not text.strip():
            raise PDFExtractionError(
                "Could not extract text from PDF. "
                "The file may be scanned or corrupted."
            )
        return text

    def _extract_sync(self, pdf_bytes: bytes) -> str:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        raw = "\n".join(pages)
        # Normalise whitespace: collapse runs of blank lines, strip trailing spaces
        lines = [line.rstrip() for line in raw.splitlines()]
        cleaned_lines = []
        blank_run = 0
        for line in lines:
            if line == "":
                blank_run += 1
                if blank_run <= 1:
                    cleaned_lines.append(line)
            else:
                blank_run = 0
                cleaned_lines.append(line)
        return "\n".join(cleaned_lines)

    async def extract_from_base64(self, b64_string: str) -> str:
        pdf_bytes = base64.b64decode(b64_string)
        return await self.extract_text(pdf_bytes)


pdf_extractor = PDFExtractor()
