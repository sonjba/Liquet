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
}