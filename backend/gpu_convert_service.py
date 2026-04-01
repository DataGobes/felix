"""GPU Document Conversion Service — stateless Docling wrapper for Azure Container Apps.

Accepts a document binary + pipeline options, runs GPU-accelerated conversion
via Docling, and returns the serialized DoclingDocument JSON.

Uses async job pattern to avoid ACA's 240s gateway timeout:
  POST /convert  → accepts file, returns job_id immediately
  GET  /jobs/{id} → poll for status/result

Runs on x86_64 with CUDA-enabled PyTorch. Designed for Azure Container Apps
with T4 GPU workload profile (scale 0→1 on HTTP request).
"""

import io
import json
import os
import threading
import time
import traceback
import uuid

import structlog
import torch
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.io import DocumentStream
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse

logger = structlog.get_logger("gpu-convert")

API_KEY = os.getenv("API_KEY", "")

app = FastAPI(title="GPU Document Conversion Service")

# Pre-warmed converter — built at startup so models are cached before first request
_warm_converter: DocumentConverter | None = None

# In-memory job store (single replica, no persistence needed)
_jobs: dict[str, dict] = {}


@app.on_event("startup")
def warmup():
    """Pre-download and cache all VLM models at container startup.

    Docling lazy-loads models on first convert() call, so we run a
    dummy PDF conversion to force all model downloads now, before
    any real request arrives.
    """
    global _warm_converter
    logger.info("warmup_start", msg="Building converter and forcing model download...")
    start = time.time()
    _warm_converter = build_converter({
        "do_code_enrichment": True,
        "do_formula_enrichment": True,
        "do_picture_description": True,
        "do_picture_classification": True,
    })

    # Create a minimal valid PDF to force model loading
    dummy_pdf = (
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R"
        b"/Resources<<>>>>endobj\nxref\n0 4\n"
        b"0000000000 65535 f \n0000000009 00000 n \n"
        b"0000000058 00000 n \n0000000115 00000 n \n"
        b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n229\n%%EOF"
    )
    try:
        source = DocumentStream(name="warmup.pdf", stream=io.BytesIO(dummy_pdf))
        _warm_converter.convert(source)
        logger.info("warmup_complete", time_seconds=round(time.time() - start, 2),
                     msg="All models loaded and ready")
    except Exception as e:
        logger.warning("warmup_dummy_conversion_failed", error=str(e),
                        time_seconds=round(time.time() - start, 2),
                        msg="Models may still be loaded; proceeding")


def verify_api_key(x_api_key: str = Header(default="")):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


def build_converter(options: dict) -> DocumentConverter:
    """Build a DocumentConverter with the given pipeline options."""
    pdf_options = PdfPipelineOptions()
    pdf_options.do_ocr = options.get("do_ocr", False)
    pdf_options.generate_picture_images = options.get("generate_picture_images", True)
    pdf_options.images_scale = options.get("images_scale", 2.0)
    pdf_options.do_code_enrichment = options.get("do_code_enrichment", True)
    pdf_options.do_formula_enrichment = options.get("do_formula_enrichment", True)
    pdf_options.do_picture_description = options.get("do_picture_description", False)
    pdf_options.do_picture_classification = options.get("do_picture_classification", False)

    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_options)}
    )


def _run_conversion(job_id: str, content: bytes, filename: str, opts: dict):
    """Run the actual conversion in a background thread."""
    start = time.time()
    _jobs[job_id]["status"] = "processing"

    source = DocumentStream(name=filename, stream=io.BytesIO(content))

    all_on = (
        opts.get("do_code_enrichment", True) is True
        and opts.get("do_formula_enrichment", True) is True
        and opts.get("do_picture_description") is True
        and opts.get("do_picture_classification") is True
    )
    converter = _warm_converter if (_warm_converter and all_on) else build_converter(opts)

    try:
        result = converter.convert(source)
        doc_json = result.document.model_dump_json()
        elapsed = time.time() - start

        _jobs[job_id].update({
            "status": "complete",
            "document_json": doc_json,
            "conversion_time_seconds": round(elapsed, 2),
        })

        logger.info(
            "conversion_complete",
            job_id=job_id,
            filename=filename,
            time_seconds=round(elapsed, 2),
            doc_json_bytes=len(doc_json),
        )
    except Exception as e:
        elapsed = time.time() - start
        tb = traceback.format_exc()
        gpu_mem = ""
        if torch.cuda.is_available():
            alloc = torch.cuda.memory_allocated() / 1e9
            reserved = torch.cuda.memory_reserved() / 1e9
            gpu_mem = f"GPU mem: {alloc:.1f}GB allocated, {reserved:.1f}GB reserved"
        _jobs[job_id].update({
            "status": "failed",
            "error": f"{str(e)}\n{tb}",
            "conversion_time_seconds": round(elapsed, 2),
        })
        logger.error("conversion_failed", job_id=job_id, filename=filename,
                     error=str(e), traceback=tb, gpu_memory=gpu_mem)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "gpu_available": torch.cuda.is_available(),
        "cuda_version": torch.version.cuda if torch.cuda.is_available() else None,
        "gpu_name": (
            torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
        ),
        "active_jobs": sum(1 for j in _jobs.values() if j["status"] == "processing"),
    }


@app.post("/convert", dependencies=[Depends(verify_api_key)])
async def convert_document(
    file: UploadFile = File(...),
    options: str = Form("{}"),
):
    content = await file.read()
    filename = file.filename or "document.pdf"
    opts = json.loads(options)

    job_id = uuid.uuid4().hex[:12]
    _jobs[job_id] = {
        "status": "accepted",
        "filename": filename,
        "submitted_at": time.time(),
    }

    thread = threading.Thread(
        target=_run_conversion,
        args=(job_id, content, filename, opts),
        daemon=True,
    )
    thread.start()

    logger.info("job_submitted", job_id=job_id, filename=filename,
                file_bytes=len(content))

    return JSONResponse(content={"job_id": job_id, "status": "accepted"})


@app.get("/jobs/{job_id}", dependencies=[Depends(verify_api_key)])
async def get_job(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] == "complete":
        # Return result and clean up
        result = {
            "status": "complete",
            "document_json": job["document_json"],
            "conversion_time_seconds": job["conversion_time_seconds"],
        }
        del _jobs[job_id]
        return JSONResponse(content=result)

    if job["status"] == "failed":
        result = {
            "status": "failed",
            "error": job["error"],
            "conversion_time_seconds": job.get("conversion_time_seconds"),
        }
        del _jobs[job_id]
        return JSONResponse(content=result, status_code=500)

    return JSONResponse(content={
        "status": job["status"],
        "elapsed_seconds": round(time.time() - job["submitted_at"], 1),
    })
