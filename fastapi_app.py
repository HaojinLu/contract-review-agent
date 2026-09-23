from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from contract_review_agent.config import DEFAULT_PROVIDER_BASE_URLS, DEFAULT_PROVIDER_MODELS
from contract_review_agent.llm import ProviderSettings
from contract_review_agent.service import run_contract_review

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_REPORT_DIR = BASE_DIR / "contract_review_report"
DEFAULT_OUTPUT_DIR = BASE_DIR / "output_md"


def load_env_file(env_path: Path = BASE_DIR / ".env") -> None:
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def resolve_web_dir() -> Path:
    configured = os.getenv("CONTRACT_AGENT_WEB_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return BASE_DIR / "web"


load_env_file()
WEB_DIR = resolve_web_dir()

app = FastAPI(title="Contract Review Agent API", version="1.0.0")

if WEB_DIR.exists():
    app.mount("/web", StaticFiles(directory=str(WEB_DIR)), name="web")


@app.get("/")
def root() -> FileResponse:
    index_file = WEB_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Frontend page not found.")
    return FileResponse(index_file)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config")
def api_config() -> dict:
    return {
        "providers": {
            provider: {
                "default_model": DEFAULT_PROVIDER_MODELS[provider],
                "default_base_url": DEFAULT_PROVIDER_BASE_URLS[provider],
                "env_key": f"{provider.upper()}_API_KEY",
            }
            for provider in DEFAULT_PROVIDER_MODELS
        },
        "web_dir": str(WEB_DIR),
        "output_md_dir": str(DEFAULT_OUTPUT_DIR),
        "report_output_dir": str(DEFAULT_REPORT_DIR),
    }


@app.post("/api/review")
async def review_contracts(
    procurement_file: UploadFile = File(...),
    contract_file: UploadFile = File(...),
    provider: str = Form(...),
    model: str | None = Form(default=None),
    api_key: str | None = Form(default=None),
    base_url: str | None = Form(default=None),
    temperature: float = Form(default=0.2),
    report_output_dir: str | None = Form(default=None),
) -> dict:
    try:
        settings = ProviderSettings(
            provider=provider,  # type: ignore[arg-type]
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid provider settings: {exc}") from exc

    with tempfile.TemporaryDirectory(prefix="contract_review_api_") as temp_dir:
        temp_path = Path(temp_dir)
        procurement_name = Path(procurement_file.filename or "procurement.bin").name
        contract_name = Path(contract_file.filename or "contract.bin").name
        procurement_path = temp_path / f"procurement_{procurement_name}"
        contract_path = temp_path / f"contract_{contract_name}"

        procurement_bytes = await procurement_file.read()
        contract_bytes = await contract_file.read()
        procurement_path.write_bytes(procurement_bytes)
        contract_path.write_bytes(contract_bytes)

        try:
            result = run_contract_review(
                settings=settings,
                procurement_file=str(procurement_path),
                contract_file=str(contract_path),
                report_output_dir=report_output_dir or str(DEFAULT_REPORT_DIR),
            )
        except Exception as exc:
            import traceback
            traceback.print_exc()  # 打印完整堆栈到终端
            raise HTTPException(status_code=500, detail=f"Review failed: {exc}") from exc

    response_payload = result["final_json"]
    if isinstance(response_payload, dict):
        response_payload["saved_json_path"] = result["saved_json_path"]
        response_payload["saved_markdown_path"] = result["saved_markdown_path"]
    return response_payload
