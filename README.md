# Contract Review Agent

A prototype for comparing a procurement document with a draft contract. It combines document conversion, a LangGraph tool workflow, LLM-assisted clause extraction and comparison, and a local report viewer. The output is a review aid that requires human verification, not a legal decision.

## What this project demonstrates

- A modular agent workflow with separate conversion, review, and report tools.
- PDF/Office ingestion with MinerU, optional OCR, and Markdown handoff to the LLM.
- Configurable OpenAI-compatible model providers (DeepSeek, MiniMax, GLM), a FastAPI endpoint, a browser UI, and a command-line entry point.
- Structured JSON and Markdown report output with source evidence and human-readable issue descriptions.

## Architecture

```text
PDF / Office files
      | 
      v
MinerU / document conversion -> Markdown
      |
      v
LangGraph agent -> clause extraction -> comparison -> report
      |                                      |
      +---------------- JSON + Markdown ----+
                         |
                    FastAPI / web UI
```

The LLM can make mistakes, and document conversion can omit or misread text. Review all findings against the original files.

## Run locally

The project was developed on Windows with Python 3.13 and a local MinerU model cache. A clean installation with the current unpinned dependencies has **not** been verified. PDF/Office conversion requires additional model downloads and may need MinerU version-specific adjustment.

1. Create and activate a Python virtual environment.
2. Install dependencies: `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env` and set one provider key, or enter a key in the web UI. Never commit `.env`.
4. For PDF/Office input, run `python bootstrap_mineru.py` to download the OCR/layout assets and generate the local `magic-pdf.json`. The bootstrap script adapts one OCR model reference inside the installed MinerU package; use a dedicated virtual environment.
5. Start the local API: `uvicorn fastapi_app:app --host 127.0.0.1 --port 8000` and open `http://127.0.0.1:8000/`.

The CLI entry point is `python run_contract_review_agent.py --provider deepseek --procurement-file PATH --contract-file PATH`. Use `--help` for options.

This app has no authentication. Bind it to localhost; do not expose it as a public service. Uploaded files and generated reports may contain confidential contract data. Provider requests transmit extracted document text to the configured model endpoint.

## Repository map

| Path | Purpose |
| --- | --- |
| `contract_review_agent/graph.py` | Agent state and tool workflow |
| `contract_review_agent/tools/` | Conversion, review, and report tools |
| `contract_review_agent/service.py` | End-to-end orchestration and report saving |
| `mineru_markdown_converter.py` | PDF/Office parsing and OCR enrichment |
| `fastapi_app.py` | Local HTTP API |
| `web/` | Browser interface |
| `bootstrap_mineru.py` | Optional local model setup |

## Verification and limits

- Run `python -m unittest discover -s tests -v` for dependency-free checks of JSON extraction and serialization. The GitHub Actions workflow also checks source syntax in a clean Python environment. These checks cover parsing behavior, **not** contract review quality or a complete API/OCR run.
- The FastAPI application imports successfully in the original project runtime. This is a startup check, **not** a full review run.
- Python syntax checks pass for the published source.
- Original local contract files and generated reports are intentionally excluded. No client documents, scores, benchmark numbers, or anonymized results are claimed here.
- There is no public evaluation dataset, baseline comparison, ablation, or measured accuracy yet.
- Model API keys and OCR weights are not included. Reproducing a full run requires a configured provider and local model setup.

## Provenance

This is an engineering project using LangGraph, MinerU, PyMuPDF, Mammoth, FastAPI, and their upstream packages. It is not a reproduction of a specific research paper. The public copy removes local data and environment artifacts and simplifies the setup path; the libraries remain the work of their respective authors and are subject to their own licenses.
