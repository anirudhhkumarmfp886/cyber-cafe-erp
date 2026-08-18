"""
Restricted formula engine for service pricing.

The owner describes how a bill line is priced as plain-text math::

    pages * rate
    fillup_charge + paid_to_site
    piece * rate_per_piece
    cash * (1 + pct / 100)

A formula is evaluated against a whitelist of variables (the line's
custom-field values plus ``qty`` and ``price``). It can NEVER touch Python
imports, Django models, the database, the filesystem or the network: the
grammar below simply has no way to express those. This is the replacement
for hard-coded per-service pricing rules (cash withdrawal, money transfer,
form fill-up, ...) — one calculation path for every service.

Supported: Decimal numbers, identifiers, ``+ - * /``, parentheses and
unary minus. Anything else raises :class:`FormulaError`.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.db import models

_MONEY = Decimal("0.01")

_TOKEN_EOF = "EOF"
_TOKEN_NUMBER = "NUMBER"
_TOKEN_NAME = "NAME"
_TOKEN_OP = "OP"
_TOKEN_LPAREN = "LPAREN"
_TOKEN_RPAREN = "RPAREN"

_OPS = "+-*/"


class FormulaError(ValueError):
    """Raised for any invalid / unsafe formula or evaluation problem."""


def slugify_variable(label: str) -> str:
    """Turn a human label into a safe machine variable name.

    ``"Rate / Page"`` -> ``rate_page``. Leading digits are prefixed so the
    result is always a valid identifier.
    """
    parts = []
    for ch in str(label or "").strip().lower():
        if ch.isalnum() or ch == "_":
            parts.append(ch)
        else:
            parts.append("_")
    name = "".join(parts).strip("_")
    if not name:
        name = "field"
    if name[0].isdigit():
        name = f"f_{name}"
    return name


def _tokenize(expr: str):
    tokens = []
    i, n = 0, len(expr)
    while i < n:
        ch = expr[i]
        if ch.isspace():
            i += 1
            continue
        if ch.isdigit() or ch == ".":
            j = i
            while j < n and (expr[j].isdigit() or expr[j] == "."):
                j += 1
            raw = expr[i:j]
            if raw.count(".") > 1:
                raise FormulaError(f"Invalid number '{raw}'.")
            try:
                value = Decimal(raw)
            except InvalidOperation as exc:
                raise FormulaError(f"Invalid number '{raw}'.") from exc
            tokens.append((_TOKEN_NUMBER, value))
            i = j
            continue
        if ch.isalpha() or ch == "_":
            j = i
            while j < n and (expr[j].isalnum() or expr[j] == "_"):
                j += 1
            tokens.append((_TOKEN_NAME, expr[i:j]))
            i = j
            continue
        if ch in _OPS:
            tokens.append((_TOKEN_OP, ch))
            i += 1
            continue
        if ch == "(":
            tokens.append((_TOKEN_LPAREN, ch))
            i += 1
            continue
        if ch == ")":
            tokens.append((_TOKEN_RPAREN, ch))
            i += 1
            continue
        raise FormulaError(f"Unsupported character '{ch}' in formula.")
    tokens.append((_TOKEN_EOF, None))
    return tokens


class _Parser:
    def __init__(self, expr: str):
        self._tokens = _tokenize(expr)
        self._pos = 0

    def _peek(self):
        return self._tokens[self._pos]

    def _next(self):
        token = self._tokens[self._pos]
        self._pos += 1
        return token

    def _expect(self, kind):
        token = self._next()
        if token[0] != kind:
            raise FormulaError("Unexpected end of formula." if token[0] == _TOKEN_EOF else "Invalid formula syntax.")
        return token

    def parse(self):
        node = self._expr()
        if self._peek()[0] != _TOKEN_EOF:
            raise FormulaError("Invalid formula syntax.")
        return node

    def _expr(self):
        node = self._term()
        while self._peek()[0] == _TOKEN_OP and self._peek()[1] in "+-":
            op = self._next()[1]
            right = self._term()
            node = ("bin", op, node, right)
        return node

    def _term(self):
        node = self._factor()
        while self._peek()[0] == _TOKEN_OP and self._peek()[1] in "*/":
            op = self._next()[1]
            right = self._factor()
            node = ("bin", op, node, right)
        return node

    def _factor(self):
        token = self._next()
        kind, value = token
        if kind == _TOKEN_OP and value == "-":
            return ("neg", self._factor())
        if kind == _TOKEN_NUMBER:
            return ("num", value)
        if kind == _TOKEN_NAME:
            return ("var", value)
        if kind == _TOKEN_LPAREN:
            node = self._expr()
            self._expect(_TOKEN_RPAREN)
            return node
        raise FormulaError("Invalid formula syntax.")


def _evaluate(node, names: dict) -> Decimal:
    kind = node[0]
    if kind == "num":
        return node[1]
    if kind == "var":
        name = node[1]
        if name not in names:
            raise FormulaError(f"Formula uses an unknown variable '{name}'.")
        return names[name]
    if kind == "neg":
        return -_evaluate(node[1], names)
    # bin
    _, op, left, right = node
    a = _evaluate(left, names)
    b = _evaluate(right, names)
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op == "*":
        return a * b
    if op == "/":
        if b == 0:
            raise FormulaError("Formula divides by zero.")
        return a / b
    raise FormulaError("Invalid formula operator.")


def names_in(formula: str) -> set[str]:
    """The set of variable names a formula references (for config validation)."""
    if not formula or not str(formula).strip():
        return set()
    parser = _Parser(str(formula))
    node = parser.parse()

    found: set[str] = set()

    def walk(n):
        if n[0] == "var":
            found.add(n[1])
        elif n[0] == "neg":
            walk(n[1])
        elif n[0] == "bin":
            walk(n[2])
            walk(n[3])

    walk(node)
    return found


def evaluate(formula: str, names: dict, *, round_to: Decimal = _MONEY) -> Decimal:
    """Evaluate ``formula`` against ``names`` and return a rounded Decimal.

    ``names`` must be a ``{variable: Decimal|int|float}`` mapping. Every
    referenced variable must be present; unknown names raise FormulaError.
    """
    expr = str(formula or "").strip()
    if not expr:
        raise FormulaError("Formula is empty.")
    parser = _Parser(expr)
    node = parser.parse()
    result = _evaluate(node, {key: Decimal(str(value)) for key, value in names.items()})
    return Decimal(result).quantize(round_to, rounding=ROUND_HALF_UP)


def validate(formula: str) -> None:
    """Parse a formula to catch syntax errors (no evaluation)."""
    if formula and str(formula).strip():
        _Parser(str(formula)).parse()


def validate_for_names(formula: str, allowed: set[str]) -> list[str]:
    """Return the referenced variable names that are not in ``allowed``."""
    return sorted(names_in(formula) - allowed)


class ServicePassThroughType(models.TextChoices):
    """How a service's pass-through money leaves the shop.

    ``NONE``   — plain sale; the whole line amount is shop income.
    ``CASH``   — pass-through is handed to the customer as cash (withdrawal /
                 E-Sathi): staff CASH wallet debit + cash-out expense.
    ``ONLINE`` — pass-through is transferred out (money transfer, form fill-up
                 paid to a site): staff ONLINE wallet debit.
    """

    NONE = "NONE", "None (plain sale)"
    CASH = "CASH", "Cash given to customer (withdrawal / E-Sathi)"
    ONLINE = "ONLINE", "Online transfer on behalf of customer"
