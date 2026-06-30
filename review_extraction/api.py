from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse

from .env import load_environment
from .openai_agents import DualAgentExtractor
from .pipeline import process_pdf

load_environment()

app = FastAPI(
    title="Review Extraction API",
    description="Systematic-review extraction with an independent validator agent.",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/extract")
async def extract_pdf(
    file: UploadFile = File(...),
    output_dir: str = Form("outputs"),
    highlight: bool = Form(True),
) -> JSONResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return JSONResponse(status_code=400, content={"error": "Please upload a PDF file."})

    out_dir = Path(output_dir)
    agents = DualAgentExtractor()

    upload_dir = out_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = upload_dir / Path(file.filename).name
    pdf_path.write_bytes(await file.read())
    result = process_pdf(pdf_path, out_dir, agents, write_highlights=highlight)

    return JSONResponse(content=result.model_dump(mode="json"))
