"""Unit tests for the restricted formula engine (apps.common.services.formula)."""
from decimal import Decimal

from django.test import SimpleTestCase

from apps.common.services.formula import (
    FormulaError,
    ServicePassThroughType,
    evaluate,
    names_in,
    slugify_variable,
    validate,
    validate_for_names,
)


class FormulaEvaluateTests(SimpleTestCase):
    def test_plain_number(self):
        self.assertEqual(evaluate("10", {}), Decimal("10.00"))

    def test_basic_arithmetic_precedence(self):
        self.assertEqual(evaluate("2 + 3 * 4", {}), Decimal("14.00"))

    def test_parentheses_override_precedence(self):
        self.assertEqual(evaluate("(2 + 3) * 4", {}), Decimal("20.00"))

    def test_division_and_rounding(self):
        self.assertEqual(evaluate("100 / 3", {}), Decimal("33.33"))

    def test_unary_minus(self):
        self.assertEqual(evaluate("-5 + 10", {}), Decimal("5.00"))

    def test_variables_resolved(self):
        self.assertEqual(evaluate("cash * (1 + pct / 100)", {"cash": Decimal("5000"), "pct": Decimal("2")}), Decimal("5100.00"))

    def test_half_up_rounding(self):
        self.assertEqual(evaluate("0.005 + 0", {}), Decimal("0.01"))

    def test_unknown_variable_rejected(self):
        with self.assertRaisesMessage(FormulaError, "unknown variable 'cash'"):
            evaluate("cash + 1", {})

    def test_divide_by_zero_rejected(self):
        with self.assertRaisesMessage(FormulaError, "divides by zero"):
            evaluate("5 / 0", {})

    def test_empty_formula_rejected(self):
        with self.assertRaisesMessage(FormulaError, "Formula is empty."):
            evaluate("", {})

    def test_unsupported_character_rejected(self):
        with self.assertRaisesMessage(FormulaError, "Unsupported character '=' in formula."):
            evaluate("a = b", {})

    def test_invalid_syntax_rejected(self):
        with self.assertRaises(FormulaError):
            evaluate("2 +", {})

    def test_float_and_int_names(self):
        self.assertEqual(evaluate("x * y", {"x": 2, "y": 1.5}), Decimal("3.00"))


class FormulaNamesTests(SimpleTestCase):
    def test_names_in_collects_variables(self):
        self.assertEqual(names_in("cash * (1 + pct / 100)"), {"cash", "pct"})

    def test_names_in_empty(self):
        self.assertEqual(names_in(""), set())

    def test_validate_accepts_valid_formula(self):
        self.assertIsNone(validate("a + b"))

    def test_validate_rejects_invalid_formula(self):
        with self.assertRaises(FormulaError):
            validate("a +")

    def test_validate_for_names_reports_missing(self):
        self.assertEqual(validate_for_names("a + b", {"a"}), ["b"])

    def test_validate_for_names_all_known(self):
        self.assertEqual(validate_for_names("a + b", {"a", "b"}), [])


class FormulaSlugTests(SimpleTestCase):
    def test_slug_lowercases_and_replaces_spaces(self):
        self.assertEqual(slugify_variable("Rate / Page"), "rate___page")

    def test_slug_collapses_simple_space(self):
        self.assertEqual(slugify_variable("Cash Amount"), "cash_amount")

    def test_slug_strips_leading_digits(self):
        self.assertEqual(slugify_variable("2 Step"), "f_2_step")

    def test_slug_empty_label_falls_back(self):
        self.assertEqual(slugify_variable(""), "field")

    def test_slug_keeps_underscores(self):
        self.assertEqual(slugify_variable("cash_amount"), "cash_amount")


class ServicePassThroughTypeTests(SimpleTestCase):
    def test_choices_exist(self):
        self.assertEqual(ServicePassThroughType.CASH.value, "CASH")
        self.assertEqual(ServicePassThroughType.ONLINE.value, "ONLINE")
        self.assertEqual(ServicePassThroughType.NONE.value, "NONE")
