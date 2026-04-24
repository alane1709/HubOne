"""
test_step1.py
-------------
Run this to verify Step 1 is working correctly.

Usage:
    cd data_validation_platform
    python test_step1.py
"""

import sys
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent))

from engine.config_loader import (
    load_config,
    list_templates,
    get_rules_by_tier,
    get_required_columns,
    get_column_rule,
)

# ── Color helpers ─────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def ok(msg):  print(f"  {GREEN}✅ PASS{RESET}  {msg}")
def fail(msg): print(f"  {RED}❌ FAIL{RESET}  {msg}"); sys.exit(1)
def section(msg): print(f"\n{BOLD}{CYAN}{'─'*50}{RESET}\n{BOLD}{msg}{RESET}")


# ══════════════════════════════════════════════════════
# TEST 1 — List all templates
# ══════════════════════════════════════════════════════
section("TEST 1 — List available templates")

templates = list_templates()
print(f"  Found templates: {templates}")

for expected in ["HR", "Payroll", "HC_Plan"]:
    if expected in templates:
        ok(f"Template '{expected}' exists")
    else:
        fail(f"Template '{expected}' missing from config!")


# ══════════════════════════════════════════════════════
# TEST 2 — Load HR config
# ══════════════════════════════════════════════════════
section("TEST 2 — Load HR template config")

hr_rules = load_config("HR")
print(f"  Total columns configured: {len(hr_rules)}")

if len(hr_rules) > 0:
    ok(f"Loaded {len(hr_rules)} column rules for HR")
else:
    fail("HR config returned 0 rules!")


# ══════════════════════════════════════════════════════
# TEST 3 — Rules sorted by tier
# ══════════════════════════════════════════════════════
section("TEST 3 — Rules sorted by tier (Tier 1 first)")

tiers = [r.tier for r in hr_rules]
if tiers == sorted(tiers):
    ok(f"Rules correctly sorted by tier: {tiers}")
else:
    fail(f"Rules NOT sorted! Got: {tiers}")


# ══════════════════════════════════════════════════════
# TEST 4 — Filter by tier
# ══════════════════════════════════════════════════════
section("TEST 4 — Filter rules by tier")

for tier_num in [1, 2, 3]:
    tier_rules = get_rules_by_tier(hr_rules, tier_num)
    print(f"  Tier {tier_num} columns: {[r.column_name for r in tier_rules]}")
    ok(f"Tier {tier_num} → {len(tier_rules)} rule(s)")


# ══════════════════════════════════════════════════════
# TEST 5 — Required columns
# ══════════════════════════════════════════════════════
section("TEST 5 — Get required columns")

required = get_required_columns(hr_rules)
print(f"  Required columns: {required}")

if "employee_id" in required and "full_name" in required:
    ok("employee_id and full_name are required ✓")
else:
    fail("Required columns missing expected entries!")


# ══════════════════════════════════════════════════════
# TEST 6 — Lookup specific column rule
# ══════════════════════════════════════════════════════
section("TEST 6 — Lookup specific column rule")

email_rule = get_column_rule(hr_rules, "email")
if email_rule:
    ok(f"Found rule for 'email': type={email_rule.rule_type}, severity={email_rule.severity}")
    print(f"     regex pattern: {email_rule.rule_detail}")
else:
    fail("Could not find rule for 'email'!")

missing_rule = get_column_rule(hr_rules, "nonexistent_col")
if missing_rule is None:
    ok("Correctly returns None for unknown column")
else:
    fail("Should return None for unknown column!")


# ══════════════════════════════════════════════════════
# TEST 7 — Load all 3 templates without error
# ══════════════════════════════════════════════════════
section("TEST 7 — Load Payroll + HC_Plan templates")

for tmpl in ["Payroll", "HC_Plan"]:
    rules = load_config(tmpl)
    ok(f"'{tmpl}' loaded → {len(rules)} columns")
    for r in rules:
        print(f"       [{r.tier}] {r.column_name:20s} type={r.data_type:6s} required={str(r.is_required):5s} rule={r.rule_type}")


# ══════════════════════════════════════════════════════
# TEST 8 — Error handling: unknown template
# ══════════════════════════════════════════════════════
section("TEST 8 — Error handling: unknown template")

try:
    load_config("INVALID_TEMPLATE")
    fail("Should have raised KeyError!")
except KeyError as e:
    ok(f"Correctly raises KeyError: {e}")


# ══════════════════════════════════════════════════════
print(f"\n{GREEN}{BOLD}{'═'*50}")
print(f"  🎉  ALL TESTS PASSED — Step 1 Complete!")
print(f"{'═'*50}{RESET}\n")
