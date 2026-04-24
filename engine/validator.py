"""
validator.py  v2.3
------------------
Vectorized validation — pandas operations thay for loop.
- Datatype check: vectorized
- Null check: vectorized
- Range check: vectorized
- Format check: vectorized (regex via str.match)
- Skip rule nếu cell đã WRONG_DATATYPE
- Number formats: integer, positive, positive_integer, non_negative, percent, currency_vn, year
- PERFORMANCE: cache notnull mask, vectorized date/compare/conditional/formula
"""

import re
import ast as _ast
import operator as _op
import pandas as pd
import numpy as np
from datetime import datetime, date as date_type
from pathlib import Path
from dataclasses import dataclass, field as dc_field
from typing import Optional

from engine.config_loader import (
    load_config, TemplateDef, ColumnDef, RuleDef,
    FORMAT_PATTERNS, DATE_FORMAT_MAP,
    NUMBER_FORMAT_CHECKS, NUMBER_FORMAT_MESSAGES,
)


# ── Error model ────────────────────────────────────────────────────────────────

@dataclass
class ValidationError:
    row_id:      int
    column_name: str
    error_type:  str
    severity:    str
    message:     str
    rule_id:     str = ""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _norm(s) -> str:
    return str(s).strip().lower()

def _is_empty(val) -> bool:
    if val is None: return True
    if isinstance(val, float) and np.isnan(val): return True
    return str(val).strip() == ""

def _parse_number(val) -> Optional[float]:
    try:
        return float(str(val).replace(",","").strip())
    except (ValueError, TypeError):
        return None

def _parse_date_strict(val, strftime_fmt: str) -> Optional[datetime]:
    if _is_empty(val): return None
    if isinstance(val, (datetime, date_type)):
        return datetime.combine(val, datetime.min.time()) if isinstance(val, date_type) else val
    s = str(val).strip().split(" ")[0].split("T")[0]
    try:
        return datetime.strptime(s, strftime_fmt)
    except ValueError:
        return None

def _parse_date_for_compare(val, col_def: Optional[ColumnDef]) -> Optional[datetime]:
    if _is_empty(val): return None
    if isinstance(val, (datetime, date_type)):
        return datetime.combine(val, datetime.min.time()) if isinstance(val, date_type) else val
    s = str(val).strip().split(" ")[0].split("T")[0]
    if col_def and col_def.strftime_format:
        return _parse_date_strict(s, col_def.strftime_format)
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None

def _make_ops() -> dict:
    return {">":  lambda a,b: a>b, ">=": lambda a,b: a>=b,
            "<":  lambda a,b: a<b, "<=": lambda a,b: a<=b,
            "==": lambda a,b: a==b, "!=": lambda a,b: a!=b}


# ── Column Engine — vectorized ────────────────────────────────────────────────

