"""
config_loader.py  v2.2
----------------------
Schema v2 — columns + rules separated.
Thêm number formats vào FORMAT_PATTERNS.
"""

import json
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

CONFIG_PATH = Path(__file__).parent.parent / "config" / "template_config.json"

# ── DATE FORMAT MAP ───────────────────────────────────────────────────────────
DATE_FORMAT_MAP = {
    "YYYY-MM-DD": "%Y-%m-%d",
    "DD/MM/YYYY": "%d/%m/%Y",
    "MM/DD/YYYY": "%m/%d/%Y",
    "YYYY/MM/DD": "%Y/%m/%d",
    "YYYY-MM":    "%Y-%m",
    "DD-MM-YYYY": "%d-%m-%Y",
    "YYYYMMDD":   "%Y%m%d",
}

# ── FORMAT PATTERNS (text/date) ───────────────────────────────────────────────
FORMAT_PATTERNS = {
    # Text formats — regex
    "email":      r"^[\w\.\+\-]+@[\w\-]+\.[\w\.\-]+$",
    "phone_vn":   r"^\+?[0-9]{9,15}$",
    "phone_intl": r"^\+?[1-9]\d{6,14}$",
    "url":        r"^https?://[\w\-\.]+(:\d+)?(/.*)?$",
    # Date formats — regex (strict)
    "YYYY-MM-DD": r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$",
    "DD/MM/YYYY": r"^(0[1-9]|[12]\d|3[01])/(0[1-9]|1[0-2])/\d{4}$",
    "YYYY-MM":    r"^\d{4}-(0[1-9]|1[0-2])$",
    "YYYYMMDD":   r"^\d{4}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])$",
}

# ── NUMBER FORMATS — function-based check ─────────────────────────────────────
# value: float đã parse được
NUMBER_FORMAT_CHECKS = {
    "integer":          lambda v: v == int(v),
    "positive":         lambda v: v > 0,
    "positive_integer": lambda v: v > 0 and v == int(v),
    "non_negative":     lambda v: v >= 0,
    "percent":          lambda v: 0 <= v <= 100,
    "currency_vn":      lambda v: v >= 0 and v % 1000 == 0,
    "year":             lambda v: 1900 <= int(v) <= 2100,
}

NUMBER_FORMAT_MESSAGES = {
    "integer":          "phải là số nguyên",
    "positive":         "phải là số dương (> 0)",
    "positive_integer": "phải là số nguyên dương (> 0)",
    "non_negative":     "phải >= 0",
    "percent":          "phải trong khoảng 0–100",
    "currency_vn":      "phải là số nguyên >= 0, bội số 1000",
    "year":             "phải là năm hợp lệ (1900–2100)",
}

ALL_NUMBER_FORMATS = list(NUMBER_FORMAT_CHECKS.keys())
ALL_TEXT_FORMATS   = ["email", "phone_vn", "phone_intl", "url"]
ALL_DATE_FORMATS   = list(DATE_FORMAT_MAP.keys())


# ── Data models ───────────────────────────────────────────────────────────────

@dataclass
class ColumnDef:
    name:               str
    data_type:          str           # text | number | date
    is_required:        bool
    allow_null_percent: float
    date_format:        Optional[str] = None

    def __post_init__(self):
        assert self.data_type in {"text", "number", "date"}, \
            f"[{self.name}] data_type must be text|number|date"
        assert 0 <= self.allow_null_percent <= 100, \
            f"[{self.name}] allow_null_percent must be 0-100"
        if self.date_format and self.date_format not in DATE_FORMAT_MAP:
            raise ValueError(
                f"[{self.name}] date_format '{self.date_format}' not supported. "
                f"Supported: {list(DATE_FORMAT_MAP.keys())}"
            )

    @property
    def strftime_format(self) -> Optional[str]:
        return DATE_FORMAT_MAP.get(self.date_format) if self.date_format else None


@dataclass
class RuleDef:
    id:              str
    type:            str
    scope:           str
    priority:        int
    severity:        str
    enabled:         bool
    column:          Optional[str]   = None
    columns:         list            = field(default_factory=list)
    params:          dict            = field(default_factory=dict)
    conditions:      list            = field(default_factory=list)
    condition_logic: str             = "AND"
    then:            list            = field(default_factory=list)
    condition:       Optional[dict]  = None   # backward compat
    message:         Optional[str]   = None

    def __post_init__(self):
        assert self.scope in {"column","row","table","dataset"}, \
            f"[{self.id}] invalid scope: {self.scope}"
        assert self.severity in {"critical","warning"}, \
            f"[{self.id}] invalid severity: {self.severity}"
        if self.condition and not self.conditions:
            self.conditions = [self.condition]
        if self.column and not self.columns:
            self.columns = [self.column]


