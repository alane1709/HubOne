"""
main.py  v2.2
-------------
FastAPI — Upload, Validate, Config API
- 50MB file limit
- Stream upload
- JSONResponse fixed: use content= keyword
- generate_output_all added to output_generator
"""

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import shutil, uuid, json, os
from pathlib import Path
from datetime import datetime

from engine.config_loader import list_templates
from engine.template_detector import detect_template

# ── .env loading ─────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    _base = Path(__file__).parent.parent
    for _p in [_base / ".env", _base.parent / ".env"]:
        if _p.exists():
            load_dotenv(_p)
            break
except ImportError:
    pass

# ── App setup ─────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Data Validation Platform",
    description="Upload & validate Excel files based on configurable rules",
    version="2.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Paths ─────────────────────────────────────────────────────────────────────
_DEFAULT_BASE = Path(__file__).parent.parent

UPLOAD_DIR  = Path(os.environ.get("DV_UPLOAD_DIR",  str(_DEFAULT_BASE / "uploads")))
OUTPUT_DIR  = Path(os.environ.get("DV_OUTPUT_DIR",  str(_DEFAULT_BASE / "outputs")))
CONFIG_PATH = Path(os.environ.get("DV_CONFIG_PATH", str(_DEFAULT_BASE / "config" / "template_config.json")))
MAX_FILE_SIZE_MB = int(os.environ.get("DV_MAX_FILE_MB", "50"))
CHUNK_SIZE       = 1024 * 1024  # 1MB

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

print(f"[DataValid] UPLOAD_DIR : {UPLOAD_DIR}")
print(f"[DataValid] OUTPUT_DIR : {OUTPUT_DIR}")
print(f"[DataValid] CONFIG_PATH: {CONFIG_PATH}")
print(f"[DataValid] MAX_FILE   : {MAX_FILE_SIZE_MB}MB")

# ── Startup check ─────────────────────────────────────────────────────────────
@app.on_event("startup")
def startup_check():
    print("[DataValid] ─── Startup checks ───")
    try:
        templates = list_templates()
        print(f"[DataValid] Templates: {templates}")
    except Exception as e:
        print(f"[DataValid] ERROR config: {e}")

    try:
        from engine.output_generator import generate_output_all, generate_output
        print("[DataValid] output_generator: OK")
    except ImportError as e:
        print(f"[DataValid] ERROR output_generator: {e}")

    try:
        from engine.validator import Validator
        print("[DataValid] Validator: OK")
    except Exception as e:
        print(f"[DataValid] ERROR Validator: {e}")

    print("[DataValid] ─── Ready! ───")

# ── Helpers ───────────────────────────────────────────────────────────────────
def check_extension(filename: str):
    if Path(filename).suffix.lower() != ".xlsx":
        raise HTTPException(400, f"Only .xlsx supported. Got: '{Path(filename).suffix}'")

def make_saved_name(template_name: str) -> str:
    return f"{template_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.xlsx"

def file_meta(path: Path, template_name: str, original_name: str = "") -> dict:
    return {
        "saved_as":      path.name,
        "template":     template_name,
        "original_name": original_name or path.name,
        "size_kb":       round(path.stat().st_size / 1024, 2),
        "size_mb":       round(path.stat().st_size / (1024*1024), 2),
        "uploaded_at":   datetime.now().isoformat(),
    }

# ── Routes ──────────────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {"message": "Data Validation Platform API", "version": "2.2.0",
            "max_file_size_mb": MAX_FILE_SIZE_MB}

@app.get("/health")
def health_check():
    return {"status": "ok", "version": "2.2.0"}

@app.get("/templates")
def get_templates():
    return {"templates": list_templates()}