class ColumnEngine:
    """scope=column: vectorized checks per column."""

    def run(self, rule: RuleDef, df: pd.DataFrame, tmpl: TemplateDef,
            bad_rows: set, cache: dict) -> list[ValidationError]:
        col_key = _norm(rule.column) if rule.column else None
        if not col_key or col_key not in df.columns:
            return []
        handler = {
            "format_check":   self._format_check,
            "regex":          self._regex,
            "range":          self._range,
            "no_future_date": self._no_future_date,
        }.get(rule.type)
        return handler(rule, df, col_key, tmpl, bad_rows, cache) if handler else []

    def _get_notnull(self, series: pd.Series, cache: dict) -> pd.Series:
        """Cache notnull mask per column to avoid recomputation."""
        key = id(series)
        if key not in cache:
            cache[key] = series.notna() & (series.astype(str).str.strip() != "")
        return cache[key]

    def _skip_bad(self, series: pd.Series, bad_rows: set) -> pd.Series:
        if not bad_rows:
            return pd.Series(True, index=series.index)
        return ~series.index.isin(bad_rows)

    # ── format_check ──────────────────────────────────────────────────────────
    def _format_check(self, rule, df, col_key, tmpl, bad_rows, cache):
        errors  = []
        fmt     = rule.params.get("format", "")
        col_def = tmpl.get_column(rule.column)
        series  = df[col_key]
        notnull = self._get_notnull(series, cache)
        valid   = notnull & self._skip_bad(series, bad_rows)
        s       = series[valid].astype(str).str.strip()

        if not fmt:
            return errors

        # ── Number format ─────────────────────────────────────────────────────
        if fmt in NUMBER_FORMAT_CHECKS:
            check_fn = NUMBER_FORMAT_CHECKS[fmt]
            msg_tmpl = NUMBER_FORMAT_MESSAGES.get(fmt, f"không hợp lệ theo format '{fmt}'")
            nums = pd.to_numeric(s.str.replace(",","",regex=False), errors="coerce")
            bad_mask = nums.isna() | ~nums.map(lambda v: check_fn(v) if pd.notna(v) else False)
            for idx in s[bad_mask].index:
                errors.append(ValidationError(
                    row_id=int(idx)+2, column_name=rule.column,
                    error_type="WRONG_FORMAT", severity=rule.severity,
                    message=rule.message or f"'{series.at[idx]}' {msg_tmpl} trong cột '{rule.column}'.",
                    rule_id=rule.id,
                ))
            return errors

        # ── Date format (strict) ───────────────────────────────────────────────
        if fmt in DATE_FORMAT_MAP:
            strftime_fmt = DATE_FORMAT_MAP[fmt]
            bad_mask = pd.Series(False, index=s.index)
            sv = s.copy()
            for fmt_key, std_fmt in DATE_FORMAT_MAP.items():
                parsed = pd.to_datetime(sv, format=std_fmt, errors="coerce")
                if fmt == fmt_key:
                    bad_mask = parsed.isna() & sv.str.strip().str.len() > 0
                    break
            # Fallback: check with the specific format
            try:
                parsed = pd.to_datetime(s, format=strftime_fmt, errors="coerce")
                bad_mask = parsed.isna() & s.str.strip().str.len() > 0
            except Exception:
                pass
            for idx in s[bad_mask].index:
                errors.append(ValidationError(
                    row_id=int(idx)+2, column_name=rule.column,
                    error_type="WRONG_FORMAT", severity=rule.severity,
                    message=rule.message or f"'{series.at[idx]}' không đúng định dạng ngày '{fmt}' trong cột '{rule.column}'.",
                    rule_id=rule.id,
                ))
            return errors

        # ── Text/regex pattern ─────────────────────────────────────────────────
        pattern = FORMAT_PATTERNS.get(fmt, fmt)
        try:
            rx = re.compile(pattern)
        except re.error as e:
            return [ValidationError(0, rule.column, "CONFIG_ERROR", "critical",
                                    f"Rule '{rule.id}': pattern lỗi — {e}", rule.id)]
        bad_mask = ~s.str.match(pattern, na=False)
        for idx in s[bad_mask].index:
            errors.append(ValidationError(
                row_id=int(idx)+2, column_name=rule.column,
                error_type="WRONG_FORMAT", severity=rule.severity,
                message=rule.message or f"'{series.at[idx]}' không đúng định dạng '{fmt}' trong cột '{rule.column}'.",
                rule_id=rule.id,
            ))
        return errors

    # ── regex ─────────────────────────────────────────────────────────────────
    def _regex(self, rule, df, col_key, tmpl, bad_rows, cache):
        pattern = rule.params.get("pattern","")
        if not pattern: return []
        try:
            re.compile(pattern)
        except re.error as e:
            return [ValidationError(0, rule.column or "", "CONFIG_ERROR", "critical",
                                    f"Rule '{rule.id}': regex lỗi — {e}", rule.id)]
        series  = df[col_key]
        notnull = self._get_notnull(series, cache)
        valid   = notnull & self._skip_bad(series, bad_rows)
        s       = series[valid].astype(str).str.strip()
        bad_mask= ~s.str.match(pattern, na=False)
        errors  = []
        for idx in s[bad_mask].index:
            errors.append(ValidationError(
                row_id=int(idx)+2, column_name=rule.column,
                error_type="INVALID_FORMAT", severity=rule.severity,
                message=rule.message or f"'{series.at[idx]}' không khớp pattern trong cột '{rule.column}'.",
                rule_id=rule.id,
            ))
        return errors

    # ── range ─────────────────────────────────────────────────────────────────
    def _range(self, rule, df, col_key, tmpl, bad_rows, cache):
        op        = rule.params.get("operator",">")
        threshold = float(rule.params.get("value",0))
        ops       = _make_ops()
        check     = ops.get(op)
        if check is None:
            return [ValidationError(0,"","CONFIG_ERROR","critical",
                                    f"Rule '{rule.id}': operator '{op}' không hợp lệ.", rule.id)]
        series  = df[col_key]
        notnull = self._get_notnull(series, cache)
        valid   = notnull & self._skip_bad(series, bad_rows)
        s       = series[valid].astype(str).str.replace(",","",regex=False)
        nums    = pd.to_numeric(s, errors="coerce")
        parsed  = nums.notna()
        to_check= nums[parsed]
        bad_mask= ~to_check.map(lambda v: check(v, threshold))
        errors  = []
        for idx in to_check[bad_mask].index:
            errors.append(ValidationError(
                row_id=int(idx)+2, column_name=rule.column,
                error_type="OUT_OF_RANGE", severity=rule.severity,
                message=rule.message or f"'{series.at[idx]}' vi phạm '{op} {threshold}' trong cột '{rule.column}'.",
                rule_id=rule.id,
            ))
        return errors

    # ── no_future_date — VECTORIZED ────────────────────────────────────────────
    def _no_future_date(self, rule, df, col_key, tmpl, bad_rows, cache):
        today   = datetime.now().date()
        col_def = tmpl.get_column(rule.column or "")
        series  = df[col_key]
        notnull = self._get_notnull(series, cache)
        valid   = notnull & self._skip_bad(series, bad_rows)
        s       = series[valid]

        # Vectorized: skip datetime objects, parse rest
        strftime_fmt = col_def.strftime_format if col_def else None

        def _parse_vec(series: pd.Series, fmt: Optional[str]):
            result = pd.Series(index=series.index, dtype=object)
            for idx in series.index:
                val = series.at[idx]
                if isinstance(val, (datetime, date_type)):
                    result.at[idx] = val
                else:
                    result.at[idx] = _parse_date_strict(val, fmt) if fmt else _parse_date_for_compare(val, col_def)
            return result

        dates = _parse_vec(s, strftime_fmt)
        today_dt = datetime.combine(today, datetime.min.time())

        errors = []
        for idx in s.index:
            val = s.at[idx]
            dt  = dates.at[idx]
            if dt is None:
                errors.append(ValidationError(
                    row_id=int(idx)+2, column_name=rule.column,
                    error_type="WRONG_FORMAT", severity=rule.severity,
                    message=f"'{val}' không parse được thành ngày trong cột '{rule.column}'.",
                    rule_id=rule.id,
                ))
            elif dt.date() > today:
                errors.append(ValidationError(
                    row_id=int(idx)+2, column_name=rule.column,
                    error_type="FUTURE_DATE", severity=rule.severity,
                    message=rule.message or f"'{val}' là ngày tương lai trong cột '{rule.column}'.",
                    rule_id=rule.id,
                ))
        return errors


