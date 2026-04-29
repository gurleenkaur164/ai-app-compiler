#!/usr/bin/env python3
"""
AppForge - Single-command startup script.
Serves the FastAPI backend + static frontend from one process.
"""

import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exception_handlers import http_exception_handler
from pydantic import BaseModel
import uvicorn
from pipeline import AppForgePipeline
from validator import SchemaValidator
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="AppForge", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_pipeline = None

def get_pipeline():
    global _pipeline
    if _pipeline is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key or api_key.strip() == "your_groq_api_key_here" or api_key.strip() == "":
            raise RuntimeError(
                "GROQ_API_KEY is not set. "
                "Get a free key at https://console.groq.com/keys, "
                "then add it to your .env file as: GROQ_API_KEY=gsk_..."
            )
        _pipeline = AppForgePipeline(api_key=api_key.strip())
    return _pipeline


class GenerateRequest(BaseModel):
    prompt: str


@app.get("/health")
def health():
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    key_set = bool(api_key and api_key != "your_groq_api_key_here" and len(api_key) > 10)
    return {
        "status": "ok",
        "service": "AppForge",
        "model": "llama-3.3-70b-versatile",
        "groq_key_configured": key_set
    }


@app.post("/generate")
def generate(req: GenerateRequest):
    if not req.prompt or not req.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty")

    # Always return JSON — catch every possible failure
    try:
        pipeline = get_pipeline()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to initialize pipeline: {str(e)}")

    try:
        result = pipeline.run(req.prompt)
        return result
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print("\n=== PIPELINE ERROR ===")
        print(tb)
        print("======================\n")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {str(e)}")


@app.get("/test-groq")
def test_groq():
    """Quick endpoint to verify Groq API key and model work."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent / "backend"))
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key or api_key == "your_groq_api_key_here":
        raise HTTPException(status_code=500, detail="GROQ_API_KEY not set in .env")
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        models_to_try = ["llama-3.3-70b-versatile", "llama-3.1-70b-versatile", "llama3-70b-8192", "mixtral-8x7b-32768"]
        for model in models_to_try:
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": "Reply with just: OK"}],
                    max_tokens=10
                )
                return {
                    "status": "ok",
                    "working_model": model,
                    "response": resp.choices[0].message.content,
                    "tokens_used": resp.usage.total_tokens
                }
            except Exception as e:
                if any(x in str(e).lower() for x in ["model", "not found", "decommissioned"]):
                    continue
                raise HTTPException(status_code=500, detail=f"Groq API error: {str(e)}")
        raise HTTPException(status_code=500, detail="No working models found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Connection error: {str(e)}")


@app.post("/validate")
def validate_config(config: dict):
    try:
        v = SchemaValidator()
        result = v.validate(config)
        return {"is_valid": result.is_valid, "errors": result.errors, "warnings": result.warnings}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Serve frontend
frontend_dir = Path(__file__).parent / "frontend"
app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

@app.get("/")
def root():
    return FileResponse(str(frontend_dir / "index.html"))


if __name__ == "__main__":
    # Pre-flight check
    api_key = os.getenv("GROQ_API_KEY", "")
    print("\n" + "="*55)
    print("  AppForge — Natural Language → App Config Compiler")
    print("="*55)
    if not api_key or api_key == "your_groq_api_key_here":
        print("\n  ⚠️  WARNING: GROQ_API_KEY is not set!")
        print("  Get a free key at: https://console.groq.com/keys")
        print("  Then add it to your .env file:")
        print("  GROQ_API_KEY=gsk_your_key_here\n")
    else:
        print(f"\n  ✓ Groq API key loaded (gsk_...{api_key[-4:]})")
    print(f"\n  Open: http://localhost:8000")
    print(f"  API:  http://localhost:8000/docs")
    print(f"  Health: http://localhost:8000/health")
    print(f"\n  Ctrl+C to stop\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)