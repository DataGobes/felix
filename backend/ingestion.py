#!/usr/bin/env python3
"""
RAG Ingestion Worker

Scans /ingest for new/changed/deleted files, processes them into chunks,
generates embeddings via Azure OpenAI, and stores in pgvector.

Uses Docling for document conversion (PDF, markdown, text) and
HybridChunker for structure-aware, token-limited chunking.

Idempotent and resumable - safe to restart mid-run.
"""

import io
import logging
import pandas as pd
import os
import sys
import time
import hashlib
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Set, Tuple
from dataclasses import dataclass, field

import structlog
import tiktoken
from openai import AzureOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential
import requests
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values

import imagehash
from PIL import Image as PILImage

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.chunking import HybridChunker
from docling_core.types.doc.document import (
    DoclingDocument,
    PictureItem,
    TableItem,
    DescriptionAnnotation,
    PictureClassificationData,
)
from docling_core.transforms.chunker.tokenizer.openai import OpenAITokenizer
from docling_core.types.io import DocumentStream
from docling_core.types.doc import (
    ContentLayer,
    GroupItem,
    SectionHeaderItem,
)

# Configure stdlib logging (required for structlog stdlib integration)
logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(message)s")

# Configure structlog
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger("rag-ingestion")


# Configuration from environment
INGEST_PATH = Path(os.getenv("INGEST_PATH", "/ingest"))
IMAGES_PATH = Path(os.getenv("IMAGES_PATH", "/images"))
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "500"))

# Database config
DB_HOST = os.getenv("POSTGRES_HOST", "rag-postgres")
DB_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
DB_USER = os.getenv("POSTGRES_USER", "raguser")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD")
DB_NAME = os.getenv("POSTGRES_DB", "ragdb")

