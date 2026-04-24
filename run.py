"""
run.py — Entry point
Chạy: python run.py
"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

import uvicorn

if __name__ == "__main__":
    host = os.environ.get("DV_HOST", "0.0.0.0")
    port = int(os.environ.get("DV_PORT", "8000"))
    uvicorn.run(
        "api.main:app",
        host=host,
        port=port,
        reload=True,
    )
