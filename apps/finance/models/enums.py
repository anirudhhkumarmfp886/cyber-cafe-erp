"""Shared financial enums for the finance app."""
from django.db import models


class PaymentMode(models.TextChoices):
    CASH = "CASH", "Cash"
    UPI = "UPI", "UPI"
    CARD = "CARD", "Card"
    BANK_TRANSFER = "BANK_TRANSFER", "Bank Transfer"


class CashEntryType(models.TextChoices):
    INCOME = "INCOME", "Income"
    EXPENSE = "EXPENSE", "Expense"


class CashEntryCategory(models.TextChoices):
    # Income categories
    SALES = "SALES", "Sales"
    SERVICE_FEE = "SERVICE_FEE", "Service Fee"
    OTHER_INCOME = "OTHER_INCOME", "Other Income"
    # Expense categories
    PURCHASE = "PURCHASE", "Purchases"
    RENT = "RENT", "Rent"
    ELECTRICITY = "ELECTRICITY", "Electricity"
    INTERNET = "INTERNET", "Internet / ISP"
    SALARY = "SALARY", "Salary"
    MAINTENANCE = "MAINTENANCE", "Maintenance"
    UTILITIES = "UTILITIES", "Utilities"
    TAX = "TAX", "Tax"
    MISC = "MISC", "Miscellaneous"


INCOME_CATEGORIES = {
    CashEntryCategory.SALES,
    CashEntryCategory.SERVICE_FEE,
    CashEntryCategory.OTHER_INCOME,
}

EXPENSE_CATEGORIES = {
    CashEntryCategory.PURCHASE,
    CashEntryCategory.RENT,
    CashEntryCategory.ELECTRICITY,
    CashEntryCategory.INTERNET,
    CashEntryCategory.SALARY,
    CashEntryCategory.MAINTENANCE,
    CashEntryCategory.UTILITIES,
    CashEntryCategory.TAX,
    CashEntryCategory.MISC,
}


class BankAccountType(models.TextChoices):
    CURRENT = "CURRENT", "Current Account"
    SAVINGS = "SAVINGS", "Savings Account"
    CASH_CREDIT = "CASH_CREDIT", "Cash Credit / Overdraft"


class BankTransactionType(models.TextChoices):
    CREDIT = "CREDIT", "Deposit / Credit"
    DEBIT = "DEBIT", "Withdrawal / Debit"


class BankTransactionCategory(models.TextChoices):
    DEPOSIT = "DEPOSIT", "Cash / Cheque Deposit"
    WITHDRAWAL = "WITHDRAWAL", "Cash Withdrawal"
    TRANSFER_IN = "TRANSFER_IN", "Transfer In"
    TRANSFER_OUT = "TRANSFER_OUT", "Transfer Out"
    PAYMENT_RECEIVED = "PAYMENT_RECEIVED", "Payment Received"
    EXPENSE_PAYMENT = "EXPENSE_PAYMENT", "Expense Payment"
    SALARY = "SALARY", "Salary Payment"
    INTEREST = "INTEREST", "Interest Earned"
    CHARGES = "CHARGES", "Bank Charges"
    MISC = "MISC", "Miscellaneous"