# ── Row Engine ────────────────────────────────────────────────────────────────

class RowEngine:
    """scope=row — logic giữa các cột trong cùng row."""

    def run(self, rule: RuleDef, df: pd.DataFrame, tmpl: TemplateDef,
            bad_rows: set = None) -> list[ValidationError]:
        handler = {
            "compare":     self._compare,
            "conditional": self._conditional,
            "formula":     self._formula,
            "sum_check":   self._sum_check,
        }.get(rule.type)
        return handler(rule, df, tmpl) if handler else []

    # ── compare — vectorized with batch parse ──────────────────────────────────
    def _compare(self, rule, df, tmpl, _extra=None) -> list[ValidationError]:
        params    = rule.params
        left_key  = _norm(params.get("left",""))
        right_key = _norm(params.get("right",""))
        op        = params.get("operator",">=")

        # v1 expr compat
        if not left_key:
            expr = params.get("expr","")
            m = re.match(r"(\w+)\s*([><=!]+)\s*(\w+)", expr)
            if m: left_key, op, right_key = _norm(m.group(1)), m.group(2), _norm(m.group(3))

        if not left_key or not right_key:
            return [ValidationError(0,"","CONFIG_ERROR","critical",
                                    f"Rule '{rule.id}': compare cần 'left' và 'right'.", rule.id)]

        missing = [c for c in [left_key, right_key] if c not in df.columns]
        if missing:
            return [ValidationError(0,", ".join(missing),"MISSING_COLUMN","critical",
                                    f"Rule '{rule.id}': cột '{', '.join(missing)}' không tồn tại.", rule.id)]

        ops   = _make_ops()
        check = ops.get(op)
        if not check:
            return [ValidationError(0,"","CONFIG_ERROR","critical",
                                    f"Rule '{rule.id}': operator '{op}' không hợp lệ.", rule.id)]

        left_def  = tmpl.get_column(left_key)
        right_def = tmpl.get_column(right_key)
        dtype     = (left_def.data_type if left_def else None) or \
                    (right_def.data_type if right_def else None)
        errors = []

        va_col = df[left_key]
        vb_col = df[right_key]

        if dtype == "date":
            # Vectorized date parsing
            def _parse_date_col(col, col_def):
                result = pd.Series(index=col.index, dtype=object)
                for idx in col.index:
                    result.at[idx] = _parse_date_for_compare(col.at[idx], col_def)
                return result

            a_series = _parse_date_col(va_col, left_def)
            b_series = _parse_date_col(vb_col, right_def)

            valid = va_col.astype(str).str.strip().str.len() > 0 & \
                    vb_col.astype(str).str.strip().str.len() > 0
            a_valid = valid & a_series.notna()
            b_valid = valid & b_series.notna()

            for idx in df.index:
                va, vb = va_col.at[idx], vb_col.at[idx]
                if _is_empty(va) or _is_empty(vb): continue
                if not a_valid.at[idx]:
                    errors.append(ValidationError(int(idx)+2, left_key, "WRONG_FORMAT",
                        rule.severity, f"Không parse được ngày '{va}'.", rule.id)); continue
                if not b_valid.at[idx]:
                    errors.append(ValidationError(int(idx)+2, right_key, "WRONG_FORMAT",
                        rule.severity, f"Không parse được ngày '{vb}'.", rule.id)); continue
                a, b = a_series.at[idx], b_series.at[idx]
                if not check(a, b):
                    col_label = _extra.get("col_label", left_key) if _extra else left_key
                    errors.append(ValidationError(
                        row_id=int(idx)+2, column_name=col_label,
                        error_type="COMPARE_FAIL", severity=rule.severity,
                        message=rule.message or f"'{left_key}'={va} phải {op} '{right_key}'={vb}.",
                        rule_id=rule.id,
                    ))

        elif dtype == "number":
            # Vectorized number parsing
            def _num(col):
                return pd.to_numeric(
                    col.astype(str).str.replace(",","",regex=False),
                    errors="coerce"
                )
            a_nums = _num(va_col)
            b_nums = _num(vb_col)
            valid = a_nums.notna() & b_nums.notna()

            for idx in df.index:
                va, vb = va_col.at[idx], vb_col.at[idx]
                if _is_empty(va) or _is_empty(vb): continue
                a, b = a_nums.at[idx], b_nums.at[idx]
                if pd.isna(a) or pd.isna(b): continue
                if not check(a, b):
                    col_label = _extra.get("col_label", left_key) if _extra else left_key
                    errors.append(ValidationError(
                        row_id=int(idx)+2, column_name=col_label,
                        error_type="COMPARE_FAIL", severity=rule.severity,
                        message=rule.message or f"'{left_key}'={va} phải {op} '{right_key}'={vb}.",
                        rule_id=rule.id,
                    ))
        else:
            for idx in df.index:
                va, vb = str(va_col.at[idx]).strip(), str(vb_col.at[idx]).strip()
                if not va or not vb: continue
                if not check(va, vb):
                    col_label = _extra.get("col_label", left_key) if _extra else left_key
                    errors.append(ValidationError(
                        row_id=int(idx)+2, column_name=col_label,
                        error_type="COMPARE_FAIL", severity=rule.severity,
                        message=rule.message or f"'{left_key}'={va} phải {op} '{right_key}'={vb}.",
                        rule_id=rule.id,
                    ))
        return errors

    # ── conditional ───────────────────────────────────────────────────────────
    def _conditional(self, rule, df, tmpl) -> list[ValidationError]:
        conditions = rule.conditions
        logic      = rule.condition_logic.upper()
        thens      = rule.then
        errors     = []

        if not conditions:
            return [ValidationError(0,"","CONFIG_ERROR","critical",
                                    f"Rule '{rule.id}': cần ít nhất 1 condition.", rule.id)]

        cond_ops = {
            "equals":       lambda a,b: _norm(str(a))==_norm(str(b)),
            "not_equals":   lambda a,b: _norm(str(a))!=_norm(str(b)),
            "in":           lambda a,b: _norm(str(a)) in [_norm(str(x)) for x in (b if isinstance(b,list) else [b])],
            "not_in":       lambda a,b: _norm(str(a)) not in [_norm(str(x)) for x in (b if isinstance(b,list) else [b])],
            "is_null":      lambda a,b: _is_empty(a),
            "is_not_null":  lambda a,b: not _is_empty(a),
            "greater_than": lambda a,b: (_parse_number(a) or 0) > float(b),
            "less_than":    lambda a,b: (_parse_number(a) or 0) < float(b),
            "contains":     lambda a,b: str(b).lower() in str(a).lower(),
        }

        # Vectorized condition evaluation per column
        cond_results = {}
        for cond in conditions:
            cc  = _norm(cond.get("column",""))
            cop = cond.get("operator","equals")
            cv  = cond.get("value")
            if cc not in df.columns:
                cond_results[cc] = pd.Series(False, index=df.index)
                continue

            series = df[cc]
            fn = cond_ops.get(cop)
            if fn is None:
                cond_results[cc] = pd.Series(False, index=df.index)
                continue

            if cop == "is_null":
                cond_results[cc] = series.astype(str).str.strip().str.len() == 0
            elif cop == "is_not_null":
                cond_results[cc] = series.astype(str).str.strip().str.len() > 0
            elif cop in ("equals", "not_equals", "in", "not_in", "contains"):
                cond_results[cc] = series.astype(str).str.strip().str.lower().apply(
                    lambda a: fn(a, cv)
                )
            elif cop in ("greater_than", "less_than"):
                nums = pd.to_numeric(series.astype(str).str.replace(",","",regex=False), errors="coerce")
                cond_results[cc] = nums.apply(lambda a: fn(a, cv) if pd.notna(a) else False)
            else:
                cond_results[cc] = pd.Series(False, index=df.index)

        # Combine condition results
        if logic == "AND":
            cond_met = pd.Series(True, index=df.index)
            for cr in cond_results.values():
                cond_met &= cr.fillna(False)
        else:  # OR
            cond_met = pd.Series(False, index=df.index)
            for cr in cond_results.values():
                cond_met |= cr.fillna(True)

        triggered = cond_met[cond_met].index

        cond_summary = (" AND " if logic=="AND" else " OR ").join([
            f"{c.get('column','')}={c.get('value','')}" for c in conditions
        ])

        for idx in triggered:
            for then in thens:
                tt   = then.get("type")
                tc   = _norm(then.get("column",""))

                if tt == "not_null":
                    if tc not in df.columns: continue
                    if _is_empty(df.at[idx, tc]):
                        errors.append(ValidationError(
                            row_id=int(idx)+2, column_name=then.get("column", tc),
                            error_type="CONDITIONAL_NULL", severity=rule.severity,
                            message=rule.message or f"Khi [{cond_summary}] thì '{tc}' không được trống.",
                            rule_id=rule.id,
                        ))

                elif tt == "compare":
                    sub = RuleDef(
                        id=rule.id+"_then", type="compare", scope="row",
                        priority=rule.priority, severity=rule.severity, enabled=True,
                        params={"left":then.get("left",then.get("column","")),
                                "operator":then.get("operator",">="),
                                "right":then.get("right","")},
                        message=rule.message,
                    )
                    row_df = df.iloc[[idx]]
                    errors.extend(self._compare(sub, row_df, tmpl))

                elif tt == "not_equals":
                    if tc not in df.columns: continue
                    v      = df.at[idx, tc]
                    expect = then.get("value")
                    if not _is_empty(v) and _norm(str(v))==_norm(str(expect)):
                        errors.append(ValidationError(
                            row_id=int(idx)+2, column_name=then.get("column", tc),
                            error_type="CONDITIONAL_FAIL", severity=rule.severity,
                            message=rule.message or f"'{tc}'='{v}' không được bằng '{expect}'.",
                            rule_id=rule.id,
                        ))
        return errors

    # ── formula (AST safe eval) — batch ─────────────────────────────────────
    def _formula(self, rule, df, tmpl) -> list[ValidationError]:
        params     = rule.params
        result_col = _norm(params.get("result",""))
        expression = params.get("expression","").strip()
        op_str     = params.get("operator","==")
        tolerance  = float(params.get("tolerance") or 0.01)

        if not result_col or not expression:
            return [ValidationError(0,"","CONFIG_ERROR","critical",
                                    f"Rule '{rule.id}': formula cần 'result' và 'expression'.", rule.id)]
        if result_col not in df.columns:
            return [ValidationError(0,result_col,"MISSING_COLUMN","critical",
                                    f"Rule '{rule.id}': cột '{result_col}' không tồn tại.", rule.id)]

        try:
            tree = _ast.parse(expression, mode='eval')
        except SyntaxError as e:
            return [ValidationError(0,"","CONFIG_ERROR","critical",
                                    f"Rule '{rule.id}': expression sai cú pháp — {e}", rule.id)]

        expr_cols = {_norm(n.id) for n in _ast.walk(tree) if isinstance(n, _ast.Name)}
        missing   = [c for c in expr_cols if c not in df.columns]
        if missing:
            return [ValidationError(0,", ".join(missing),"MISSING_COLUMN","critical",
                                    f"Rule '{rule.id}': cột '{', '.join(missing)}' không tồn tại.", rule.id)]

        SAFE_OPS = {
            _ast.Add: _op.add, _ast.Sub: _op.sub, _ast.Mult: _op.mul,
            _ast.Div: _op.truediv, _ast.Mod: _op.mod, _ast.Pow: _op.pow,
            _ast.USub: _op.neg, _ast.UAdd: _op.pos,
        }

        def _eval(node, ctx):
            if isinstance(node, _ast.Constant): return float(node.value)
            if isinstance(node, _ast.Num):       return float(node.n)
            if isinstance(node, _ast.Name):
                k = _norm(node.id)
                if k not in ctx: raise ValueError(f"Cột '{node.id}' không tồn tại")
                v = ctx[k]
                if v is None or (isinstance(v,float) and pd.isna(v)): return None
                return float(str(v).replace(",","").strip())
            if isinstance(node, _ast.BinOp):
                fn = SAFE_OPS.get(type(node.op))
                if not fn: raise ValueError(f"Operator không hỗ trợ")
                l,r = _eval(node.left,ctx), _eval(node.right,ctx)
                if l is None or r is None: return None
                if isinstance(node.op, _ast.Div) and r==0: raise ValueError("Chia cho 0")
                return fn(l,r)
            if isinstance(node, _ast.UnaryOp):
                fn = SAFE_OPS.get(type(node.op))
                v  = _eval(node.operand, ctx)
                return fn(v) if (fn and v is not None) else None
            raise ValueError(f"Node '{type(node).__name__}' không được phép")

        cmp_ops = _make_ops()
        cmp_fn  = cmp_ops.get(op_str)
        if not cmp_fn:
            return [ValidationError(0,"","CONFIG_ERROR","critical",
                                    f"Rule '{rule.id}': operator '{op_str}' không hợp lệ.", rule.id)]

        # Pre-parse result column numbers
        rv_nums = pd.to_numeric(
            df[result_col].astype(str).str.replace(",","",regex=False),
            errors="coerce"
        )
        errors = []

        for idx in df.index:
            rv = rv_nums.at[idx]
            if pd.isna(rv): continue
            ctx = {col: df.at[idx, col] for col in df.columns}
            try:
                expected = _eval(tree.body, ctx)
            except (ValueError, ZeroDivisionError) as e:
                errors.append(ValidationError(int(idx)+2, result_col, "FORMULA_ERROR",
                    rule.severity, f"Lỗi tính expression: {e}", rule.id)); continue
            if expected is None: continue

            if op_str in ("==","!="):
                passed = (abs(rv-expected)<=tolerance) if op_str=="==" else (abs(rv-expected)>tolerance)
            else:
                passed = cmp_fn(rv, expected)

            if not passed:
                errors.append(ValidationError(
                    row_id=int(idx)+2, column_name=result_col,
                    error_type="FORMULA_FAIL", severity=rule.severity,
                    message=rule.message or (
                        f"'{result_col}'={rv:.4g} phải {op_str} {expression}={expected:.4g} "
                        f"(sai lệch={abs(rv-expected):.4g})."
                    ),
                    rule_id=rule.id,
                ))
        return errors

    # ── sum_check (backward compat → formula) ─────────────────────────────────
    def _sum_check(self, rule, df, tmpl) -> list[ValidationError]:
        import copy
        p = rule.params
        adds = [c for c in p.get("operands",[]) if c]
        subs = [c for c in p.get("subtract",[]) if c]
        if not p.get("result") or not adds:
            return [ValidationError(0,"","CONFIG_ERROR","critical",
                                    f"Rule '{rule.id}': sum_check cần 'result' và 'operands'.", rule.id)]
        expr = " + ".join(adds) + (" - " + " - ".join(subs) if subs else "")
        nr   = copy.copy(rule)
        nr.params = {"result": p["result"], "expression": expr,
                     "operator": "==", "tolerance": p.get("tolerance", 0.01)}
        return self._formula(nr, df, tmpl)