@dataclass
class TemplateDef:
    name:    str
    columns: list[ColumnDef]
    rules:   list[RuleDef]

    @property
    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]

    @property
    def required_columns(self) -> list[str]:
        return [c.name for c in self.columns if c.is_required]

    def get_column(self, name: str) -> Optional[ColumnDef]:
        key = name.strip().lower()
        for c in self.columns:
            if c.name.strip().lower() == key:
                return c
        return None

    def get_rules_by_scope(self, scope: str) -> list[RuleDef]:
        return [r for r in self.rules if r.scope == scope and r.enabled]


# ── Public API ────────────────────────────────────────────────────────────────

def load_config(template_name: str, config_path: Optional[Path] = None) -> TemplateDef:
    path = config_path or CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    version = raw.get("version", "1.0")
    return _parse_v2(template_name, raw) if version == "2.0" else _parse_v1(template_name, raw)


def list_templates(config_path: Optional[Path] = None) -> list[str]:
    path = config_path or CONFIG_PATH
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    if raw.get("version") == "2.0":
        return list(raw["templates"].keys())
    return [k for k in raw.keys() if not k.startswith("_")]


# ── v2 Parser ─────────────────────────────────────────────────────────────────

def _parse_v2(template_name: str, raw: dict) -> TemplateDef:
    templates = raw.get("templates", {})
    if template_name not in templates:
        raise KeyError(f"Template '{template_name}' not found. Available: {list(templates.keys())}")
    tmpl = templates[template_name]

    columns = [
        ColumnDef(
            name               = c["name"],
            data_type          = c["data_type"],
            is_required        = c.get("is_required", False),
            allow_null_percent = c.get("allow_null_percent", 100),
            date_format        = c.get("date_format"),
        )
        for c in tmpl.get("columns", [])
    ]

    rules = sorted([
        RuleDef(
            id             = r["id"],
            type           = r["type"],
            scope          = r.get("scope", _infer_scope(r["type"])),
            priority       = r.get("priority", 99),
            severity       = r.get("severity", "warning"),
            enabled        = r.get("enabled", True),
            column         = r.get("column"),
            columns        = r.get("columns", []),
            params         = r.get("params", {}),
            conditions     = r.get("conditions", []),
            condition_logic= r.get("condition_logic", "AND"),
            then           = r.get("then", []),
            condition      = r.get("condition"),
            message        = r.get("message"),
        )
        for r in tmpl.get("rules", [])
    ], key=lambda x: x.priority)

    return TemplateDef(name=template_name, columns=columns, rules=rules)


# ── v1 Parser ─────────────────────────────────────────────────────────────────

def _parse_v1(template_name: str, raw: dict) -> TemplateDef:
    if template_name not in raw:
        raise KeyError(f"Template '{template_name}' not found.")
    flat, columns, rules, rule_id = raw[template_name], [], [], 1

    for col in flat:
        col_name  = col.get("column_name", col.get("name", ""))
        dtype     = col.get("data_type", "text")
        severity  = col.get("severity", "warning")
        tier      = col.get("tier", 2)
        rule_type = col.get("rule_type", "none")
        detail    = col.get("rule_detail", "")

        columns.append(ColumnDef(
            name=col_name, data_type=dtype,
            is_required=col.get("is_required", False),
            allow_null_percent=col.get("allow_null_percent", 100),
        ))

        if rule_type not in ("none", "", None):
            scope  = _infer_scope(rule_type)
            params = {}
            rt     = rule_type
            if rt == "regex":   params = {"pattern": detail}
            elif rt == "range":
                import re as _re
                m = _re.match(r"([><=!]+)\s*([\d.]+)", detail)
                if m: params = {"operator": m.group(1), "value": float(m.group(2))}
            elif rt in ("cross_column","compare"):
                rt = "compare"
                import re as _re
                m = _re.match(r"(\w+)\s*([><=!]+)\s*(\w+)", detail)
                if m: params = {"left": m.group(1), "operator": m.group(2), "right": m.group(3)}
            elif rt == "no_future_date": params = {}

            rules.append(RuleDef(
                id=f"v1_r{rule_id:03d}", type=rt, scope=scope,
                priority=tier*10+rule_id, severity=severity, enabled=True,
                column=col_name, columns=[col_name], params=params,
            ))
            rule_id += 1

    rules.sort(key=lambda r: r.priority)
    return TemplateDef(name=template_name, columns=columns, rules=rules)


def _infer_scope(rule_type: str) -> str:
    return {
        "unique":"table","null_percent":"table",
        "regex":"column","range":"column","format_check":"column","no_future_date":"column",
        "compare":"row","conditional":"row","formula":"row","sum_check":"row",
        "ref_integrity":"dataset",
    }.get(rule_type, "column")