# Azure OpenAI config
AZURE_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01")
AZURE_EMBEDDING_MODEL = os.getenv("AZURE_OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

# Supported file extensions (Docling handles all of these)
SUPPORTED_EXTENSIONS = {".txt", ".md", ".markdown", ".pdf", ".html", ".docx", ".xlsx", ".pptx"}


@dataclass
class ProcessedChunk:
    """A chunk produced by Docling's HybridChunker with metadata."""
    content: str
    contextualized: str
    chunk_index: int
    token_count: int
    char_count: int
    headings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProcessedImage:
    """An image extracted from a document by Docling."""
    image: PILImage.Image
    image_index: int
    page_number: Optional[int] = None
    bbox: Optional[Tuple[float, float, float, float]] = None  # left, top, right, bottom
    bbox_coord_origin: Optional[str] = None
    caption: Optional[str] = None
    label: Optional[str] = None
    phash: str = ""
    sha256: str = ""
    width: int = 0
    height: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProcessedTable:
    """A table extracted from a document by Docling."""
    table_index: int
    num_rows: int = 0
    num_cols: int = 0
    cells: List[Dict[str, Any]] = field(default_factory=list)
    page_number: Optional[int] = None
    bbox: Optional[Tuple[float, float, float, float]] = None
    bbox_coord_origin: Optional[str] = None
    caption: Optional[str] = None
    label: Optional[str] = None
    content_markdown: str = ""
    content_html: str = ""
    content_text: str = ""
    sha256: str = ""


@dataclass
class ProcessedPage:
    """Page metadata from a Docling document."""
    page_number: int
    width: float
    height: float
    element_count: int = 0


@dataclass
class ProcessedLayoutElement:
    """A layout element extracted from a Docling document."""
    self_ref: str
    element_type: str
    content_layer: str
    reading_order: int
    page_number: Optional[int] = None
    bbox: Optional[Tuple[float, float, float, float]] = None
    bbox_coord_origin: Optional[str] = None
    text_preview: Optional[str] = None
    full_text: Optional[str] = None
    heading_level: Optional[int] = None
    parent_ref: Optional[str] = None
    group_label: Optional[str] = None
    children_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversionResult:
    """Full result of document conversion: chunks, images, tables, and layout."""
    chunks: List[ProcessedChunk]
    images: List[ProcessedImage]
    tables: List[ProcessedTable]
    pages: List[ProcessedPage]
    layout_elements: List[ProcessedLayoutElement]


class Database:
    def __init__(self):
        self.conn = None
        self._connect()

    def _connect(self):
        """Establish database connection with retry."""
        max_retries = 10
        for attempt in range(max_retries):
            try:
                self.conn = psycopg2.connect(
                    host=DB_HOST,
                    port=DB_PORT,
                    user=DB_USER,
                    password=DB_PASSWORD,
                    database=DB_NAME,
                    cursor_factory=RealDictCursor
                )
                self.conn.autocommit = False
                logger.info("database_connected", host=DB_HOST, database=DB_NAME)
                return
            except psycopg2.OperationalError as e:
                if attempt < max_retries - 1:
                    wait_time = min(2 ** attempt, 30)
                    logger.warning("database_connection_retry", attempt=attempt + 1, wait=wait_time, error=str(e))
                    time.sleep(wait_time)
                else:
                    raise

    def execute(self, query: str, params: tuple = None) -> List[Dict]:
        """Execute a query and return results."""
        with self.conn.cursor() as cur:
            cur.execute(query, params)
            if cur.description:
                return cur.fetchall()
            return []

    def commit(self):
        self.conn.commit()

    def close(self):
        if self.conn:
            self.conn.close()


class EmbeddingClient:
    def __init__(self):
        self.client = AzureOpenAI(
            azure_endpoint=AZURE_ENDPOINT,
            api_key=AZURE_API_KEY,
            api_version=AZURE_API_VERSION
        )
        self.model = AZURE_EMBEDDING_MODEL

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        reraise=True
    )
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a batch of texts."""
        if not texts:
            return []
        response = self.client.embeddings.create(
            model=self.model,
            input=texts
        )
        return [item.embedding for item in response.data]


def _get_config_value(conn, key, env_var, default):
    """Read a boolean config from pipeline_config table, falling back to env var."""
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT value FROM pipeline_config WHERE key = %s", (key,))
            row = cur.fetchone()
            if row:
                return row["value"].lower() == "true" if isinstance(row, dict) else row[0].lower() == "true"
    except Exception:
        pass
    return os.getenv(env_var, default).lower() == "true"


def _get_config_string(conn, key, env_var, default):
    """Read a string config from pipeline_config table, falling back to env var."""
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT value FROM pipeline_config WHERE key = %s", (key,))
            row = cur.fetchone()
            if row:
                val = row["value"] if isinstance(row, dict) else row[0]
                if val:
                    return val
    except Exception:
        pass
    return os.getenv(env_var, default)


class DoclingProcessor:
    """Handles document conversion and chunking via Docling."""

    def __init__(self, chunk_size: int = CHUNK_SIZE, db=None):
        # Configure PDF pipeline — no OCR for programmatic PDFs
        pdf_options = PdfPipelineOptions()
        pdf_options.do_ocr = False
        pdf_options.generate_picture_images = True
        pdf_options.images_scale = 2.0
        if db and db.conn:
            pdf_options.do_code_enrichment = _get_config_value(
                db.conn, 'enable_code_enrichment', 'ENABLE_CODE_ENRICHMENT', 'true')
            pdf_options.do_formula_enrichment = _get_config_value(
                db.conn, 'enable_formula_enrichment', 'ENABLE_FORMULA_ENRICHMENT', 'true')
            pdf_options.do_picture_description = _get_config_value(
                db.conn, 'enable_picture_description', 'ENABLE_PICTURE_DESCRIPTION', 'false')
            pdf_options.do_picture_classification = _get_config_value(
                db.conn, 'enable_picture_classification', 'ENABLE_PICTURE_CLASSIFICATION', 'false')
        else:
            pdf_options.do_code_enrichment = os.getenv("ENABLE_CODE_ENRICHMENT", "true").lower() == "true"
            pdf_options.do_formula_enrichment = os.getenv("ENABLE_FORMULA_ENRICHMENT", "true").lower() == "true"
            pdf_options.do_picture_description = os.getenv("ENABLE_PICTURE_DESCRIPTION", "false").lower() == "true"
            pdf_options.do_picture_classification = os.getenv("ENABLE_PICTURE_CLASSIFICATION", "false").lower() == "true"

        # Store options for GPU passthrough
        self.pipeline_options = {
            "do_ocr": pdf_options.do_ocr,
            "generate_picture_images": pdf_options.generate_picture_images,
            "images_scale": pdf_options.images_scale,
            "do_code_enrichment": pdf_options.do_code_enrichment,
            "do_formula_enrichment": pdf_options.do_formula_enrichment,
            "do_picture_description": pdf_options.do_picture_description,
            "do_picture_classification": pdf_options.do_picture_classification,
        }

        self.converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_options),
            }
        )

        # Token-aware chunker using the same tokenizer family as the embedding model
        tokenizer = OpenAITokenizer(
            tokenizer=tiktoken.encoding_for_model("text-embedding-3-small"),
            max_tokens=8191,
        )
        self.chunker = HybridChunker(
            tokenizer=tokenizer,
            max_tokens=chunk_size,
            merge_peers=True,
        )

        logger.info("docling_processor_initialized", chunk_size=chunk_size)

    def _make_source(self, filepath: Path):
        """Return a source suitable for DocumentConverter.convert().

        Docling does not recognise .txt as a format, so we wrap plain-text
        files in a DocumentStream with a .md name, which Docling handles
        natively as markdown.
        """
        if filepath.suffix.lower() in {".txt"}:
            data = filepath.read_bytes()
            return DocumentStream(
                name=filepath.stem + ".md",
                stream=io.BytesIO(data),
            )
        return str(filepath)

    def _extract_images(self, doc) -> List[ProcessedImage]:
        """Extract images from a converted Docling document."""
        images = []
        idx = 0
        for item, _level in doc.iterate_items():
            if not isinstance(item, PictureItem):
                continue

            pil_image = item.get_image(doc)
            if pil_image is None:
                continue

            # Provenance: page number and bounding box
            page_number = None
            bbox = None
            bbox_coord_origin = None
            if item.prov and len(item.prov) > 0:
                prov = item.prov[0]
                page_number = prov.page_no
                if prov.bbox:
                    bbox = (prov.bbox.l, prov.bbox.t, prov.bbox.r, prov.bbox.b)
                    bbox_coord_origin = str(prov.bbox.coord_origin) if hasattr(prov.bbox, 'coord_origin') else None

            # Caption and label
            caption = None
            try:
                cap_text = item.caption_text(doc)
                if cap_text:
                    caption = cap_text
            except Exception:
                pass
            label = item.label if hasattr(item, 'label') else None

            # Picture enrichment annotations (description + classification)
            description = None
            classification = None
            if hasattr(item, 'annotations') and item.annotations:
                for ann in item.annotations:
                    if isinstance(ann, DescriptionAnnotation):
                        description = ann.text
                    elif isinstance(ann, PictureClassificationData) and ann.predicted_classes:
                        classification = ann.predicted_classes[0].class_name

            img_metadata = {}
            if description:
                img_metadata['description'] = description
            if classification:
                img_metadata['classification'] = classification

            # Compute hashes
            buf = io.BytesIO()
            pil_image.save(buf, format="PNG")
            png_bytes = buf.getvalue()
            sha256 = hashlib.sha256(png_bytes).hexdigest()
            phash = str(imagehash.phash(pil_image))

            images.append(ProcessedImage(
                image=pil_image,
                image_index=idx,
                page_number=page_number,
                bbox=bbox,
                bbox_coord_origin=bbox_coord_origin,
                caption=caption,
                label=label,
                phash=phash,
                sha256=sha256,
                width=pil_image.width,
                height=pil_image.height,
                metadata=img_metadata,
            ))
            idx += 1

        return images

    def _extract_tables(self, doc) -> "List[ProcessedTable]":
        """Extract tables from a converted Docling document."""
        tables = []
        idx = 0
        for item, _level in doc.iterate_items():
            if not isinstance(item, TableItem):
                continue

            # Provenance: page number and bounding box
            page_number = None
            bbox = None
            bbox_coord_origin = None
            if item.prov and len(item.prov) > 0:
                prov = item.prov[0]
                page_number = prov.page_no
                if prov.bbox:
                    bbox = (prov.bbox.l, prov.bbox.t, prov.bbox.r, prov.bbox.b)
                    bbox_coord_origin = str(prov.bbox.coord_origin) if hasattr(prov.bbox, "coord_origin") else None

            # Caption and label
            caption = None
            try:
                cap_text = item.caption_text(doc)
                if cap_text:
                    caption = cap_text
            except Exception:
                pass
            label = item.label if hasattr(item, "label") else None

            # Export structured content
            try:
                content_markdown = item.export_to_markdown(doc)
            except Exception:
                content_markdown = ""
            try:
                content_html = item.export_to_html(doc)
            except Exception:
                content_html = ""

            # Build triplet text from dataframe
            content_text = ""
            try:
                df = item.export_to_dataframe(doc)
                if df.shape[0] >= 1 and df.shape[1] >= 2:
                    header_row = pd.DataFrame([df.columns.tolist()], columns=df.columns)
                    df = pd.concat([header_row, df], ignore_index=True)
                    rows_list = [str(v).strip() for v in df.iloc[:, 0].to_list()]
                    cols_list = [str(v).strip() for v in df.iloc[0, :].to_list()]
                    triplets = [
                        f"{rows_list[i]}, {cols_list[j]} = {str(df.iloc[i, j]).strip()}"
                        for i in range(1, df.shape[0])
                        for j in range(1, df.shape[1])
                    ]
                    content_text = ". ".join(triplets)
            except Exception:
                pass

            # Dimensions
            num_rows = item.data.num_rows if item.data else 0
            num_cols = item.data.num_cols if item.data else 0

            # Extract cell-level data from grid
            cells = []
            if item.data and item.data.num_rows > 0:
                for r_idx, row in enumerate(item.data.grid):
                    for c_idx, cell in enumerate(row):
                        cells.append({
                            "row_idx": r_idx,
                            "col_idx": c_idx,
                            "text": cell.text,
                            "row_span": cell.row_span,
                            "col_span": cell.col_span,
                            "is_column_header": cell.column_header,
                            "is_row_header": cell.row_header,
                        })

            # Hash of markdown for dedup; fall back to cell content when markdown is empty
            if content_markdown:
                sha256 = hashlib.sha256(content_markdown.encode("utf-8")).hexdigest()
            else:
                cell_fingerprint = f"{num_rows}x{num_cols}:" + "|".join(
                    c["text"] for c in cells
                )
                sha256 = hashlib.sha256(cell_fingerprint.encode("utf-8")).hexdigest()

            tables.append(ProcessedTable(
                table_index=idx,
                num_rows=num_rows,
                num_cols=num_cols,
                page_number=page_number,
                bbox=bbox,
                bbox_coord_origin=bbox_coord_origin,
                caption=caption,
                label=label,
                content_markdown=content_markdown,
                content_html=content_html,
                content_text=content_text,
                sha256=sha256,
                cells=cells,
            ))
            idx += 1

        return tables

    def _extract_layout(self, doc) -> Tuple[List[ProcessedPage], List[ProcessedLayoutElement]]:
        """Extract page metadata and layout elements from a Docling document."""
        pages = []
        for page_no, page_item in doc.pages.items():
            width = page_item.size.width if page_item.size else 0.0
            height = page_item.size.height if page_item.size else 0.0
            pages.append(ProcessedPage(
                page_number=int(page_no),
                width=width,
                height=height,
            ))

        elements = []
        order = 0
        try:
            items_iter = doc.iterate_items(
                with_groups=True,
                included_content_layers={ContentLayer.BODY, ContentLayer.FURNITURE},
            )
        except (TypeError, AttributeError) as e:
            logger.warning("layout_extraction_fallback", error=str(e))
            items_iter = doc.iterate_items()

        for item, _level in items_iter:
            self_ref = str(item.self_ref) if hasattr(item, "self_ref") else f"#/item/{order}"

            # Element type from label
            if isinstance(item, GroupItem):
                element_type = "group"
                group_label = item.label.value if hasattr(item.label, "value") else str(item.label)
            else:
                element_type = item.label.value if hasattr(item.label, "value") else str(item.label)
                group_label = None

            # Content layer
            content_layer = "body"
            if hasattr(item, "content_layer") and item.content_layer is not None:
                content_layer = item.content_layer.value if hasattr(item.content_layer, "value") else str(item.content_layer)

            # Provenance: page number and bounding box
            page_number = None
            bbox = None
            bbox_coord_origin = None
            if hasattr(item, "prov") and item.prov:
                prov = item.prov[0]
                page_number = prov.page_no
                if prov.bbox:
                    bbox = (prov.bbox.l, prov.bbox.t, prov.bbox.r, prov.bbox.b)
                    bbox_coord_origin = prov.bbox.coord_origin.value if hasattr(prov.bbox.coord_origin, "value") else str(prov.bbox.coord_origin)

            # Text content
            text_preview = None
            full_text = None
            if hasattr(item, "text") and item.text:
                text_preview = item.text[:200]
                full_text = item.text

            # Heading level (SectionHeaderItem only)
            heading_level = None
            if isinstance(item, SectionHeaderItem) and hasattr(item, "level"):
                heading_level = item.level

            # Parent reference
            parent_ref = None
            if hasattr(item, "parent") and item.parent is not None:
                parent_ref = str(item.parent.cref) if hasattr(item.parent, "cref") else str(item.parent)

            # Children count
            children_count = 0
            if hasattr(item, "children") and item.children:
                children_count = len(item.children)

            # Enrichment metadata (code language, etc.)
            el_metadata = {}
            if hasattr(item, "code_language") and item.code_language:
                el_metadata["code_language"] = str(item.code_language)

            # Picture enrichment annotations (description + classification)
            if element_type == 'picture' and hasattr(item, 'annotations') and item.annotations:
                for ann in item.annotations:
                    if isinstance(ann, DescriptionAnnotation) and ann.text:
                        el_metadata['description'] = ann.text
                        if not full_text:
                            full_text = ann.text
                            text_preview = ann.text[:200]
                    elif isinstance(ann, PictureClassificationData) and ann.predicted_classes:
                        el_metadata['classification'] = ann.predicted_classes[0].class_name

            elements.append(ProcessedLayoutElement(
                self_ref=self_ref,
                element_type=element_type,
                content_layer=content_layer,
                reading_order=order,
                page_number=page_number,
                bbox=bbox,
                bbox_coord_origin=bbox_coord_origin,
                text_preview=text_preview,
                full_text=full_text,
                heading_level=heading_level,
                parent_ref=parent_ref,
                group_label=group_label,
                children_count=children_count,
                metadata=el_metadata,
            ))
            order += 1

        # Update page element counts
        page_element_counts: Dict[int, int] = {}
        for el in elements:
            if el.page_number is not None:
                page_element_counts[el.page_number] = page_element_counts.get(el.page_number, 0) + 1
        for page in pages:
            page.element_count = page_element_counts.get(page.page_number, 0)

        logger.info("layout_extracted", pages=len(pages), elements=len(elements))
        return pages, elements


    def _convert_remote(self, filepath, gpu_endpoint, gpu_api_key,
                        pipeline_options):
        """Send document to Azure GPU service for async conversion.

        Submits the file, then polls for completion.
        Returns a DoclingDocument on success.
        Raises Exception on failure (caller handles fallback).
        """
        import time as _time
        base = gpu_endpoint.rstrip("/")
        logger.info("gpu_conversion_start", path=str(filepath), endpoint=base)

        headers = {}
        if gpu_api_key:
            headers["X-Api-Key"] = gpu_api_key

        # Step 1: Submit the file (retry for ACA cold start - scale-to-zero returns 404)
        submit_resp = None
        for attempt in range(24):  # up to ~2 min for cold start
            with open(filepath, "rb") as f:
                try:
                    submit_resp = requests.post(
                        f"{base}/convert",
                        files={"file": (filepath.name, f)},
                        data={"options": json.dumps(pipeline_options)},
                        headers=headers,
                        timeout=120,
                    )
                except requests.ConnectionError:
                    submit_resp = None
            if submit_resp is not None and submit_resp.status_code not in (404, 502, 503):
                break
            if attempt < 23:
                logger.info("gpu_cold_start_waiting", attempt=attempt + 1,
                            status=getattr(submit_resp, "status_code", None))
                _time.sleep(5)
        if submit_resp is None:
            raise RuntimeError("GPU service unreachable after cold start wait")
        submit_resp.raise_for_status()
        job_id = submit_resp.json()["job_id"]
        logger.info("gpu_job_submitted", path=str(filepath), job_id=job_id)

        # Step 2: Poll for result (up to 15 minutes)
        poll_interval = 5
        max_wait = 900
        waited = 0
        while waited < max_wait:
            _time.sleep(poll_interval)
            waited += poll_interval

            poll_resp = requests.get(
                f"{base}/jobs/{job_id}",
                headers=headers,
                timeout=30,
            )

            if poll_resp.status_code == 404:
                raise RuntimeError(f"GPU job {job_id} not found")

            data = poll_resp.json()
            status = data.get("status")

            if status == "complete":
                doc = DoclingDocument.model_validate_json(data["document_json"])
                logger.info("gpu_conversion_complete",
                            path=str(filepath), job_id=job_id,
                            time_seconds=data.get("conversion_time_seconds"))
                return doc

            if status == "failed":
                raise RuntimeError(f"GPU conversion failed: {data.get('error')}")

            if waited % 30 == 0:
                elapsed = data.get("elapsed_seconds", waited)
                logger.info("gpu_conversion_polling",
                            job_id=job_id, elapsed=elapsed)

        raise TimeoutError(f"GPU conversion timed out after {max_wait}s")

    def convert_and_chunk(self, filepath: Path, use_gpu: bool = False,
                          gpu_endpoint: str = "", gpu_api_key: str = "",
                          pipeline_options: dict = None) -> Optional[ConversionResult]:
        """Convert a document, chunk it, and extract images, tables, and layout. Returns None on failure."""
        doc = None

        # Attempt GPU conversion if enabled
        if use_gpu and gpu_endpoint:
            try:
                doc = self._convert_remote(
                    filepath, gpu_endpoint, gpu_api_key,
                    pipeline_options or {})
            except Exception as e:
                logger.warning("gpu_conversion_failed_falling_back",
                               path=str(filepath), error=str(e))

        # Local CPU fallback (or primary if GPU not enabled)
        if doc is None:
            try:
                source = self._make_source(filepath)
                result = self.converter.convert(source)
                doc = result.document
            except Exception as e:
                logger.error("docling_conversion_failed", path=str(filepath), error=str(e), exc_info=True)
                return None

        try:
            raw_chunks = list(self.chunker.chunk(dl_doc=doc))
        except Exception as e:
            logger.error("docling_chunking_failed", path=str(filepath), error=str(e))
            return None

        if not raw_chunks:
            return ConversionResult(chunks=[], images=[], tables=[], pages=[], layout_elements=[])

        processed_chunks = []
        for i, chunk in enumerate(raw_chunks):
            contextualized = self.chunker.contextualize(chunk)
            token_count = self.chunker.tokenizer.count_tokens(contextualized)
            headings = list(chunk.meta.headings) if chunk.meta.headings else []

            # Extract page numbers from chunk provenance for image/table linking
            page_numbers = set()
            if chunk.meta.doc_items:
                for doc_item in chunk.meta.doc_items:
                    if hasattr(doc_item, 'prov') and doc_item.prov:
                        for prov in doc_item.prov:
                            if hasattr(prov, 'page_no') and prov.page_no is not None:
                                page_numbers.add(prov.page_no)

            # Collect self_ref pointers from source doc_items for chunk-element linking
            element_refs = []
            if hasattr(chunk.meta, "doc_items") and chunk.meta.doc_items:
                for doc_item in chunk.meta.doc_items:
                    if hasattr(doc_item, "self_ref"):
                        element_refs.append(str(doc_item.self_ref))

            processed_chunks.append(ProcessedChunk(
                content=chunk.text,
                contextualized=contextualized,
                chunk_index=i,
                token_count=token_count,
                char_count=len(contextualized),
                headings=headings,
                metadata={
                    "page_numbers": sorted(page_numbers) if page_numbers else [],
                    "element_refs": element_refs,
                },
            ))

        # Extract images
        images = self._extract_images(doc)
        if images:
            logger.info("images_extracted", path=str(filepath), count=len(images))

        # Extract tables
        tables = self._extract_tables(doc)
        if tables:
            logger.info("tables_extracted", path=str(filepath), count=len(tables))

        # Extract layout (pages + elements)
        pages, layout_elements = self._extract_layout(doc)

        return ConversionResult(
            chunks=processed_chunks,
            images=images,
            tables=tables,
            pages=pages,
            layout_elements=layout_elements,
        )


class FileProcessor:
    def __init__(self, db: Database, embedder: EmbeddingClient, docling: DoclingProcessor):
        self.db = db
        self.embedder = embedder
        self.docling = docling

        # GPU conversion config
        if db and db.conn:
            self.use_gpu = _get_config_value(
                db.conn, 'enable_gpu_conversion', 'ENABLE_GPU_CONVERSION', 'false')
            self.gpu_endpoint = _get_config_string(
                db.conn, 'gpu_endpoint', 'GPU_CONVERT_ENDPOINT', '')
        else:
            self.use_gpu = os.getenv('ENABLE_GPU_CONVERSION', 'false').lower() == 'true'
            self.gpu_endpoint = os.getenv('GPU_CONVERT_ENDPOINT', '')
        self.gpu_api_key = os.getenv('GPU_CONVERT_API_KEY', '')

        if self.use_gpu and self.gpu_endpoint:
            logger.info("gpu_conversion_enabled", endpoint=self.gpu_endpoint)
        elif self.use_gpu and not self.gpu_endpoint:
            logger.warning("gpu_conversion_enabled_but_no_endpoint")

    def compute_sha256(self, filepath: Path) -> str:
        """Compute SHA256 hash of file contents."""
        sha256_hash = hashlib.sha256()
        with open(filepath, "rb") as f:
            for block in iter(lambda: f.read(8192), b""):
                sha256_hash.update(block)
        return sha256_hash.hexdigest()

    def get_existing_document(self, path: str, index_id: int = None) -> Optional[Dict]:
        """Get existing document record by path, optionally scoped to an index."""
        if index_id is not None:
            results = self.db.execute(
                "SELECT id, sha256, ingested_at FROM documents WHERE path = %s AND index_id = %s",
                (path, index_id)
            )
        else:
            results = self.db.execute(
                "SELECT id, sha256, ingested_at FROM documents WHERE path = %s",
                (path,)
            )
        return results[0] if results else None

    def get_all_document_paths(self) -> Set[str]:
        """Get all document paths from database."""
        results = self.db.execute("SELECT path FROM documents")
        return {row["path"] for row in results}

    def _update_job_status(self, filename, index_slug, status, progress=None, error_message=None, document_id=None):
        """Update ingestion_jobs row. Commits immediately for cross-container visibility."""
        try:
            sets = ["status = %s", "updated_at = NOW()"]
            params = [status]

            if progress:
                sets.append("progress = progress || %s::jsonb")
                params.append(json.dumps(progress))

            if error_message is not None:
                sets.append("error_message = %s")
                params.append(error_message)

            if document_id is not None:
                sets.append("document_id = %s")
                params.append(document_id)

            # Set started_at on first transition out of queued
            sets.append("started_at = COALESCE(started_at, CASE WHEN %s != 'queued' THEN NOW() ELSE NULL END)")
            params.append(status)

            if status in ('completed', 'failed'):
                sets.append("completed_at = NOW()")

            params.extend([filename, index_slug])

            query = (
                f"UPDATE ingestion_jobs SET {', '.join(sets)} "
                f"WHERE filename = %s AND index_slug = %s "
                f"AND status NOT IN ('completed', 'failed')"
            )
            self.db.execute(query, tuple(params))
            self.db.commit()
        except Exception as e:
            logger.warning("job_status_update_failed", filename=filename, error=str(e))
            try:
                self.db.conn.rollback()
            except Exception:
                pass

    def process_file(self, filepath: Path, index_id: int = None) -> bool:
        """Process a single file: convert, chunk, embed, store. Returns True if successful."""
        rel_path = str(filepath.relative_to(INGEST_PATH))
        _job_slug = rel_path.split("/")[0] if "/" in rel_path else "default"
        _job_fname = filepath.name

        if not filepath.exists():
            logger.warning("file_not_found", path=rel_path)
            return False

        self._update_job_status(_job_fname, _job_slug, "hashing")
        try:
            file_hash = self.compute_sha256(filepath)
        except Exception as e:
            logger.error("hash_computation_failed", path=rel_path, error=str(e))
            self._update_job_status(_job_fname, _job_slug, "failed", error_message=f"Hash failed: {e}")
            return False

        existing = self.get_existing_document(rel_path)
        if existing and existing["sha256"] == file_hash:
            logger.debug("file_unchanged", path=rel_path, hash=file_hash[:16])
            return True

        # Convert, chunk, and extract images/tables/layout via Docling
        self._update_job_status(_job_fname, _job_slug, "converting", progress={"sha256": file_hash[:16], "gpu": self.use_gpu and bool(self.gpu_endpoint)})
        conversion = self.docling.convert_and_chunk(
            filepath,
            use_gpu=self.use_gpu,
            gpu_endpoint=self.gpu_endpoint,
            gpu_api_key=self.gpu_api_key,
            pipeline_options=self.docling.pipeline_options,
        )
        if conversion is None:
            return False
        if not conversion.chunks:
            logger.warning("no_chunks_generated", path=rel_path)
            self._update_job_status(_job_fname, _job_slug, "failed", error_message="No chunks generated")
            return False

        stat = filepath.stat()
        file_size = stat.st_size
        last_modified = datetime.fromtimestamp(stat.st_mtime)

        logger.info("processing_file",
                     path=rel_path,
                     size=file_size,
                     hash=file_hash[:16],
                     chunks=len(conversion.chunks),
                     images=len(conversion.images),
                     tables=len(conversion.tables),
                     action="update" if existing else "insert")

        self._update_job_status(_job_fname, _job_slug, "chunking", progress={"total_chunks": len(conversion.chunks)})

        # Delete old document if updating (cascades to chunks/embeddings/images)
        if existing:
            self._cleanup_document_images(existing["id"])
            self.db.execute("DELETE FROM documents WHERE id = %s", (existing["id"],))
            self.db.commit()

        # Insert document
        self.db.execute(
            """INSERT INTO documents (path, sha256, file_size, last_modified, metadata, index_id)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (rel_path, file_hash, file_size, last_modified,
             json.dumps({"extension": filepath.suffix.lower()}), index_id)
        )
        result = self.db.execute("SELECT id FROM documents WHERE path = %s", (rel_path,))
        doc_id = result[0]["id"]

        # Process chunks in batches, collecting chunk_id mapping
        all_chunk_ids: Dict[int, int] = {}  # chunk_index -> chunk_id
        batch_size = 100
        for i in range(0, len(conversion.chunks), batch_size):
            batch = conversion.chunks[i:i + batch_size]
            self._update_job_status(_job_fname, _job_slug, "embedding",
                                    progress={"embedded": i, "total_chunks": len(conversion.chunks), "batch": i // batch_size + 1})
            batch_ids = self._process_chunk_batch(doc_id, batch)
            all_chunk_ids.update(batch_ids)

        # Process images: save to filesystem, insert to DB, link to chunks
        if conversion.images:
            self._update_job_status(_job_fname, _job_slug, "storing_images")
            self._process_images(doc_id, conversion.images, all_chunk_ids, conversion.chunks)

        # Process tables: insert to DB, link to chunks
        if conversion.tables:
            self._update_job_status(_job_fname, _job_slug, "storing_tables")
            self._process_tables(doc_id, conversion.tables, all_chunk_ids, conversion.chunks)

        # Process layout data (pages, elements, chunk-element links)
        self._update_job_status(_job_fname, _job_slug, "storing_layout")
        self._process_layout(
            doc_id, conversion.pages, conversion.layout_elements,
            all_chunk_ids, conversion.chunks,
        )

        self.db.commit()
        self._update_job_status(_job_fname, _job_slug, "completed",
                                progress={"total_chunks": len(conversion.chunks),
                                          "images": len(conversion.images),
                                          "tables": len(conversion.tables),
                                          "pages": len(conversion.pages)},
                                document_id=doc_id)
        logger.info("file_ingested", path=rel_path,
                     chunks=len(conversion.chunks),
                     images=len(conversion.images),
                     tables=len(conversion.tables),
                     pages=len(conversion.pages),
                     layout_elements=len(conversion.layout_elements))
        return True

    def _process_chunk_batch(self, doc_id: int, chunks: List[ProcessedChunk]) -> Dict[int, int]:
        """Process a batch of chunks: insert chunks, generate embeddings, insert embeddings.

        Returns a mapping of chunk_index -> chunk_id for image/table/layout linking.
        """
        # Insert chunks (store contextualized text as content for search display)
        chunk_values = [
            (doc_id, c.chunk_index, c.contextualized, c.token_count, c.char_count,
             c.headings, json.dumps(c.metadata))
            for c in chunks
        ]

        with self.db.conn.cursor() as cur:
            execute_values(
                cur,
                """INSERT INTO chunks (document_id, chunk_index, content, token_count, char_count, headings, metadata)
                   VALUES %s RETURNING id, chunk_index""",
                chunk_values
            )
            chunk_ids = {row["chunk_index"]: row["id"] for row in cur.fetchall()}

        # Generate embeddings from contextualized text (includes heading context)
        texts = [c.contextualized for c in chunks]
        embeddings = self.embedder.embed_batch(texts)

        # Insert embeddings
        embedding_values = [
            (chunk_ids[c.chunk_index], json.dumps(emb), AZURE_EMBEDDING_MODEL)
            for c, emb in zip(chunks, embeddings)
        ]

        with self.db.conn.cursor() as cur:
            execute_values(
                cur,
                """INSERT INTO embeddings (chunk_id, embedding, model)
                   VALUES %s""",
                embedding_values,
                template="(%s, %s::vector, %s)"
            )

        self.db.commit()
        return chunk_ids

    def _process_images(self, doc_id: int, images: List[ProcessedImage],
                        chunk_ids: Dict[int, int], chunks: List[ProcessedChunk]):
        """Save images to filesystem, insert into DB, and link to chunks."""
        doc_dir = IMAGES_PATH / str(doc_id)
        doc_dir.mkdir(parents=True, exist_ok=True)

        for img in images:
            # Save to filesystem
            filename = f"img_{img.image_index:04d}.png"
            file_path = doc_dir / filename
            img.image.save(str(file_path), format="PNG")
            file_size = file_path.stat().st_size
            rel_path = f"{doc_id}/{filename}"

            # Release PIL memory
            img.image.close()
            img.image = None

            # Insert into images table
            bbox_left = img.bbox[0] if img.bbox else None
            bbox_top = img.bbox[1] if img.bbox else None
            bbox_right = img.bbox[2] if img.bbox else None
            bbox_bottom = img.bbox[3] if img.bbox else None

            result = self.db.execute(
                """INSERT INTO images (document_id, file_path, file_size, mime_type,
                       width, height, page_number,
                       bbox_left, bbox_top, bbox_right, bbox_bottom, bbox_coord_origin,
                       caption, label, image_index, phash, sha256, metadata)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING id""",
                (doc_id, rel_path, file_size, "image/png",
                 img.width, img.height, img.page_number,
                 bbox_left, bbox_top, bbox_right, bbox_bottom, img.bbox_coord_origin,
                 img.caption, img.label, img.image_index, img.phash, img.sha256,
                 json.dumps(img.metadata) if img.metadata else '{}')
            )
            image_id = result[0]["id"]

            # Link image to chunks (Phase 4)
            self._link_image_to_chunks(image_id, img, chunk_ids, chunks)

        logger.info("images_stored", doc_id=doc_id, count=len(images),
                     directory=str(doc_dir))

    def _link_image_to_chunks(self, image_id: int, img: ProcessedImage,
                              chunk_ids: Dict[int, int], chunks: List[ProcessedChunk]):
        """Create chunk-image relationships based on page proximity and caption references."""
        if img.page_number is None:
            return

        for chunk in chunks:
            chunk_pages = set(chunk.metadata.get("page_numbers", []))
            if not chunk_pages:
                continue

            chunk_id = chunk_ids.get(chunk.chunk_index)
            if chunk_id is None:
                continue

            relationship = None

            # Caption reference: chunk text contains the image caption
            if img.caption and img.caption.lower() in chunk.content.lower():
                relationship = "caption_reference"
            # Same page
            elif img.page_number in chunk_pages:
                relationship = "same_page"
            # Adjacent page (within 1 page)
            elif any(abs(img.page_number - p) == 1 for p in chunk_pages):
                relationship = "adjacent_page"

            if relationship:
                self.db.execute(
                    """INSERT INTO chunk_images (chunk_id, image_id, relationship_type)
                       VALUES (%s, %s, %s) ON CONFLICT (chunk_id, image_id) DO NOTHING""",
                    (chunk_id, image_id, relationship)
                )


    def _process_tables(self, doc_id: int, tables: "List[ProcessedTable]",
                        chunk_ids: "Dict[int, int]", chunks: "List[ProcessedChunk]"):
        """Insert tables into DB and link to chunks."""
        for tbl in tables:
            bbox_left = tbl.bbox[0] if tbl.bbox else None
            bbox_top = tbl.bbox[1] if tbl.bbox else None
            bbox_right = tbl.bbox[2] if tbl.bbox else None
            bbox_bottom = tbl.bbox[3] if tbl.bbox else None

            result = self.db.execute(
                """INSERT INTO tables (document_id, table_index, num_rows, num_cols,
                       page_number, bbox_left, bbox_top, bbox_right, bbox_bottom,
                       bbox_coord_origin, caption, label,
                       content_markdown, content_html, content_text, sha256)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING id""",
                (doc_id, tbl.table_index, tbl.num_rows, tbl.num_cols,
                 tbl.page_number, bbox_left, bbox_top, bbox_right, bbox_bottom,
                 tbl.bbox_coord_origin, tbl.caption, tbl.label,
                 tbl.content_markdown, tbl.content_html, tbl.content_text, tbl.sha256)
            )
            table_id = result[0]["id"]

            # Insert cells
            if tbl.cells:
                cell_values = [
                    (table_id, c["row_idx"], c["col_idx"], c["text"],
                     c["row_span"], c["col_span"],
                     c["is_column_header"], c["is_row_header"])
                    for c in tbl.cells
                ]
                with self.db.conn.cursor() as cur:
                    execute_values(
                        cur,
                        """INSERT INTO table_cells
                               (table_id, row_idx, col_idx, text, row_span, col_span,
                                is_column_header, is_row_header)
                           VALUES %s ON CONFLICT (table_id, row_idx, col_idx) DO NOTHING""",
                        cell_values
                    )

            self._link_table_to_chunks(table_id, tbl, chunk_ids, chunks)

        logger.info("tables_stored", doc_id=doc_id, count=len(tables))

    def _link_table_to_chunks(self, table_id: int, tbl: "ProcessedTable",
                              chunk_ids: "Dict[int, int]", chunks: "List[ProcessedChunk]"):
        """Create chunk-table relationships based on page proximity and caption references."""
        if tbl.page_number is None:
            return

        for chunk in chunks:
            chunk_pages = set(chunk.metadata.get("page_numbers", []))
            if not chunk_pages:
                continue

            chunk_id = chunk_ids.get(chunk.chunk_index)
            if chunk_id is None:
                continue

            relationship = None

            if tbl.caption and tbl.caption.lower() in chunk.content.lower():
                relationship = "caption_reference"
            elif tbl.page_number in chunk_pages:
                relationship = "same_page"
            elif any(abs(tbl.page_number - p) == 1 for p in chunk_pages):
                relationship = "adjacent_page"

            if relationship:
                self.db.execute(
                    """INSERT INTO chunk_tables (chunk_id, table_id, relationship_type)
                       VALUES (%s, %s, %s) ON CONFLICT (chunk_id, table_id) DO NOTHING""",
                    (chunk_id, table_id, relationship)
                )

    def _cleanup_document_images(self, doc_id: int):
        """Remove image files from filesystem for a document."""
        # Query file paths before DB cascade deletes them
        results = self.db.execute(
            "SELECT file_path FROM images WHERE document_id = %s", (doc_id,)
        )
        for row in results:
            full_path = IMAGES_PATH / row["file_path"]
            try:
                full_path.unlink(missing_ok=True)
            except Exception as e:
                logger.warning("image_file_delete_failed", path=str(full_path), error=str(e))

        # Remove the document's image directory if empty
        doc_dir = IMAGES_PATH / str(doc_id)
        if doc_dir.exists():
            try:
                doc_dir.rmdir()  # only removes if empty
            except OSError:
                pass

    def _process_layout(
        self,
        doc_id: int,
        pages: List[ProcessedPage],
        elements: List[ProcessedLayoutElement],
        chunk_ids: Dict[int, int],
        chunks: List[ProcessedChunk],
    ):
        """Store layout data: pages, elements, and chunk-element junction rows."""
        if not pages and not elements:
            return

        # 1. Insert pages
        # Note: fetch=True is required so execute_values collects RETURNING
        # rows from all pages (without it, only the last page is returned).
        page_id_map: Dict[int, int] = {}
        if pages:
            page_values = [
                (doc_id, p.page_number, p.width, p.height, p.element_count)
                for p in pages
            ]
            with self.db.conn.cursor() as cur:
                rows = execute_values(
                    cur,
                    """INSERT INTO pages (document_id, page_number, width, height, element_count)
                       VALUES %s RETURNING id, page_number""",
                    page_values,
                    fetch=True,
                )
                for row in rows:
                    page_id_map[row["page_number"]] = row["id"]

        # 2. Insert layout elements
        element_id_map: Dict[str, int] = {}
        if elements:
            element_values = [
                (
                    doc_id,
                    page_id_map.get(el.page_number),
                    el.self_ref,
                    el.element_type,
                    el.content_layer,
                    el.reading_order,
                    el.page_number,
                    el.bbox[0] if el.bbox else None,
                    el.bbox[1] if el.bbox else None,
                    el.bbox[2] if el.bbox else None,
                    el.bbox[3] if el.bbox else None,
                    el.bbox_coord_origin,
                    el.text_preview,
                    el.full_text,
                    el.heading_level,
                    el.parent_ref,
                    el.group_label,
                    el.children_count,
                    json.dumps(el.metadata) if el.metadata else '{}',
                )
                for el in elements
            ]
            with self.db.conn.cursor() as cur:
                rows = execute_values(
                    cur,
                    """INSERT INTO layout_elements
                       (document_id, page_id, self_ref, element_type, content_layer,
                        reading_order, page_number, bbox_left, bbox_top, bbox_right,
                        bbox_bottom, bbox_coord_origin, text_preview, full_text,
                        heading_level, parent_ref, group_label, children_count, metadata)
                       VALUES %s RETURNING id, self_ref""",
                    element_values,
                    fetch=True,
                )
                for row in rows:
                    element_id_map[row["self_ref"]] = row["id"]

        # 3. Insert chunk-element junction rows
        junction_count = 0
        if element_id_map and chunk_ids:
            junction_values = []
            for chunk in chunks:
                chunk_db_id = chunk_ids.get(chunk.chunk_index)
                if not chunk_db_id:
                    continue
                for ref in chunk.metadata.get("element_refs", []):
                    element_db_id = element_id_map.get(ref)
                    if element_db_id:
                        junction_values.append((chunk_db_id, element_db_id))

            if junction_values:
                with self.db.conn.cursor() as cur:
                    execute_values(
                        cur,
                        """INSERT INTO chunk_elements (chunk_id, element_id)
                           VALUES %s ON CONFLICT DO NOTHING""",
                        junction_values,
                    )
                junction_count = len(junction_values)

        logger.info("layout_stored",
                     pages=len(page_id_map),
                     elements=len(element_id_map),
                     chunk_links=junction_count)

    def delete_document(self, path: str):
        """Delete document and its chunks/embeddings/images from database."""
        logger.info("deleting_document", path=path)
        # Clean up image files before DB cascade
        results = self.db.execute("SELECT id FROM documents WHERE path = %s", (path,))
        if results:
            self._cleanup_document_images(results[0]["id"])
        self.db.execute("DELETE FROM documents WHERE path = %s", (path,))
        self.db.commit()



def _ensure_index(conn, slug, display_name=None):
    """Upsert an index row, return its id."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO indexes (slug, display_name) VALUES (%s, %s) "
            "ON CONFLICT (slug) DO NOTHING",
            (slug, display_name or slug.replace("-", " ").title()),
        )
        conn.commit()
        cur.execute("SELECT id FROM indexes WHERE slug = %s", (slug,))
        return cur.fetchone()["id"]


class IngestionWorker:
    def __init__(self):
        self.db = Database()
        self.embedder = EmbeddingClient()
        self.docling = DoclingProcessor(db=self.db)
        self.processor = FileProcessor(self.db, self.embedder, self.docling)
        self.running = True

    def scan_files(self) -> List[Path]:
        """Scan ingest directory for supported files."""
        files = []
        if not INGEST_PATH.exists():
            logger.warning("ingest_path_not_found", path=str(INGEST_PATH))
            return files

        for ext in SUPPORTED_EXTENSIONS:
            files.extend(INGEST_PATH.rglob(f"*{ext}"))

        return files

    def full_sync(self):
        """Perform a full sync: ingest new/changed files, delete removed ones.

        Supports multi-index via subfolders:
        - Root-level files -> 'default' index
        - Subdirectories -> each is an index slug
        """
        logger.info("starting_full_sync")

        # Collect (filepath, index_slug) pairs
        files_with_index = []

        # Root-level files -> 'default' index
        for f in INGEST_PATH.iterdir():
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS:
                files_with_index.append((f, "default"))

        # Subdirectories -> each is an index slug
        for subdir in sorted(INGEST_PATH.iterdir()):
            if subdir.is_dir() and not subdir.name.startswith("."):
                slug = subdir.name
                for f in subdir.iterdir():
                    if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS:
                        files_with_index.append((f, slug))

        current_paths = {str(f.relative_to(INGEST_PATH)) for f, _ in files_with_index}
        db_paths = self.processor.get_all_document_paths()

        # Delete removed files
        deleted_paths = db_paths - current_paths
        for path in deleted_paths:
            self.processor.delete_document(path)

        # Process current files
        processed = 0
        failed = 0
        skipped = 0

        for filepath, index_slug in files_with_index:
            rel_path = str(filepath.relative_to(INGEST_PATH))
            index_id = _ensure_index(self.db.conn, index_slug)
            existing = self.processor.get_existing_document(rel_path, index_id)

            if existing:
                try:
                    current_hash = self.processor.compute_sha256(filepath)
                    if current_hash == existing["sha256"]:
                        skipped += 1
                        continue
                except Exception as e:
                    logger.error("hash_check_failed", path=rel_path, error=str(e))
                    failed += 1
                    continue

            if self.processor.process_file(filepath, index_id):
                processed += 1
            else:
                failed += 1

        logger.info("full_sync_complete",
                     processed=processed,
                     skipped=skipped,
                     failed=failed,
                     deleted=len(deleted_paths))

    def run(self, once=False):
        """Run ingestion. If once=True, do a single sync and exit."""
        logger.info("ingestion_worker_started",
                     ingest_path=str(INGEST_PATH),
                     chunk_size=CHUNK_SIZE,
                     mode="one_shot" if once else "continuous")

        try:
            self.full_sync()
        except Exception as e:
            logger.error("sync_failed", error=str(e), exc_info=True)
            self.db.close()
            return

        if once:
            logger.info("one_shot_complete")
            self.db.close()
            return

        # Continuous sync loop (kept for backwards compat / dev)
        while self.running:
            try:
                time.sleep(60)
                self.full_sync()
            except KeyboardInterrupt:
                logger.info("shutting_down")
                self.running = False
            except Exception as e:
                logger.error("sync_error", error=str(e), exc_info=True)
                time.sleep(10)

        self.db.close()


def main():
    missing = []
    if not AZURE_ENDPOINT:
        missing.append("AZURE_OPENAI_ENDPOINT")
    if not AZURE_API_KEY:
        missing.append("AZURE_OPENAI_API_KEY")
    if not DB_PASSWORD:
        missing.append("POSTGRES_PASSWORD")

    if missing:
        logger.error("missing_configuration", variables=missing)
        sys.exit(1)

    once = "--once" in sys.argv
    worker = IngestionWorker()
    worker.run(once=once)


if __name__ == "__main__":
    main()