@app.post("/upload")
async def upload_file(file: UploadFile = File(...), template_name: str = Form(None)):
    check_extension(file.filename)

    tmp_name = f"tmp_{uuid.uuid4().hex}.xlsx"
    tmp_path = UPLOAD_DIR / tmp_name
    total_bytes = 0

    try:
        with open(tmp_path, "wb") as f:
            while True:
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > MAX_FILE_SIZE_MB * 1024 * 1024:
                    tmp_path.unlink(missing_ok=True)
                    raise HTTPException(413, f"File vượt quá {MAX_FILE_SIZE_MB}MB")
                f.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(500, f"Lỗi upload: {e}")

    detection = None
    try:
        if not template_name:
            detection     = detect_template(tmp_path)
            template_name = detection["template"]
            if detection["confidence"] < 0.3:
                tmp_path.unlink(missing_ok=True)
                raise HTTPException(422, "Không detect được template. Chọn template thủ công.")
        else:
            if template_name not in list_templates():
                tmp_path.unlink(missing_ok=True)
                raise HTTPException(400, f"Template không tồn tại: {template_name}")
    except HTTPException:
        raise
    except TypeError as e:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(500, f"Lỗi detect template (cần cập nhật template_detector.py): {e}")
    except Exception as e:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(500, f"Lỗi detect template: {e}")

    final_name = make_saved_name(template_name)
    final_path = UPLOAD_DIR / final_name
    shutil.move(str(tmp_path), str(final_path))

    meta = file_meta(final_path, template_name, file.filename)
    response = {"status": "uploaded", "message": "File uploaded. Ready for validation.", "metadata": meta}

    if detection:
        response["auto_detection"] = {
            "confidence":   f"{detection['confidence']*100:.1f}%",
            "matched_cols": detection.get("matched", []),
            "all_scores":   {k: f"{v*100:.1f}%" for k, v in detection.get("all_scores", {}).items()},
        }
    return JSONResponse(content=response)


@app.post("/upload-path")
def upload_by_path(file_path: str = Form(...), template_name: str = Form(None)):
    path = Path(file_path)
    if not path.exists():
        raise HTTPException(404, f"File not found: {file_path}")
    check_extension(path.name)

    size_mb = path.stat().st_size / (1024*1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(413, f"File vượt quá {MAX_FILE_SIZE_MB}MB ({size_mb:.1f}MB)")

    detection = None
    try:
        if not template_name:
            detection     = detect_template(path)
            template_name = detection["template"]
            if detection["confidence"] < 0.3:
                raise HTTPException(422, {"message": "Không detect được template.",
                                          "scores": detection.get("all_scores", {})})
        else:
            if template_name not in list_templates():
                raise HTTPException(400, f"Template '{template_name}' không tồn tại.")
    except HTTPException:
        raise
    except TypeError as e:
        raise HTTPException(500, f"Lỗi detect template (cần cập nhật template_detector.py): {e}")
    except Exception as e:
        raise HTTPException(500, f"Lỗi detect template: {e}")

    final_name = make_saved_name(template_name)
    final_path = UPLOAD_DIR / final_name
    shutil.copy2(path, final_path)

    meta = file_meta(final_path, template_name, path.name)
    meta["original_path"] = str(path)
    response = {"status": "registered", "message": "File registered. Ready for validation.", "metadata": meta}

    if detection:
        response["auto_detection"] = {
            "confidence":   f"{detection['confidence']*100:.1f}%",
            "matched_cols": detection.get("matched", []),
            "all_scores":   {k: f"{v*100:.1f}%" for k, v in detection.get("all_scores", {}).items()},
        }
    return JSONResponse(content=response)


@app.get("/uploads")
def list_uploads():
    files = [
        {"filename": f.name, "size_kb": round(f.stat().st_size/1024, 2),
         "size_mb": round(f.stat().st_size/(1024*1024), 2),
         "uploaded_at": datetime.fromtimestamp(f.stat().st_mtime).isoformat()}
        for f in sorted(UPLOAD_DIR.glob("*.xlsx"), key=lambda x: x.stat().st_mtime, reverse=True)
    ]
    return {"total": len(files), "files": files}


@app.post("/validate")
def validate_file(saved_as: str = Form(...), template_name: str = Form(...)):
    from engine.validator import Validator
    from engine.output_generator import generate_output

    file_path = UPLOAD_DIR / saved_as
    if not file_path.exists():
        raise HTTPException(404, f"File không tồn tại: {saved_as}")

    v      = Validator(template_name)
    result = v.validate(file_path)
    out    = generate_output(file_path, result, OUTPUT_DIR)

    result["excel_output"]    = out["excel_path"]
    result["summary_output"]  = out["summary_path"]
    return JSONResponse(content=result)


@app.post("/validate-all")
def validate_all_sheets(saved_as: str = Form(...)):
    from engine.validator import Validator
    from engine.output_generator import generate_output_all
    import openpyxl

    file_path = UPLOAD_DIR / saved_as
    if not file_path.exists():
        raise HTTPException(404, f"File không tồn tại: {saved_as}")

    wb = openpyxl.load_workbook(file_path, read_only=True)
    sheet_names = wb.sheetnames
    wb.close()

    templates = list_templates()
    sheet_match = {}
    for tmpl in templates:
        tk = tmpl.lower().replace("_","").replace(" ","")
        for sheet in sheet_names:
            sk = sheet.lower().replace("_","").replace(" ","")
            if tk == sk or tk in sk or sk in tk:
                sheet_match[tmpl] = sheet
                break

    if not sheet_match:
        raise HTTPException(422,
            f"Không tìm thấy sheet khớp template. Sheets: {sheet_names}, Templates: {templates}")

    results = {}
    for tmpl in sheet_match:
        v = Validator(tmpl)
        results[tmpl] = v.validate(file_path)

    out        = generate_output_all(file_path, results, OUTPUT_DIR)
    total_rows = sum(r["total_rows"] for r in results.values())
    total_errs = sum(r["error_rows"] for r in results.values())
    total_crit = sum(r["critical"]   for r in results.values())
    total_warn = sum(r["warnings"]   for r in results.values())
    error_pct  = round(total_errs/total_rows*100, 1) if total_rows > 0 else 0
    status     = "fail" if total_crit > 0 else ("warning" if total_warn > 0 else "pass")

    return JSONResponse(content={
        "status": status,
        "total_rows": total_rows,
        "total_error_rows": total_errs,
        "error_pct": error_pct,
        "critical": total_crit,
        "warnings": total_warn,
        "sheets_validated": list(sheet_match.keys()),
        "sheet_results": {
            tmpl: {k: r[k] for k in ["sheet_name","total_rows","error_rows","error_pct","critical","warnings","status","errors"]}
            for tmpl, r in results.items()
        },
        "excel_output":   out["excel_path"],
        "summary_output": out["summary_path"],
    })


# ── Config API ────────────────────────────────────────────────────────────────
@app.get("/config")
def get_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)

