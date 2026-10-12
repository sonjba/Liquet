"""How this bank's descriptions map to Liquet's entry types.

Checked in order; the first description start that fits wins.
A description that fits none gets no type (None). Liquet never guesses.
Another bank → a new table, not new code.
"""

# Liquet's name : the header's name in the bank's file
HEADER_FIELDS = {
    "account_id" : "account_id",
    "custodian" : "custodian",
    "currency" : "currency",
    "period_start" : "period_start",
    "period_end" : "period_end",
    "opening_balance" : "opening_balance",
    "closing_balance" : "closing_balance"
}


# Liquet's name : the column's name in the bank's file
COLUMNS = {
    "date": "date",
    "description": "description",
    "reference": "reference",
    "paid_in": "paid_in",
    "paid_out": "paid_out",
    "balance": "balance",
}

BANK_DESCRIPTION_TYPES = [
    ("SUBSCRIPTION",     "SUBSCRIPTION"),
    ("WITHDRAWAL",       "WITHDRAWAL"),
    ("SETTLEMENT",       "TRADE_SETTLEMENT"),
    ("DIVIDEND",         "DIVIDEND"),
    ("TRANSFER KRW FEE", "MANAGEMENT_FEE"),
    ("CUSTODY FEE",      "CUSTODY_FEE"),
    ("CREDIT INTEREST",  "INTEREST"),
]