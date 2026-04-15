"""Felix MCP Server — wraps Felix's REST API as MCP tools."""

import os
from typing import Optional
from urllib.parse import urljoin

import httpx
from mcp.server.fastmcp import FastMCP

FELIX_API_URL = os.getenv("FELIX_API_URL", "http://localhost:8001")

mcp = FastMCP(
    "felix",
    instructions=(
        "Felix is a document intelligence platform. Use these tools to explore "
        "documents that have been processed by Felix. Start with "
        "felix_list_documents to see what's available, then use "
        "felix_document_structure to understand the document's organization, "
        "and felix_read_section to read specific sections in full with tables, "
        "images, and footnotes preserved in reading order."
    ),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _api(path: str) -> str:
    """Join FELIX_API_URL with a path."""
    base = FELIX_API_URL.rstrip("/")
    return f"{base}/{path.lstrip('/')}"


async def _get(path: str, params: dict | None = None):
    """Async GET — returns parsed JSON."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(_api(path), params=params)
        response.raise_for_status()
        return response.json()


async def _post(path: str, json_body: dict):
    """Async POST — returns parsed JSON."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(_api(path), json=json_body)
        response.raise_for_status()
        return response.json()


# ---------------------------------------------------------------------------
# Tools — thin wrappers
# ---------------------------------------------------------------------------

@mcp.tool()
async def felix_list_documents() -> str:
    """List all documents ingested into Felix."""
    data = await _get("/documents")
    docs = data.get("documents", [])
    total = data.get("total", len(docs))
    if not docs:
        return "No documents found."
    lines = [f"Total documents: {total}\n"]
    for doc in docs:
        lines.append(
            f"ID {doc['id']}: {doc.get('path', 'unknown')}"
            f"  [ingested: {doc.get('ingested_at', 'unknown')}]"
        )
    return "\n".join(lines)


@mcp.tool()
async def felix_document_detail(document_id: int) -> str:
    """Get detailed statistics for a document — page, chunk, table, and image counts."""
    data = await _get(f"/documents/{document_id}/detail")
    doc = data.get("document", {})
    chunks = data.get("chunks", [])
    images = data.get("images", [])
    tables = data.get("tables", [])
    pages = data.get("pages", [])
    layout_elements = data.get("layout_elements", [])

    lines = [
        f"Document ID: {document_id}",
        f"Path: {doc.get('path', 'unknown')}",
        f"Ingested at: {doc.get('ingested_at', 'unknown')}",
        "",
        f"Pages:           {len(pages)}",
        f"Chunks:          {len(chunks)}",
        f"Tables:          {len(tables)}",
        f"Images:          {len(images)}",
        f"Layout elements: {len(layout_elements)}",
    ]
    return "\n".join(lines)


@mcp.tool()
async def felix_document_structure(document_id: int) -> str:
    """Get the heading/section structure of a document as an indented tree."""
    headings = await _get(f"/documents/{document_id}/structure")
    if not headings:
        return "No structure found for this document."

    lines = [f"Structure of document {document_id}:\n"]
    for h in headings:
        level = h.get("heading_level", 1)
        text = h.get("heading_text", "")
        page = h.get("page_number", "?")
        indent = "  " * (level - 1)
        lines.append(f"{indent}{'#' * level} {text}  (page {page})")
    return "\n".join(lines)


@mcp.tool()
async def felix_search(
    query: str,
    top_k: int = 5,
    document_ids: Optional[list[int]] = None,
    search_mode: str = "hybrid",
) -> str:
    """Semantic/hybrid search across Felix documents.

    Args:
        query: Natural language search query.
        top_k: Number of results to return (default 5).
        document_ids: Restrict search to specific document IDs (optional).
        search_mode: "hybrid" (default), "vector", or "keyword".
    """
    body = {
        "query": query,
        "top_k": top_k,
        "search_mode": search_mode,
        "include_images": True,
        "include_tables": True,
    }
    if document_ids:
        body["document_ids"] = document_ids

    data = await _post("/search", body)
    results = data.get("results", [])
    total = data.get("total_results", len(results))

    if not results:
        return f"No results found for query: {query!r}"

    lines = [f"Query: {query!r}  |  {total} result(s)\n"]
    for i, r in enumerate(results, 1):
        headings = " > ".join(r.get("headings", []))
        content = r.get("content", "").strip()
        similarity = r.get("similarity", 0.0)
        path = r.get("document_path", "unknown")

        lines.append(f"[{i}] chunk_id={r.get('chunk_id')}  score={similarity:.3f}")
        lines.append(f"    Document: {path}")
        if headings:
            lines.append(f"    Section:  {headings}")
        lines.append(f"    {content[:500]}")

        for tbl in r.get("tables") or []:
            lines.append(f"    [Table] {tbl.get('caption', '')}")
        for img in r.get("images") or []:
            lines.append(f"    [Image] {img.get('caption', '')}")

        lines.append("")

    return "\n".join(lines)


@mcp.tool()
async def felix_get_chunk(chunk_id: int) -> str:
    """Retrieve the full content of a single chunk by ID."""
    data = await _get(f"/chunks/{chunk_id}")
    headings = " > ".join(data.get("headings", []))
    content = data.get("content", "")
    path = data.get("document_path", "unknown")
    chunk_index = data.get("chunk_index", "?")
    metadata = data.get("metadata", {})

    lines = [
        f"Chunk ID:    {data.get('chunk_id', chunk_id)}",
        f"Document:    {path}",
        f"Chunk index: {chunk_index}",
    ]
    if headings:
        lines.append(f"Section:     {headings}")
    if metadata:
        lines.append(f"Metadata:    {metadata}")
    lines.append("")
    lines.append(content)
    return "\n".join(lines)


@mcp.tool()
async def felix_get_tables(document_id: Optional[int] = None) -> str:
    """List tables extracted from Felix documents, with their markdown content.

    Args:
        document_id: Filter to a specific document (optional).
    """
    params = {}
    if document_id is not None:
        params["document_id"] = document_id

    data = await _get("/tables", params=params)
    tables = data.get("tables", [])
    total = data.get("total", len(tables))

    if not tables:
        return "No tables found."

    lines = [f"Total tables: {total}\n"]
    for t in tables:
        lines.append(
            f"Table ID {t['id']}  (doc {t.get('document_id')}, page {t.get('page_number')})"
        )
        caption = t.get("caption", "")
        if caption:
            lines.append(f"Caption: {caption}")
        lines.append(f"Size: {t.get('num_rows', '?')} rows × {t.get('num_cols', '?')} cols")
        markdown = t.get("content_markdown", "")
        if markdown:
            lines.append(markdown)
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
async def felix_get_images(document_id: Optional[int] = None) -> str:
    """List images extracted from Felix documents with captions and metadata.

    Args:
        document_id: Filter to a specific document (optional).
    """
    params = {}
    if document_id is not None:
        params["document_id"] = document_id

    data = await _get("/images", params=params)
    images = data.get("images", [])
    total = data.get("total", len(images))

    if not images:
        return "No images found."

    lines = [f"Total images: {total}\n"]
    for img in images:
        lines.append(
            f"Image ID {img['id']}  (page {img.get('page_number', '?')})"
        )
        caption = img.get("caption", "")
        if caption:
            lines.append(f"  Caption: {caption}")
        label = img.get("label", "")
        if label:
            lines.append(f"  Label:   {label}")
        w = img.get("width", "?")
        h = img.get("height", "?")
        lines.append(f"  Size:    {w} × {h}")
        fp = img.get("file_path", "")
        if fp:
            lines.append(f"  Path:    {fp}")
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
async def felix_upload(file_path: str, index_slug: str = "default") -> str:
    """Upload a document to Felix for ingestion.

    Args:
        file_path: Absolute path to the file on the server filesystem.
        index_slug: Index to assign the document to (default: "default").
    """
    async with httpx.AsyncClient(timeout=60.0) as client:
        with open(file_path, "rb") as fh:
            files = {"file": (os.path.basename(file_path), fh)}
            data = {"index_slug": index_slug}
            response = await client.post(_api("/upload"), files=files, data=data)
            response.raise_for_status()
            result = response.json()

    status = result.get("status", "unknown")
    message = result.get("message", "")
    return f"Upload status: {status}\n{message}"


@mcp.tool()
async def felix_ingestion_status() -> str:
    """Check the status of all ingestion jobs in Felix."""
    data = await _get("/ingestion/status")
    jobs = data.get("jobs", [])

    if not jobs:
        return "No ingestion jobs found."

    lines = [f"Ingestion jobs: {len(jobs)}\n"]
    for job in jobs:
        filename = job.get("filename", "unknown")
        status = job.get("status", "unknown")
        progress = job.get("progress", {})
        lines.append(f"{filename}  [{status}]")
        if progress:
            lines.append(f"  Progress: {progress}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Compound tool — felix_read_section
# ---------------------------------------------------------------------------

@mcp.tool()
async def felix_read_section(
    document_id: int,
    heading: Optional[str] = None,
    start_page: Optional[int] = None,
    end_page: Optional[int] = None,
    include_tables: bool = True,
    include_images: bool = True,
) -> str:
    """Read a document section with full structural fidelity — tables, images, footnotes in reading order.

    Provide one of:
      - heading: section title (case-insensitive substring match)
      - start_page / end_page: explicit page range
      - neither: reads page 1

    Args:
        document_id: Felix document ID.
        heading: Section heading to locate (optional).
        start_page: First page of range (optional).
        end_page: Last page of range (optional).
        include_tables: Render tables inline (default True).
        include_images: Render image references inline (default True).
    """
    # Step 1: Resolve page range
    page_from: int
    page_to: int

    if heading is not None:
        structure = await _get(f"/documents/{document_id}/structure")
        # Find heading by case-insensitive substring
        match_idx = None
        for i, h in enumerate(structure):
            if heading.lower() in h.get("heading_text", "").lower():
                match_idx = i
                break

        if match_idx is None:
            return f"Heading {heading!r} not found in document {document_id}."

        matched = structure[match_idx]
        matched_level = matched.get("heading_level", 1)
        page_from = matched.get("page_number", 1)

        # Find next heading at same or higher level (lower number = higher level)
        page_to = page_from  # default: single page
        for h in structure[match_idx + 1 :]:
            if h.get("heading_level", 99) <= matched_level:
                # Next section starts here — end just before it
                next_page = h.get("page_number", page_from + 1)
                page_to = max(page_from, next_page - 1)
                break
        else:
            # No next sibling — read to end; fetch page count from detail
            detail = await _get(f"/documents/{document_id}/detail")
            pages = detail.get("pages", [])
            page_to = max((p.get("page_number", 1) for p in pages), default=page_from)

    elif start_page is not None:
        page_from = start_page
        page_to = end_page if end_page is not None else start_page
    else:
        page_from = 1
        page_to = 1

    # Step 2: Fetch layout elements for the page range
    elements = await _get(
        "/elements/search",
        params={
            "document_id": document_id,
            "page_from": page_from,
            "page_to": page_to,
            "include_text": "true",
            "limit": 1000,
        },
    )
    # elements may be a list directly
    if isinstance(elements, dict):
        elements = elements.get("elements", [])

    # Step 3: Fetch tables and images for the page range (if requested)
    rendered_table_ids: set[int] = set()
    rendered_image_ids: set[int] = set()
    tables_by_page: dict[int, list] = {}
    images_by_page: dict[int, list] = {}

    if include_tables:
        tbl_data = await _get("/tables", params={"document_id": document_id})
        for t in tbl_data.get("tables", []):
            pg = t.get("page_number", 0)
            if page_from <= pg <= page_to:
                tables_by_page.setdefault(pg, []).append(t)

    if include_images:
        img_data = await _get("/images", params={"document_id": document_id})
        for img in img_data.get("images", []):
            pg = img.get("page_number", 0)
            if page_from <= pg <= page_to:
                images_by_page.setdefault(pg, []).append(img)

    # Step 4: Assemble output in reading order
    lines: list[str] = []

    heading_label = heading or f"pages {page_from}–{page_to}"
    lines.append(f"# Document {document_id} — {heading_label}\n")

    # Sort elements by (page_number, reading_order)
    sorted_elements = sorted(
        elements,
        key=lambda e: (e.get("page_number", 0), e.get("reading_order", 0)),
    )

    current_page = None

    for elem in sorted_elements:
        elem_page = elem.get("page_number", 0)
        elem_type = elem.get("element_type", "text")
        content = elem.get("full_text") or elem.get("text_preview") or ""
        heading_level = elem.get("heading_level") or 1

        # Inline tables/images that appear before this element on the same page
        if elem_page != current_page:
            current_page = elem_page

        if not content.strip() and elem_type not in ("table", "picture"):
            continue

        if elem_type == "section_header":
            md_level = "#" * (heading_level + 1)
            lines.append(f"\n{md_level} {content}\n")

        elif elem_type == "table":
            # Try to find matching table in tables_by_page
            group_label = elem.get("group_label", "")
            # Attempt to match by page then by content overlap
            page_tables = tables_by_page.get(elem_page, [])
            matched_table = None
            for t in page_tables:
                if t["id"] not in rendered_table_ids:
                    matched_table = t
                    break

            if matched_table and include_tables:
                rendered_table_ids.add(matched_table["id"])
                caption = matched_table.get("caption", "")
                md = matched_table.get("content_markdown", content)
                if caption:
                    lines.append(f"\n*Table: {caption}*\n")
                lines.append(md)
                lines.append("")
            elif content.strip():
                lines.append(f"\n{content}\n")

        elif elem_type == "picture":
            page_images = images_by_page.get(elem_page, [])
            matched_image = None
            for img in page_images:
                if img["id"] not in rendered_image_ids:
                    matched_image = img
                    break

            if matched_image and include_images:
                rendered_image_ids.add(matched_image["id"])
                caption = matched_image.get("caption", "")
                label = matched_image.get("label", "")
                img_id = matched_image["id"]
                desc = caption or label or content
                lines.append(f"\n*[Image ID {img_id}: {desc}]*\n")
            elif content.strip():
                lines.append(f"\n*[Image: {content}]*\n")

        elif elem_type in ("caption", "footnote", "page_header", "page_footer"):
            lines.append(f"\n*{elem_type.replace('_', ' ').title()}: {content}*\n")

        elif elem_type == "formula":
            lines.append(f"\n$$\n{content}\n$$\n")

        elif elem_type == "code":
            lang = (elem.get("metadata") or {}).get("code_language", "")
            lines.append(f"\n```{lang}\n{content}\n```\n")

        elif elem_type == "list_item":
            lines.append(f"- {content}")

        else:
            lines.append(f"\n{content}\n")

    # Append any tables/images not yet rendered (no matching layout element)
    if include_tables:
        for pg in range(page_from, page_to + 1):
            for t in tables_by_page.get(pg, []):
                if t["id"] not in rendered_table_ids:
                    rendered_table_ids.add(t["id"])
                    caption = t.get("caption", "")
                    md = t.get("content_markdown", "")
                    if caption:
                        lines.append(f"\n*Table: {caption}*\n")
                    lines.append(md)
                    lines.append("")

    if include_images:
        for pg in range(page_from, page_to + 1):
            for img in images_by_page.get(pg, []):
                if img["id"] not in rendered_image_ids:
                    rendered_image_ids.add(img["id"])
                    caption = img.get("caption", "")
                    label = img.get("label", "")
                    img_id = img["id"]
                    desc = caption or label or ""
                    lines.append(f"\n*[Image ID {img_id}: {desc}]*\n")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
