"""Where each Liquet field comes from in the firm's data.

One line per field:  Liquet name : path in the firm's data.
path_mapper.py follows the paths (its docstring has the full rules).

How to read a path:
  accounts[*].cash_balances[*].balance
  = in the accounts data, for each account, for each entry in its
    cash_balances list, take `balance`.

Rules:
  [*]     for each item in this list
  ?[*]    the same, but the list may be missing (then it has no items)
  a.b     field b inside the object in field a
  name?   this part may be missing (not there, or null)
  None    instead of a path: the field is always None
Everything without a ? must be there, or the connector stops.

One record is made per item of the deepest list. A field with fewer [*]
is read from the parent item, e.g. a balance's account_id comes from its account.

When a part marked ? is missing:
  - if all of the record's own fields go through it, the item is skipped
    (trades: a movement without trade? is not a trade);
  - otherwise only that field is None
    (cash book: a movement without trade? gets trade_id None).
  What comes after the ? is required: a trade without trade_ref is an error.
"""

FIRM_MAPPING = {
    "accounts": {
        "account_id":   "accounts[*].account_id",
        "account_name": "accounts[*].name",
        "custodian":    "accounts[*].custodian",
        "currency":     "accounts[*].currency",
    },
    "account_balances": {
        "account_id": "accounts[*].account_id",
        "as_of":      "accounts[*].cash_balances[*].as_of",
        "balance":    "accounts[*].cash_balances[*].balance",
    },
    "portfolios": {
        "portfolio_id": "portfolios[*].portfolio_id",
        "account_id":   "portfolios[*].custody_account",
        "client_id":    "portfolios[*].client.client_id",
    },
    "clients": {
        "client_id":   "portfolios[*].client.client_id",
        "name":        "portfolios[*].client.full_name",
        "client_type": "portfolios[*].client.type",
    },
    # A trade sits inside its settlement movement. "trade?" means: only
    # movements that have a trade; the others are skipped.
    "trades": {
        "trade_id":          "portfolios[*].cash_movements[*].trade?.trade_ref",
        "portfolio_id":      "portfolios[*].portfolio_id",
        "account_id":        "portfolios[*].custody_account",
        "ticker":            "portfolios[*].cash_movements[*].trade?.security.ticker",
        "side":              "portfolios[*].cash_movements[*].trade?.side",
        "trade_date":        "portfolios[*].cash_movements[*].trade?.trade_date",
        "settlement_date":   "portfolios[*].cash_movements[*].trade?.settle_date",
        "quantity":          "portfolios[*].cash_movements[*].trade?.qty",
        "price":             "portfolios[*].cash_movements[*].trade?.unit_price",
        "costs":             "portfolios[*].cash_movements[*].trade?.fees",
        "settlement_amount": "portfolios[*].cash_movements[*].trade?.consideration",
    },
    # A security has no list of its own: it is copied inside every trade and
    # every dividend. Two blocks, one per place; one record per ticker is kept.
    "securities": [
        {
            "ticker":        "portfolios[*].cash_movements[*].trade?.security.ticker",
            "name":          "portfolios[*].cash_movements[*].trade?.security.name",
            "security_type": "portfolios[*].cash_movements[*].trade?.security.type",
            "domicile":      "portfolios[*].cash_movements[*].trade?.security.domicile",
        },
        {
            "ticker":        "portfolios[*].cash_movements[*].dividend?.security.ticker",
            "name":          "portfolios[*].cash_movements[*].dividend?.security.name",
            "security_type": "portfolios[*].cash_movements[*].dividend?.security.type",
            "domicile":      "portfolios[*].cash_movements[*].dividend?.security.domicile",
        },
    ],
    # The cash book comes from two places, so it has two blocks.
    # Only some movements have a trade or a dividend: "trade?" and "dividend?"
    # give None for the others. If one is there, the rest of its path must be too.
    "cash_book": [
        {   # client movements, inside each portfolio
            "entry_id":     "portfolios[*].cash_movements[*].movement_id",
            "date":         "portfolios[*].cash_movements[*].value_date",
            "recorded_at":  "portfolios[*].cash_movements[*].entered_on",
            "entry_type":   "portfolios[*].cash_movements[*].kind",
            "description":  "portfolios[*].cash_movements[*].narrative",
            "reference":    "portfolios[*].cash_movements[*].our_ref",
            "direction":    "portfolios[*].cash_movements[*].direction",
            "amount":       "portfolios[*].cash_movements[*].amount",
            "trade_id":     "portfolios[*].cash_movements[*].trade?.trade_ref",
            "ticker":       "portfolios[*].cash_movements[*].dividend?.security.ticker",
            "account_id":   "portfolios[*].custody_account",
            "portfolio_id": "portfolios[*].portfolio_id",
        },
        {   # account movements (custody fee, interest), inside each account
            "entry_id":     "accounts[*].account_movements[*].movement_id",
            "date":         "accounts[*].account_movements[*].value_date",
            "recorded_at":  "accounts[*].account_movements[*].entered_on",
            "entry_type":   "accounts[*].account_movements[*].kind",
            "description":  "accounts[*].account_movements[*].narrative",
            "reference":    "accounts[*].account_movements[*].our_ref",
            "direction":    "accounts[*].account_movements[*].direction",
            "amount":       "accounts[*].account_movements[*].amount",
            "trade_id":     "accounts[*].account_movements[*].trade?.trade_ref",
            "ticker":       "accounts[*].account_movements[*].dividend?.security.ticker",
            "account_id":   "accounts[*].account_id",
            "portfolio_id": None,      # account movements belong to no portfolio
        },
    ],
}

# The firm's top-level datasets, and the id field that names each of their
# records in `source`. Every path starts with one of these.
FIRM_RECORD_IDS = {
    "accounts": "account_id",
    "portfolios": "portfolio_id",
}

# The firm's direction codes : which Liquet column the amount goes in.
FIRM_DIRECTION_CODES = {
    "IN": "debit",
    "OUT": "credit",
}