# ── Table Engine ──────────────────────────────────────────────────────────────

class TableEngine:
    """scope=table: nhìn toàn bộ dataset."""

    def run(self, rule: RuleDef, df: pd.DataFrame, tmpl: TemplateDef,
            bad_rows: set) -> list[ValidationError]:
        handler = {"unique": self._unique}.get(rule.type)
        return handler(rule, df, tmpl) if handler else []

    def _unique(self, rule, df, tmpl) -> list[ValidationError]:
        col_keys = [_norm(c) for c in (rule.columns or []) if c]
        if not col_keys and rule.column:
            col_keys = [_norm(rule.column)]
        if not col_keys:
            return [ValidationError(0,"","CONFIG_ERROR","critical",
                                    f"Rule '{rule.id}': unique cần column.", rule.id)]

        missing = [c for c in col_keys if c not in df.columns]
        if missing:
            return [ValidationError(0,", ".join(missing),"MISSING_COLUMN","critical",
                                    f"Rule '{rule.id}': cột '{', '.join(missing)}' không tồn tại.", rule.id)]
        errors = []

        if len(col_keys) == 1:
            col   = col_keys[0]
            notnull = df[col].notna() & (df[col].astype(str).str.strip() != "")
            dupes = df[notnull & df[col].duplicated(keep=False)].index
            for idx in dupes:
                errors.append(ValidationError(
                    int(idx)+2, col_keys[0], "DUPLICATE_KEY", rule.severity,
                    rule.message or f"Giá trị '{df.at[idx,col]}' bị trùng trong cột '{col_keys[0]}'.",
                    rule.id,
                ))
        else:
            subset = df[col_keys].copy()
            subset = subset[~subset.isna().all(axis=1)]
            dupes  = subset.duplicated(keep=False)
            for idx in subset[dupes].index:
                vals = {c: df.at[idx,c] for c in col_keys}
                errors.append(ValidationError(
                    int(idx)+2, ", ".join(col_keys), "DUPLICATE_KEY", rule.severity,
                    rule.message or f"Khoá tổng hợp {vals} bị trùng.", rule.id,
                ))
        return errors


