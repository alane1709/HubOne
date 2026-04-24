"""
test_step4_5.py
---------------
Test Output Generator (Step 4 & 5):
- Chạy full validation
- Xuất file Excel highlight lỗi
- Xuất JSON summary

Run:
    python test_step4_5.py
"""
import sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from engine.validator        import Validator
from engine.output_generator import generate_output

# ══════════════════════════════════════════════════════
# ✏️  ĐỔI PATH Ở ĐÂY — chỉ cần sửa 1 chỗ này thôi!
# ══════════════════════════════════════════════════════
SAMPLE_FILE = Path(r"C:\Users\DELL\OneDrive - CONG TY TNHH ACACY-SGIM00492\Desktop\PO\_HubONE_ GALDERMA.xlsx")
TEMPLATE    = "HR"
OUTPUT_DIR  = Path("outputs")
# ══════════════════════════════════════════════════════

# ← THÊM VÀO ĐÂY
print(f">>> Đang validate file: {SAMPLE_FILE.name}")
print(f">>> File tồn tại: {SAMPLE_FILE.exists()}")

# ══════════════════════════════════════════════════════
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def ok(msg):      print(f"  {GREEN}✅ PASS{RESET}  {msg}")
def fail(msg):    print(f"  {RED}❌ FAIL{RESET}  {msg}"); sys.exit(1)
def info(msg):    print(f"  {YELLOW}ℹ{RESET}  {msg}")
def section(msg): print(f"\n{BOLD}{CYAN}{'─'*50}{RESET}\n{BOLD}{msg}{RESET}")


# ══════════════════════════════════════════════════════
# TEST 1 — Chạy full validation
# ══════════════════════════════════════════════════════
section("TEST 1 — Full Validation")

if not SAMPLE_FILE.exists():
    fail(f"File không tồn tại: {SAMPLE_FILE}")

try:
    v      = Validator(TEMPLATE)
    result = v.validate(SAMPLE_FILE)
    ok(f"Validation xong: {result['total_errors']} lỗi, status={result['status'].upper()}")
    info(f"Critical: {result['critical']} | Warnings: {result['warnings']}")
except Exception as e:
    fail(f"Lỗi validation: {e}")


# ══════════════════════════════════════════════════════
# TEST 2 — Xuất file output
# ══════════════════════════════════════════════════════
section("TEST 2 — Generate Output Files")

try:
    output = generate_output(SAMPLE_FILE, result, OUTPUT_DIR)
    ok("Output files generated!")
    info(f"📊 Excel : {output['excel_path']}")
    info(f"📋 JSON  : {output['summary_path']}")
except Exception as e:
    fail(f"Lỗi generate output: {e}")


# ══════════════════════════════════════════════════════
# TEST 3 — Kiểm tra file tồn tại
# ══════════════════════════════════════════════════════
section("TEST 3 — Kiểm tra file output tồn tại")

excel_path   = Path(output["excel_path"])
summary_path = Path(output["summary_path"])

if excel_path.exists():
    size_kb = excel_path.stat().st_size / 1024
    ok(f"Excel file tồn tại ({size_kb:.1f} KB)")
else:
    fail("Excel file không được tạo!")

if summary_path.exists():
    ok(f"JSON summary tồn tại")
else:
    fail("JSON summary không được tạo!")


# ══════════════════════════════════════════════════════
# TEST 4 — Kiểm tra nội dung JSON
# ══════════════════════════════════════════════════════
section("TEST 4 — Kiểm tra JSON Summary")

import json
with open(summary_path, encoding="utf-8") as f:
    summary = json.load(f)

print(f"""
  📊 Template   : {summary['template']}
  📋 Total rows : {summary['total_rows']}
  ❌ Error rows : {summary['error_rows']}
  📉 Error %    : {summary['error_pct']}%
  🔴 Critical   : {summary['critical']}
  🟡 Warnings   : {summary['warnings']}
  🏁 Status     : {summary['status'].upper()}
""")

ok("JSON summary hợp lệ")


# ══════════════════════════════════════════════════════
# TEST 5 — Mở file Excel (Windows only)
# ══════════════════════════════════════════════════════
section("TEST 5 — Mở file Excel output")

try:
    os.startfile(str(excel_path))
    ok(f"Đã mở file Excel — kiểm tra highlight lỗi nhé!")
except Exception:
    info(f"Mở thủ công tại: {excel_path}")
    ok("File đã sẵn sàng")


# ══════════════════════════════════════════════════════
print(f"\n{GREEN}{BOLD}{'═'*50}")
print(f"  🎉  ALL TESTS PASSED — Step 4 & 5 Complete!")
print(f"{'═'*50}{RESET}\n")
print(f"  📂 Xem kết quả trong thư mục: {OUTPUT_DIR.resolve()}\n")
