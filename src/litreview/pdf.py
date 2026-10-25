"""PDF download and content extraction (text + figure inventory).

Requires the ``pdf`` extra (pymupdf). Import errors surface a readable hint.
"""

from __future__ import annotations

import re
from pathlib import Path

import httpx

from .models import FigureCard, PaperContent

CAPTION_RE = re.compile(
    r"^\s*((figure|fig\.?|table|algorithm|图|表|算法)\s*[0-9IVX]+)[:.\s]?\s*(.{0,400})",
    re.IGNORECASE)
MAX_PDF_MB = 25


class PdfError(RuntimeError):
    pass


def download_pdf(url: str, dest: str | Path, *, client: httpx.Client | None = None,
                 max_mb: int = MAX_PDF_MB) -> Path:
    """Stream a PDF to ``dest`` with a hard size cap."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    own_client = client is None
    client = client or httpx.Client(timeout=60.0, follow_redirects=True,
                                    headers={"User-Agent": "lit-review-agent"})
    try:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            length = int(response.headers.get("content-length") or 0)
            if length > max_mb << 20:
                raise PdfError(f"PDF too large: {length >> 20} MB > {max_mb} MB")
            written = 0
            with open(dest, "wb") as handle:
                for chunk in response.iter_bytes(1 << 16):
                    written += len(chunk)
                    if written > max_mb << 20:
                        raise PdfError(f"PDF exceeded {max_mb} MB while streaming")
                    handle.write(chunk)
    except httpx.HTTPError as error:
        dest.unlink(missing_ok=True)
        raise PdfError(f"download failed: {url} ({error})") from error
    finally:
        if own_client:
            client.close()
    if dest.stat().st_size < 1024:
        dest.unlink(missing_ok=True)
        raise PdfError(f"not a PDF payload: {url}")
    return dest


def _caption_near(page, bbox) -> str:
    """Best-effort caption: text block just below (or above) the image bbox."""
    candidates = []
    for block in page.get_text("blocks"):
        x0, y0, x1, y1, text = block[:5]
        match = CAPTION_RE.match(text.replace("\n", " "))
        if not match:
            continue
        below = y0 >= bbox[3] - 8 and y0 - bbox[3] < 90
        above = y1 <= bbox[1] + 8 and bbox[1] - y1 < 90
        x_overlap = min(x1, bbox[2]) - max(x0, bbox[0]) > 0
        if x_overlap and (below or above):
            distance = abs(y0 - bbox[3]) if below else abs(bbox[1] - y1)
            candidates.append((distance, " ".join(match.groups()).strip()))
    if not candidates:
        return ""
    return min(candidates)[1][:300]


def extract_content(pdf_path: str | Path, paper_id: str) -> PaperContent:
    """Extract page text plus figure/table candidates with bound captions."""
    try:
        import fitz  # pymupdf
    except ImportError as error:  # pragma: no cover
        raise PdfError('missing dependency: pip install "lit-review-agent[pdf]"') from error
    doc = fitz.open(pdf_path)
    try:
        pages_text, figures, seen_xrefs = [], [], set()
        for page_index, page in enumerate(doc, start=1):
            text = page.get_text("text")
            pages_text.append(text)
            for image in page.get_images(full=True):
                xref = image[0]
                if xref in seen_xrefs:
                    continue
                seen_xrefs.add(xref)
                rects = page.get_image_rects(xref)
                if not rects:
                    continue
                rect = rects[0]
                width_px, height_px = image[2], image[3]
                caption = _caption_near(page, (rect.x0, rect.y0, rect.x1, rect.y1))
                kind = "table" if re.match(r"(?i)^(table|表)", caption) else "figure"
                figures.append(FigureCard(
                    paper_id=paper_id, kind=kind, page=page_index,
                    caption=caption, width_px=width_px, height_px=height_px))
        full_text = "\n".join(pages_text)
        return PaperContent(paper_id=paper_id, pages=doc.page_count,
                            text_chars=len(full_text), text=full_text,
                            figures=figures)
    finally:
        doc.close()


def save_figure_images(pdf_path: str | Path, content: PaperContent,
                       out_dir: str | Path, *, max_bytes: int = 8 << 20) -> list[Path]:
    """Dump each real figure to ``out_dir`` as ``<paper_id>_p<page>_<n>.png``."""
    import fitz
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(pdf_path)
    saved = []
    try:
        counter = 0
        for card in content.figures:
            if not card.is_likely_real:
                continue
            page = doc[card.page - 1]
            for image in page.get_images(full=True):
                if image[2] < card.width_px - 2 or image[3] < card.height_px - 2:
                    continue
                try:
                    pix = fitz.Pixmap(doc, image[0])
                    if pix.n - pix.alpha > 3:
                        pix = fitz.Pixmap(fitz.csRGB, pix)
                    target = out_dir / f"{card.paper_id.replace('/', '_')}_p{card.page:02d}_{counter:02d}.png"
                    pix.save(target)
                    pix = None
                    if target.stat().st_size <= max_bytes:
                        saved.append(target)
                        counter += 1
                except (RuntimeError, ValueError):
                    continue
                break
    finally:
        doc.close()
    return saved
