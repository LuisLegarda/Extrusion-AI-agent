"""Variables calculadas con fórmulas seguras (sin eval de Python).

Sintaxis: los IDs de variables se usan por nombre (``vel / rpm``) o entre llaves
(``{zona_1} - {zona_1_sp}``). Operadores + - * / // % ** , comparaciones, and/or/not,
``a if cond else b`` y las funciones de FUNCTIONS.
"""
from __future__ import annotations

import ast
import math
import re
from dataclasses import dataclass
from typing import Callable, Optional


def _avg(*xs):
    return sum(xs) / len(xs) if xs else math.nan


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def _si(cond, a, b):
    return a if cond else b


FUNCTIONS: dict[str, Callable] = {
    "abs": abs, "min": min, "max": max, "round": round, "sqrt": math.sqrt, "log": math.log,
    "log10": math.log10, "exp": math.exp, "pow": pow, "avg": _avg, "promedio": _avg, "clamp": _clamp,
    "si": _si, "if_": _si, "pi": math.pi,
}
_BINOPS = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b,
           ast.Div: lambda a, b: a / b, ast.FloorDiv: lambda a, b: a // b, ast.Mod: lambda a, b: a % b,
           ast.Pow: lambda a, b: a ** b}
_CMPS = {ast.Lt: lambda a, b: a < b, ast.LtE: lambda a, b: a <= b, ast.Gt: lambda a, b: a > b,
         ast.GtE: lambda a, b: a >= b, ast.Eq: lambda a, b: a == b, ast.NotEq: lambda a, b: a != b}


class FormulaError(ValueError):
    pass


@dataclass
class Formula:
    source: str
    tree: ast.Expression
    deps: list[str]
    names: dict[str, str]  # nombre en el árbol -> id de variable

    def evaluate(self, values: dict[str, float]) -> Optional[float]:
        try:
            v = _eval(self.tree.body, values, self.names)
        except (ZeroDivisionError, ValueError, OverflowError, TypeError):
            return None
        if isinstance(v, bool):
            v = float(v)
        if not isinstance(v, (int, float)) or math.isnan(v) or math.isinf(v):
            return None
        return float(v)


def compile_formula(source: str, known: set[str]) -> Formula:
    names: dict[str, str] = {}

    def brace(m: re.Match) -> str:
        vid = m.group(1).strip()
        alias = f"_v{len(names)}"
        names[alias] = vid
        return alias

    text = re.sub(r"\{([^{}]+)\}", brace, source.strip())
    if not text:
        raise FormulaError("La fórmula está vacía")
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise FormulaError(f"Sintaxis inválida: {exc.msg}") from exc
    deps: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            vid = names.get(node.id, node.id)
            if node.id in FUNCTIONS:
                continue
            if vid not in known:
                raise FormulaError(f"Variable desconocida: «{vid}»")
            names.setdefault(node.id, vid)
            if vid not in deps:
                deps.append(vid)
        elif isinstance(node, ast.Call):
            if not (isinstance(node.func, ast.Name) and node.func.id in FUNCTIONS):
                raise FormulaError("Solo se permiten las funciones: " + ", ".join(sorted(FUNCTIONS)))
        elif not isinstance(node, (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Compare, ast.BoolOp, ast.IfExp,
                                   ast.Constant, ast.Load, ast.operator, ast.unaryop, ast.cmpop, ast.boolop)):
            raise FormulaError(f"Elemento no permitido en la fórmula: {type(node).__name__}")
    return Formula(source, tree, deps, names)


def _eval(node, values, names):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise FormulaError("Solo se permiten números")
    if isinstance(node, ast.Name):
        if node.id in FUNCTIONS and not callable(FUNCTIONS[node.id]):
            return FUNCTIONS[node.id]
        return values[names.get(node.id, node.id)]
    if isinstance(node, ast.BinOp):
        return _BINOPS[type(node.op)](_eval(node.left, values, names), _eval(node.right, values, names))
    if isinstance(node, ast.UnaryOp):
        v = _eval(node.operand, values, names)
        if isinstance(node.op, ast.USub):
            return -v
        if isinstance(node.op, ast.Not):
            return not v
        return +v
    if isinstance(node, ast.Compare):
        left = _eval(node.left, values, names)
        for op, comp in zip(node.ops, node.comparators):
            right = _eval(comp, values, names)
            if not _CMPS[type(op)](left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.BoolOp):
        vals = [_eval(v, values, names) for v in node.values]
        return all(vals) if isinstance(node.op, ast.And) else any(vals)
    if isinstance(node, ast.IfExp):
        return _eval(node.body if _eval(node.test, values, names) else node.orelse, values, names)
    if isinstance(node, ast.Call):
        if node.func.id in ("si", "if_") and len(node.args) == 3:
            # Evaluación perezosa: la rama no elegida no se calcula (evita p. ej. divisiones entre 0).
            cond, a, b = node.args
            return _eval(a if _eval(cond, values, names) else b, values, names)
        return FUNCTIONS[node.func.id](*[_eval(a, values, names) for a in node.args])
    raise FormulaError(type(node).__name__)


def evaluation_order(formulas: dict[str, Formula]) -> list[str]:
    """Orden topológico (una fórmula puede usar otras); error si hay ciclos."""
    order: list[str] = []
    state: dict[str, int] = {}

    def visit(vid: str, path: list[str]) -> None:
        if state.get(vid) == 2:
            return
        if state.get(vid) == 1:
            raise FormulaError("Referencia circular: " + " → ".join(path + [vid]))
        state[vid] = 1
        for d in formulas[vid].deps:
            if d in formulas:
                visit(d, path + [vid])
        state[vid] = 2
        order.append(vid)

    for vid in formulas:
        visit(vid, [])
    return order
