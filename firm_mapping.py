# firm_mapping.py - how the firm's names map to Liquet's canonical names.
# Liquet's name : the firm's name. Fields the connector adds itself
# (source, and ids taken from a parent record) are not listed here.

FIRM_MAPPING = {
    "accounts": {                      # each item in accounts.json
        "account_id": "account_id",
        "account_name": "name",
        "custodian": "custodian",
        "currency": "currency",
    },
    "account_balances": {              # each entry in an account's cash_balances
        "as_of": "as_of",
        "balance": "balance",
    },
    "portfolios": {                    # each item in portfolios.json
        "portfolio_id": "portfolio_id",
        "account_id": "custody_account",
    },
    "clients": {                       # the client object inside each portfolio
        "client_id": "client_id",
        "name": "full_name",
        "client_type": "type",
    },
    "cash_book": {                        # each item in cash_book.json
        "entry_id": "movement_id",
        "date": "value_date",
        "recorded_at": "entered_on",
        "entry_type": "kind",
        "description": "narrative",
        "reference": "our_ref",
        # fields added in code,because they are not present in the firm's data:

        # "account_id": "account_id",  --> the portfolio’s custody_account, or the account’s own id for account movements
        # "portfolio_id": "portfolio_id", --> the parent portfolio, or None for account movements
        # "trade_id": "trade_id", --> trade.trade_ref if the movement has a trade, otherwise None
        # "ticker": "ticker", --> dividend.security.ticker if it has a dividend, otherwise None
        # "debit": "debit", --> direction and AMOUNT: IN goes to debit, OUT goes to credit, and the other is None. Anything other than IN or OUT is a ValueError.
        # "credit": "credit", --> direction and AMOUNT: IN goes to debit, OUT goes to credit, and the other is None. Anything other than IN or OUT is a ValueError.
        # "source": "source" -->  portfolios/PF-CL-003/cash_movements/4 or accounts/ACC-KRW-CASH-01/account_movements/0
    },
}