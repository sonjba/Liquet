"""How this bank writes its statement, in Liquet's names.

Part of the door (with bank_reader.py): change this file, not the rest of
Liquet, when a bank names its fields or words its descriptions differently.
"""

# Liquet's name : the header's name in the bank's file
HEADER_FIELDS = {
    "account_id": "account_id",
    "custodian": "custodian",
    "currency": "currency",
    "period_start": "period_start",
    "period_end": "period_end",
    "opening_balance": "opening_balance",
    "closing_balance": "closing_balance",
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

# How the description starts : Liquet's entry type. Checked in this order,
# first match wins; a description that fits none gets entry_type None.
BANK_DESCRIPTION_TYPES = [
    ("SUBSCRIPTION", "SUBSCRIPTION"),
    ("WITHDRAWAL", "WITHDRAWAL"),
    ("SETTLEMENT", "TRADE_SETTLEMENT"),
    ("DIVIDEND", "DIVIDEND"),
    ("TRANSFER KRW FEE", "MANAGEMENT_FEE"),
    ("CUSTODY FEE", "CUSTODY_FEE"),
    ("CREDIT INTEREST", "INTEREST"),
]
