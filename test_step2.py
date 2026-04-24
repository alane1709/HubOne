"""
test_step2.py
-------------
Tests the File Upload API (Step 2).
Requires the FastAPI server to be running first:
    python -m uvicorn api.main:app --reload

Run this in a SEPARATE terminal:
    python test_step2.py
"""

import sys
import requests
from pathlib import Path

BASE_URL = "https://hubone-m7rm.onrender.com"

# ══════════════════════════════════════════════════════
# ✏️  ĐỔI PATH Ở ĐÂY — chỉ cần sửa 1 chỗ này thôi!
# ══════════════════════════════════════════════════════
SAMPLE_FILE = Path(r"C:\Users\DELL\OneDrive - CONG TY TNHH ACACY-SGIM00492\Desktop\PO\Test Template.xlsx")
TEMPLATE    = "HR"
# ══════════════════════════════════════════════════════

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def ok(msg):      print(f"  {GREEN}✅ PASS{RESET}  {msg}")
def fail(msg):    print(f"  {RED}❌ FAIL{RESET}  {msg}"); sys.exit(1)
def section(msg): print(f"\n{BOLD}{CYAN}{'─'*50}{RESET}\n{BOLD}{msg}{RESET}")


section("TEST 1 — Server health check")
try:
    r = requests.get(f"{BASE_URL}/", timeout=3)
    if r.status_code == 200:
        ok(f"Server is running: {r.json()['message']}")
    else:
        fail(f"Unexpected status: {r.status_code}")
except Exception:
    print(f"\n  {RED}❌ Cannot connect to server!{RESET}")
    print(f"  Chạy lệnh này trước:")
    print(f"  {YELLOW}python -m uvicorn api.main:app --reload{RESET}\n")
    sys.exit(1)


section("TEST 2 — GET /templates")
r    = requests.get(f"{BASE_URL}/templates")
data = r.json()
print(f"  Available templates: {data['templates']}")
if TEMPLATE in data["templates"]:
    ok("Templates endpoint working")
else:
    fail(f"Template '{TEMPLATE}' không có trong danh sách!")


section("TEST 3 — Upload valid .xlsx file")
if not SAMPLE_FILE.exists():
    fail(f"File không tồn tại: {SAMPLE_FILE}")

with open(SAMPLE_FILE, "rb") as f:
    r = requests.post(
        f"{BASE_URL}/upload",
        files={"file": (SAMPLE_FILE.name, f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"template_name": TEMPLATE},
    )
if r.status_code == 200:
    meta = r.json()["metadata"]
    ok(f"Upload successful! file_id={meta['file_id']}, size={meta['size_kb']}KB")
    print(f"     Saved as: {meta['saved_as']}")
else:
    fail(f"Upload failed: {r.status_code} — {r.text}")


section("TEST 4 — Reject unknown template")
with open(SAMPLE_FILE, "rb") as f:
    r = requests.post(
        f"{BASE_URL}/upload",
        files={"file": (SAMPLE_FILE.name, f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"template_name": "INVALID"},
    )
if r.status_code == 400:
    ok("Correctly rejected invalid template")
else:
    fail(f"Should return 400, got {r.status_code}")


section("TEST 5 — Reject non-.xlsx file")
r = requests.post(
    f"{BASE_URL}/upload",
    files={"file": ("report.csv", b"fake content", "text/csv")},
    data={"template_name": TEMPLATE},
)
if r.status_code == 400:
    ok("Correctly rejected .csv file")
else:
    fail(f"Should return 400, got {r.status_code}")


section("TEST 6 — GET /uploads")
r    = requests.get(f"{BASE_URL}/uploads")
data = r.json()
print(f"  Total files on server: {data['total']}")
if data["total"] >= 1:
    ok(f"Uploads list working — {data['total']} file(s) found")
    for f in data["files"][:3]:
        print(f"     📄 {f['filename']} ({f['size_kb']}KB)")
else:
    fail("No uploaded files found!")


print(f"\n{GREEN}{BOLD}{'═'*50}")
print(f"  🎉  ALL TESTS PASSED — Step 2 Complete!")
print(f"{'═'*50}{RESET}\n")