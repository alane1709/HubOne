"""
test_step3.py
-------------
Test Validation Engine — Tier 1, 2, 3

Run:
    python test_step3.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from engine.validator import Validator

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
def info(msg):    print(f"  {YELLOW}ℹ{RESET}  {msg}")


# ══════════════════════════════════════════════════════
# TEST 1 — Khởi tạo Validator
# ══════════════════════════════════════════════════════
section("TEST 1 — Khởi tạo Validator")
try:
    v = Validator(TEMPLATE)
    ok(f"Validator khởi tạo thành công cho template '{TEMPLATE}'")
    info(f"Số rules: {len(v.rules)}")
except Exception as e:
    fail(f"Lỗi khởi tạo: {e}")


# ══════════════════════════════════════════════════════
# TEST 2 — Chạy validation trên file thật
# ══════════════════════════════════════════════════════
section("TEST 2 — Chạy validation trên file thật")

if not SAMPLE_FILE.exists():
    fail(f"File không tồn tại: {SAMPLE_FILE}")

try:
    result = v.validate(SAMPLE_FILE)
    ok(f"Validation chạy xong!")
except Exception as e:
    fail(f"Lỗi khi chạy validation: {e}")


# ══════════════════════════════════════════════════════
# TEST 3 — Xem Summary
# ══════════════════════════════════════════════════════
section("TEST 3 — Validation Summary")

print(f"""
  📊 Template     : {result['template']}
  📋 Total rows   : {result['total_rows']}
  ❌ Error rows   : {result['error_rows']}
  📉 Error %      : {result['error_pct']}%
  🔴 Critical     : {result['critical']}
  🟡 Warnings     : {result['warnings']}
  🏁 Status       : {result['status'].upper()}
""")

ok("Summary generated")


# ══════════════════════════════════════════════════════
# TEST 4 — Xem chi tiết lỗi
# ══════════════════════════════════════════════════════
section("TEST 4 — Chi tiết lỗi (top 10)")

errors = result["errors"]
if errors:
    info(f"Tổng số lỗi tìm thấy: {len(errors)}")
    print()
    for e in errors[:10]:
        severity_icon = "🔴" if e["severity"] == "critical" else "🟡"
        print(f"  {severity_icon} Row {e['row_id']:>3} | {e['column_name']:<20} | {e['error_type']:<20} | {e['message'][:60]}")
    if len(errors) > 10:
        info(f"... và {len(errors) - 10} lỗi khác")
    ok("Errors listed successfully")
else:
    info("Không tìm thấy lỗi nào — file sạch!")
    ok("No errors found")


# ══════════════════════════════════════════════════════
# TEST 5 — Lỗi theo nhóm error_type
# ══════════════════════════════════════════════════════
section("TEST 5 — Lỗi theo nhóm")

from collections import Counter
type_counts = Counter(e["error_type"] for e in errors)
if type_counts:
    for error_type, count in type_counts.most_common():
        print(f"  {'🔴' if 'CRITICAL' in error_type.upper() or error_type in ['MISSING_COLUMN','NULL_REQUIRED','DUPLICATE_KEY','WRONG_DATATYPE'] else '🟡'} {error_type:<25} : {count} lỗi")
    ok("Error grouping working")
else:
    ok("Không có lỗi để nhóm")


# ══════════════════════════════════════════════════════
print(f"\n{GREEN}{BOLD}{'═'*50}")
print(f"  🎉  ALL TESTS PASSED — Step 3 Complete!")
print(f"{'═'*50}{RESET}\n")
