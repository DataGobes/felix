"""Tests for the RAG Ingestion Worker (ingestion.py).

Tests pure logic: dataclass construction, hash computation, metadata building,
layout extraction helpers. Docling and DB are mocked.
"""

import hashlib
import io
import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Import ingestion module — needs env vars set first
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _set_env(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("POSTGRES_PASSWORD", "test-password")
    monkeypatch.setenv("POSTGRES_HOST", "localhost")
    monkeypatch.setenv("INGEST_PATH", "/tmp/test-ingest")
    monkeypatch.setenv("IMAGES_PATH", "/tmp/test-images")


# ── Dataclass tests ───────────────────────────────────────────────────────


def test_processed_chunk_construction():
    from ingestion import ProcessedChunk

    chunk = ProcessedChunk(
        content="Hello world",
        contextualized="# Intro\nHello world",
        chunk_index=0,
        token_count=5,
        char_count=20,
        headings=["Intro"],
        metadata={"element_refs": ["#/texts/0"], "page_numbers": [1]},
    )
    assert chunk.content == "Hello world"
    assert chunk.chunk_index == 0
    assert chunk.metadata["element_refs"] == ["#/texts/0"]
    assert chunk.metadata["page_numbers"] == [1]


def test_processed_page_construction():
    from ingestion import ProcessedPage

    page = ProcessedPage(page_number=1, width=612.0, height=792.0, element_count=10)
    assert page.page_number == 1
    assert page.width == 612.0
    assert page.element_count == 10


def test_processed_page_default_element_count():
    from ingestion import ProcessedPage

    page = ProcessedPage(page_number=1, width=612.0, height=792.0)
    assert page.element_count == 0


def test_processed_layout_element_construction():
    from ingestion import ProcessedLayoutElement

    el = ProcessedLayoutElement(
        self_ref="#/texts/5",
        element_type="section_header",
        content_layer="body",
        reading_order=5,
        page_number=2,
        bbox=(72.0, 700.0, 540.0, 680.0),
        text_preview="Background",
        heading_level=2,
    )
    assert el.self_ref == "#/texts/5"
    assert el.element_type == "section_header"
    assert el.heading_level == 2
    assert el.bbox == (72.0, 700.0, 540.0, 680.0)


def test_processed_layout_element_defaults():
    from ingestion import ProcessedLayoutElement

    el = ProcessedLayoutElement(
        self_ref="#/texts/0",
        element_type="text",
        content_layer="body",
        reading_order=0,
    )
    assert el.page_number is None
    assert el.bbox is None
    assert el.heading_level is None
    assert el.children_count == 0


def test_processed_image_construction():
    from ingestion import ProcessedImage
    from PIL import Image as PILImage

    img = PILImage.new("RGB", (100, 50))
    pi = ProcessedImage(
        image=img, image_index=0, page_number=1,
        bbox=(10.0, 20.0, 90.0, 80.0),
        phash="abc123", sha256="def456",
        width=100, height=50,
    )
    assert pi.image_index == 0
    assert pi.width == 100
    assert pi.phash == "abc123"
    img.close()


def test_processed_table_construction():
    from ingestion import ProcessedTable

    tbl = ProcessedTable(
        table_index=0, num_rows=3, num_cols=2,
        content_markdown="| A | B |",
        sha256="abc123",
        cells=[{"row_idx": 0, "col_idx": 0, "text": "A"}],
    )
    assert tbl.num_rows == 3
    assert len(tbl.cells) == 1


def test_conversion_result_has_all_fields():
    from ingestion import ConversionResult, ProcessedChunk, ProcessedImage, ProcessedTable, ProcessedPage, ProcessedLayoutElement

    result = ConversionResult(
        chunks=[], images=[], tables=[], pages=[], layout_elements=[],
    )
    assert result.chunks == []
    assert result.images == []
    assert result.tables == []
    assert result.pages == []
    assert result.layout_elements == []


# ── Hash computation ──────────────────────────────────────────────────────


def test_compute_sha256():
    from ingestion import FileProcessor

    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        f.write(b"Hello RAG world")
        f.flush()
        path = Path(f.name)

    processor = MagicMock(spec=FileProcessor)
    processor.compute_sha256 = FileProcessor.compute_sha256

    expected = hashlib.sha256(b"Hello RAG world").hexdigest()
    assert processor.compute_sha256(processor, path) == expected
    path.unlink()


def test_compute_sha256_large_file():
    """Ensure hashing works for files larger than the 8192 block size."""
    from ingestion import FileProcessor

    data = b"x" * 20000  # Larger than 8192 block
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
        f.write(data)
        f.flush()
        path = Path(f.name)

    processor = MagicMock(spec=FileProcessor)
    processor.compute_sha256 = FileProcessor.compute_sha256

    expected = hashlib.sha256(data).hexdigest()
    assert processor.compute_sha256(processor, path) == expected
    path.unlink()


# ── Layout extraction logic ───────────────────────────────────────────────


def _make_mock_doc(pages_dict, items):
    """Build a mock Docling document with pages and iterate_items()."""
    doc = MagicMock()
    doc.pages = pages_dict

    def _iterate_items(**kwargs):
        return iter(items)

    doc.iterate_items = _iterate_items
    return doc


def _make_mock_page(width, height):
    """Create a mock page with size."""
    page = MagicMock()
    page.size = MagicMock()
    page.size.width = width
    page.size.height = height
    return page


def _make_mock_item(self_ref, label_value, prov_page=None, prov_bbox=None,
                     text=None, content_layer_value="body", is_group=False,
                     is_header=False, heading_level=None, children=None):
    """Create a mock Docling item."""
    from ingestion import GroupItem, SectionHeaderItem

    if is_group:
        item = MagicMock(spec=GroupItem)
    elif is_header:
        item = MagicMock(spec=SectionHeaderItem)
        item.level = heading_level
    else:
        item = MagicMock()

    item.self_ref = self_ref

    label_mock = MagicMock()
    label_mock.value = label_value
    item.label = label_mock

    cl_mock = MagicMock()
    cl_mock.value = content_layer_value
    item.content_layer = cl_mock

    item.text = text

    if prov_page is not None:
        prov = MagicMock()
        prov.page_no = prov_page
        if prov_bbox:
            prov.bbox = MagicMock()
            prov.bbox.l, prov.bbox.t, prov.bbox.r, prov.bbox.b = prov_bbox
            prov.bbox.coord_origin = MagicMock()
            prov.bbox.coord_origin.value = "BOTTOMLEFT"
        else:
            prov.bbox = None
        item.prov = [prov]
    else:
        item.prov = []

    item.parent = None
    item.children = children or []

    return item


class TestExtractLayout:
    """Test DoclingProcessor._extract_layout() with mock documents."""

    def _get_processor_class(self):
        from ingestion import DoclingProcessor
        return DoclingProcessor

    def test_extracts_pages(self):
        from ingestion import DoclingProcessor

        proc = MagicMock(spec=DoclingProcessor)
        proc._extract_layout = DoclingProcessor._extract_layout.__get__(proc)

        pages_dict = {
            1: _make_mock_page(612.0, 792.0),
            2: _make_mock_page(612.0, 792.0),
        }
        doc = _make_mock_doc(pages_dict, [])

        pages, elements = proc._extract_layout(doc)
        assert len(pages) == 2
        assert pages[0].page_number == 1
        assert pages[0].width == 612.0
        assert pages[1].page_number == 2

    def test_extracts_elements(self):
        from ingestion import DoclingProcessor

        proc = MagicMock(spec=DoclingProcessor)
        proc._extract_layout = DoclingProcessor._extract_layout.__get__(proc)

        text_item = _make_mock_item(
            "#/texts/0", "text", prov_page=1,
            prov_bbox=(72.0, 700.0, 540.0, 650.0), text="Hello world",
        )
        header_item = _make_mock_item(
            "#/texts/1", "section_header", prov_page=1,
            prov_bbox=(72.0, 750.0, 300.0, 730.0), text="Introduction",
            is_header=True, heading_level=1,
        )

        pages_dict = {1: _make_mock_page(612.0, 792.0)}
        items = [(text_item, 0), (header_item, 1)]
        doc = _make_mock_doc(pages_dict, items)

        pages, elements = proc._extract_layout(doc)

        assert len(elements) == 2
        assert elements[0].self_ref == "#/texts/0"
        assert elements[0].element_type == "text"
        assert elements[0].text_preview == "Hello world"
        assert elements[0].reading_order == 0

        assert elements[1].element_type == "section_header"
        assert elements[1].heading_level == 1

    def test_updates_page_element_counts(self):
        from ingestion import DoclingProcessor

        proc = MagicMock(spec=DoclingProcessor)
        proc._extract_layout = DoclingProcessor._extract_layout.__get__(proc)

        items = [
            (_make_mock_item("#/texts/0", "text", prov_page=1), 0),
            (_make_mock_item("#/texts/1", "text", prov_page=1), 0),
            (_make_mock_item("#/texts/2", "text", prov_page=2), 0),
        ]
        pages_dict = {
            1: _make_mock_page(612.0, 792.0),
            2: _make_mock_page(612.0, 792.0),
        }
        doc = _make_mock_doc(pages_dict, items)

        pages, elements = proc._extract_layout(doc)
        assert pages[0].element_count == 2  # page 1: 2 elements
        assert pages[1].element_count == 1  # page 2: 1 element

    def test_handles_group_items(self):
        from ingestion import DoclingProcessor

        proc = MagicMock(spec=DoclingProcessor)
        proc._extract_layout = DoclingProcessor._extract_layout.__get__(proc)

        group_item = _make_mock_item(
            "#/groups/0", "section", is_group=True, children=[MagicMock(), MagicMock()],
        )

        pages_dict = {1: _make_mock_page(612.0, 792.0)}
        doc = _make_mock_doc(pages_dict, [(group_item, 0)])

        pages, elements = proc._extract_layout(doc)
        assert len(elements) == 1
        assert elements[0].element_type == "group"
        assert elements[0].group_label == "section"
        assert elements[0].children_count == 2

    def test_handles_missing_provenance(self):
        from ingestion import DoclingProcessor

        proc = MagicMock(spec=DoclingProcessor)
        proc._extract_layout = DoclingProcessor._extract_layout.__get__(proc)

        item = _make_mock_item("#/texts/0", "text")  # no prov_page
        pages_dict = {}
        doc = _make_mock_doc(pages_dict, [(item, 0)])

        pages, elements = proc._extract_layout(doc)
        assert len(elements) == 1
        assert elements[0].page_number is None
        assert elements[0].bbox is None

    def test_text_preview_truncated_at_200(self):
        from ingestion import DoclingProcessor

        proc = MagicMock(spec=DoclingProcessor)
        proc._extract_layout = DoclingProcessor._extract_layout.__get__(proc)

        long_text = "x" * 500
        item = _make_mock_item("#/texts/0", "text", text=long_text)
        doc = _make_mock_doc({}, [(item, 0)])

        _, elements = proc._extract_layout(doc)
        assert len(elements[0].text_preview) == 200


# ── Chunk metadata ────────────────────────────────────────────────────────


class TestChunkMetadata:
    """Test that chunk metadata correctly stores both page_numbers and element_refs."""

    def test_metadata_contains_both_fields(self):
        from ingestion import ProcessedChunk

        chunk = ProcessedChunk(
            content="test",
            contextualized="test",
            chunk_index=0,
            token_count=1,
            char_count=4,
            metadata={
                "page_numbers": [1, 2],
                "element_refs": ["#/texts/0", "#/texts/1"],
            },
        )
        assert chunk.metadata["page_numbers"] == [1, 2]
        assert chunk.metadata["element_refs"] == ["#/texts/0", "#/texts/1"]

    def test_empty_metadata_defaults(self):
        from ingestion import ProcessedChunk

        chunk = ProcessedChunk(
            content="test", contextualized="test",
            chunk_index=0, token_count=1, char_count=4,
            metadata={"page_numbers": [], "element_refs": []},
        )
        assert chunk.metadata["page_numbers"] == []
        assert chunk.metadata["element_refs"] == []


# ── Supported extensions ──────────────────────────────────────────────────


def test_supported_extensions():
    from ingestion import SUPPORTED_EXTENSIONS

    assert ".pdf" in SUPPORTED_EXTENSIONS
    assert ".md" in SUPPORTED_EXTENSIONS
    assert ".txt" in SUPPORTED_EXTENSIONS
    assert ".html" in SUPPORTED_EXTENSIONS
    assert ".docx" in SUPPORTED_EXTENSIONS