@app.post("/config")
async def save_config(request_body: dict):
    if "version" not in request_body:
        templates = {}
        for tmpl_name, cols in request_body.items():
            if not isinstance(cols, list): continue
            columns, rules, idx = [], [], 1
            for col in cols:
                columns.append({
                    "name": col.get("column_name", col.get("name", "")),
                    "data_type": col.get("data_type", "text"),
                    "is_required": col.get("is_required", False),
                    "allow_null_percent": col.get("allow_null_percent", 100),
                })
                rt = col.get("rule_type", "none")
                cn = col.get("column_name", col.get("name", ""))
                sv = col.get("severity", "warning")
                if rt not in ("none", ""):
                    scope = {"unique":"table","regex":"column","range":"column",
                             "no_future_date":"column","cross_column":"row","compare":"row"}.get(rt,"column")
                    r = {"id":f"{tmpl_name.lower()}_r{idx:03d}","type":"compare" if rt=="cross_column" else rt,
                         "scope":scope,"column":cn,"priority":idx,"severity":sv,"enabled":True,"message":None,"params":{}}
                    detail = col.get("rule_detail","")
                    if rt=="regex": r["params"]={"pattern":detail}
                    elif rt=="range":
                        import re as _re
                        m=_re.match(r"([><=!]+)\s*([\d.]+)",detail)
                        if m: r["params"]={"operator":m.group(1),"value":float(m.group(2))}
                    elif rt in ("cross_column","compare"): r["params"]={"expr":detail}
                    rules.append(r); idx+=1
            templates[tmpl_name]={"columns":columns,"rules":rules}
        request_body={"version":"2.0","templates":templates}
    with open(CONFIG_PATH,"w",encoding="utf-8") as f:
        json.dump(request_body,f,ensure_ascii=False,indent=2)
    return {"status":"saved","message":"Config saved successfully."}

@app.get("/config/{template_name}")
def get_template_config(template_name: str):
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    if cfg.get("version") == "2.0":
        templates = cfg.get("templates", {})
        if template_name not in templates:
            raise HTTPException(404, f"Template '{template_name}' not found.")
        return {"template": template_name, **templates[template_name]}
    if template_name not in cfg:
        raise HTTPException(404, f"Template '{template_name}' not found.")
    return {"template": template_name, "columns": [], "rules": cfg[template_name]}