# ── Engine registry ───────────────────────────────────────────────────────────

ENGINES = {
    "column":  ColumnEngine(),
    "row":     RowEngine(),
    "table":   TableEngine(),
}


# ── Main Validator ───────────────────────────────────────────────────────────

class Validator:
    def __init__(self, template_name: str):
        self.template_name = template_name
        self.tmpl          = load_config(template_name)
        self.errors: list[ValidationError] = []
        self._used_sheet: str = ""

    def validate(self, file_path: str | Path) -> dict:
        df = self._smart_read_excel(file_path)
        df.columns = [_norm(c) for c in df.columns]
        self.errors = []

        # Cache for notnull masks — shared across all column checks
        col_cache: dict = {}

        # Step 1: Column system checks
        bad_dtype_rows: dict[str, set] = {}
        self._check_columns(df, bad_dtype_rows, col_cache)

        # Global bad rows (any col had WRONG_DATATYPE)
        all_bad_rows: set = set()
        for s in bad_dtype_rows.values():
            all_bad_rows |= s

        # Step 2: Run rules
        for rule in sorted(self.tmpl.rules, key=lambda r: r.priority):
            if not rule.enabled: continue
            engine = ENGINES.get(rule.scope)
            if not engine: continue

            col_key = _norm(rule.column) if rule.column else ""
            if rule.scope == "column":
                bad = bad_dtype_rows.get(col_key, set())
                errs = engine.run(rule, df, self.tmpl, bad, col_cache)  # cache shared across column rules
            elif rule.scope == "table":
                errs = engine.run(rule, df, self.tmpl, all_bad_rows)
            else:
                errs = engine.run(rule, df, self.tmpl)

            self.errors.extend(errs)

        return self._build_summary(df)

    # ── Column system checks — vectorized ─────────────────────────────────────

    def _check_columns(self, df: pd.DataFrame, bad_dtype_rows: dict, cache: dict):
        for col_def in self.tmpl.columns:
            col_key = _norm(col_def.name)

            if col_key not in df.columns:
                self.errors.append(ValidationError(
                    0, col_def.name, "MISSING_COLUMN", "critical",
                    f"Cột '{col_def.name}' không tồn tại trong file.",
                    "sys_missing_col",
                ))
                continue

            series   = df[col_key]
            notnull  = series.notna() & (series.astype(str).str.strip() != "")
            null_mask= ~notnull

            # Null required — vectorized
            if col_def.is_required:
                for idx in series[null_mask].index:
                    self.errors.append(ValidationError(
                        int(idx)+2, col_def.name, "NULL_REQUIRED", "critical",
                        f"Cột '{col_def.name}' bắt buộc nhưng đang trống.",
                        "sys_null_required",
                    ))

            # Null percent
            total = len(df)
            nulls = int(null_mask.sum())
            pct   = round(nulls/total*100, 1) if total > 0 else 0
            if pct > col_def.allow_null_percent:
                self.errors.append(ValidationError(
                    0, col_def.name, "NULL_EXCEEDED", "warning",
                    f"Cột '{col_def.name}' có {pct}% null (cho phép {col_def.allow_null_percent}%).",
                    "sys_null_pct",
                ))

            # Datatype
            bad_idx = self._check_datatype_vectorized(series, col_def, notnull, cache)
            bad_dtype_rows[col_key] = set(bad_idx)

    def _check_datatype_vectorized(self, series: pd.Series, col_def: ColumnDef,
                                    notnull: pd.Series, cache: dict) -> list:
        if col_def.data_type == "text":
            return []

        s       = series[notnull].astype(str).str.strip()
        bad_idx = []

        if col_def.data_type == "number":
            nums    = pd.to_numeric(s.str.replace(",","",regex=False), errors="coerce")
            bad_idx = list(nums[nums.isna()].index)
            for idx in bad_idx:
                self.errors.append(ValidationError(
                    int(idx)+2, col_def.name, "WRONG_DATATYPE", "critical",
                    f"'{series.at[idx]}' không phải số hợp lệ trong cột '{col_def.name}'.",
                    "sys_datatype",
                ))

        elif col_def.data_type == "date":
            strftime_fmt = col_def.strftime_format
            if strftime_fmt:
                # Try vectorized parse
                parsed = pd.to_datetime(s, format=strftime_fmt, errors="coerce")
                bad_mask = parsed.isna() & s.str.len() > 0
                for idx in s[bad_mask].index:
                    val = series.at[idx]
                    if not isinstance(val, (datetime, date_type)):
                        bad_idx.append(idx)
                        self.errors.append(ValidationError(
                            int(idx)+2, col_def.name, "WRONG_DATATYPE", "critical",
                            f"'{val}' không phải ngày hợp lệ"
                            + (f" (cần '{col_def.date_format}')" if col_def.date_format else "")
                            + f" trong cột '{col_def.name}'.",
                            "sys_datatype",
                        ))
            else:
                # Try common ISO formats — vectorized
                for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y"):
                    parsed = pd.to_datetime(s, format=fmt, errors="coerce")
                    if parsed.notna().sum() > 0:
                        break
                bad_mask = parsed.isna() & s.str.len() > 0
                for idx in s[bad_mask].index:
                    val = series.at[idx]
                    if not isinstance(val, (datetime, date_type)):
                        bad_idx.append(idx)
                        self.errors.append(ValidationError(
                            int(idx)+2, col_def.name, "WRONG_DATATYPE", "critical",
                            f"'{val}' không phải ngày hợp lệ trong cột '{col_def.name}'.",
                            "sys_datatype",
                        ))
        return bad_idx

    @staticmethod
    def _try_parse(s: str, fmt: str) -> bool:
        try: datetime.strptime(s, fmt); return True
        except ValueError: return False

    # ── Smart read Excel — single read ───────────────────────────────────────

    def _get_sheet_name(self, sheet_names: list[str]) -> str | int:
        tk = _norm(self.template_name).replace("_","").replace(" ","")
        for s in sheet_names:
            if tk == _norm(s).replace("_","").replace(" ",""): return s
        for s in sheet_names:
            sk = _norm(s).replace("_","").replace(" ","")
            if tk in sk or sk in tk: return s
        return 0

    def _smart_read_excel(self, file_path) -> pd.DataFrame:
        import openpyxl
        config_cols = {_norm(c.name) for c in self.tmpl.columns}

        wb          = openpyxl.load_workbook(file_path, read_only=True)
        sheet_names = wb.sheetnames
        wb.close()

        sheet = self._get_sheet_name(sheet_names)
        self._used_sheet = sheet_names[sheet] if isinstance(sheet, int) else sheet
        print(f"  [Validator] Template='{self.template_name}' → Sheet='{self._used_sheet}'")

        df0     = pd.read_excel(file_path, dtype=str, header=0, sheet_name=sheet)
        match0  = len({_norm(c) for c in df0.columns} & config_cols)

        first_row_vals = df0.columns.tolist()
        looks_like_data = any(
            _norm(str(v)) in config_cols for v in first_row_vals
        )

        if looks_like_data and match0 < len(config_cols) * 0.5:
            try:
                df1    = pd.read_excel(file_path, dtype=str, header=1, sheet_name=sheet)
                match1 = len({_norm(c) for c in df1.columns} & config_cols)
                if match1 > match0:
                    print(f"  [Validator] h0={match0} h1={match1} → using h1")
                    return df1
            except Exception:
                pass

        print(f"  [Validator] h0={match0} → using h0")
        return df0

    # ── Summary ───────────────────────────────────────────────────────────────

    def _build_summary(self, df: pd.DataFrame) -> dict:
        total_rows = len(df)
        error_rows = len({e.row_id for e in self.errors if e.row_id > 0})
        critical   = [e for e in self.errors if e.severity=="critical"]
        warnings   = [e for e in self.errors if e.severity=="warning"]
        error_pct  = round(error_rows/total_rows*100, 1) if total_rows > 0 else 0
        status     = "fail" if critical else ("warning" if warnings else "pass")
        return {
            "template":     self.template_name,
            "sheet_name":   self._used_sheet,
            "total_rows":   total_rows,
            "error_rows":   error_rows,
            "error_pct":    error_pct,
            "total_errors": len(self.errors),
            "critical":     len(critical),
            "warnings":     len(warnings),
            "status":       status,
            "errors":       [vars(e) for e in self.errors],
        }
