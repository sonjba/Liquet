"""Tests for path_mapper.py: the path rules on their own.

They use small made-up data (shops and their orders) instead of the firm's,
because path_mapper knows nothing about the firm. The firm's mapping is
tested in test_firm_connector.py.
"""

import pytest

from path_mapper import UNKNOWN, Step, check_mapping, extract, parse_path

IDS = {"shops": "shop_id"}   # one dataset, "shops"; each shop is named by its shop_id


def _extract(block, shops):
    return extract(block, {"shops": shops}, IDS)


def _shops_with_refunds():
    """One shop, three orders; only O1 and O3 have a refund."""
    return [{"shop_id": "S1", "orders": [
        {"order_id": "O1", "refund": {"reason": "late"}},
        {"order_id": "O2"},
        {"order_id": "O3", "refund": {"reason": "broken"}},
    ]}]


# ---------------- reading a path ----------------

def test_path_is_split_into_steps():
    assert parse_path("shops[*].orders?[*].refund?.reason") == [
        Step("shops", is_list=True),
        Step("orders", is_list=True, may_be_missing=True),
        Step("refund", may_be_missing=True),
        Step("reason"),
    ]


# ---------------- records ----------------

def test_one_record_per_item_of_the_deepest_list():
    # 1 shop -> 2 days -> 2 + 1 orders = 3 records, each with its parents' values.
    shops = [{
        "shop_id": "S1",
        "days": [
            {"day": "Mon", "orders": [{"total": 1}, {"total": 2}]},
            {"day": "Tue", "orders": [{"total": 3}]},
        ],
    }]
    block = {"shop_id": "shops[*].shop_id",
             "day":     "shops[*].days[*].day",
             "total":   "shops[*].days[*].orders[*].total"}
    assert _extract(block, shops) == [
        {"shop_id": "S1", "day": "Mon", "total": 1, "source": "shops/S1/days/0/orders/0"},
        {"shop_id": "S1", "day": "Mon", "total": 2, "source": "shops/S1/days/0/orders/1"},
        {"shop_id": "S1", "day": "Tue", "total": 3, "source": "shops/S1/days/1/orders/0"},
    ]


def test_each_record_keeps_its_own_parent():
    # Catches every order taking the first shop's id, or the position running
    # on across shops (0, 1, 2) instead of starting again in each (0, 1 / 0).
    shops = [
        {"shop_id": "S1", "orders": [{"total": 1}, {"total": 2}]},
        {"shop_id": "S2", "orders": [{"total": 3}]},
    ]
    block = {"shop_id": "shops[*].shop_id", "total": "shops[*].orders[*].total"}
    assert _extract(block, shops) == [
        {"shop_id": "S1", "total": 1, "source": "shops/S1/orders/0"},
        {"shop_id": "S1", "total": 2, "source": "shops/S1/orders/1"},
        {"shop_id": "S2", "total": 3, "source": "shops/S2/orders/0"},
    ]


def test_top_level_item_without_id_is_named_unknown():
    assert _extract({"name": "shops[*].name"}, [{"name": "Corner"}]) == [
        {"name": "Corner", "source": f"shops/{UNKNOWN}"},
    ]


def test_no_items_gives_no_records():
    assert _extract({"shop_id": "shops[*].shop_id"}, []) == []


def test_list_that_is_not_there_raises():
    # Silent wrong before: a missing (or renamed) list gave no records.
    with pytest.raises(ValueError, match="shops/S1: missing 'orders'"):
        _extract({"total": "shops[*].orders[*].total"}, [{"shop_id": "S1"}])


@pytest.mark.parametrize("orders", ["not there", None])
def test_list_marked_question_mark_may_be_missing(orders):
    shop = {"shop_id": "S1"} if orders == "not there" else {"shop_id": "S1", "orders": None}
    assert _extract({"total": "shops[*].orders?[*].total"}, [shop]) == []


def test_list_marked_question_mark_is_read_when_there():
    shops = [{"shop_id": "S1", "orders": [{"total": 1}]}]
    assert _extract({"total": "shops[*].orders?[*].total"}, shops) == [
        {"total": 1, "source": "shops/S1/orders/0"},
    ]


def test_none_in_the_mapping_gives_none():
    block = {"shop_id": "shops[*].shop_id", "manager": None}
    assert _extract(block, [{"shop_id": "S1"}]) == [
        {"shop_id": "S1", "manager": None, "source": "shops/S1"},
    ]


def test_list_of_blocks_gives_each_blocks_records_in_order():
    # Like the cash book: movements from portfolios, then from accounts.
    blocks = [{"total": "shops[*].orders[*].total"},
              {"total": "shops[*].returns[*].total"}]
    shops = [{"shop_id": "S1", "orders": [{"total": 1}], "returns": [{"total": 2}]}]
    assert extract(blocks, {"shops": shops}, IDS) == [
        {"total": 1, "source": "shops/S1/orders/0"},
        {"total": 2, "source": "shops/S1/returns/0"},
    ]


# ---------------- "?": this part may be missing ----------------

def test_question_mark_shared_by_all_own_fields_skips_items_without_it():
    # Like trades: an order without a refund is not a refund.
    block = {"shop_id": "shops[*].shop_id",
             "reason":  "shops[*].orders[*].refund?.reason"}
    assert _extract(block, _shops_with_refunds()) == [
        {"shop_id": "S1", "reason": "late",   "source": "shops/S1/orders/0/refund"},
        {"shop_id": "S1", "reason": "broken", "source": "shops/S1/orders/2/refund"},
    ]


def test_question_mark_in_one_field_gives_none_for_that_field():
    # Like trade_id in the cash book: every order is a record, and the one
    # without a refund gets None.
    block = {"order_id": "shops[*].orders[*].order_id",
             "reason":   "shops[*].orders[*].refund?.reason"}
    assert _extract(block, _shops_with_refunds()) == [
        {"order_id": "O1", "reason": "late",   "source": "shops/S1/orders/0"},
        {"order_id": "O2", "reason": None,     "source": "shops/S1/orders/1"},
        {"order_id": "O3", "reason": "broken", "source": "shops/S1/orders/2"},
    ]


def test_after_the_question_mark_the_rest_is_required():
    # Silent wrong before: a refund without a reason gave None, exactly like
    # an order with no refund at all.
    shops = [{"shop_id": "S1", "orders": [{"order_id": "O1", "refund": {}}]}]
    block = {"order_id": "shops[*].orders[*].order_id",
             "reason":   "shops[*].orders[*].refund?.reason"}
    with pytest.raises(ValueError) as error:
        _extract(block, shops)
    assert str(error.value) == "shops/S1/orders/0: missing 'refund.reason' (for reason)"


def test_question_mark_on_the_field_itself_gives_none():
    block = {"order_id": "shops[*].orders[*].order_id",
             "note":     "shops[*].orders[*].note?"}
    shops = [{"shop_id": "S1", "orders": [{"order_id": "O1"}]}]
    assert _extract(block, shops)[0]["note"] is None


def test_null_counts_as_missing():
    shops = [{"shop_id": "S1", "orders": [{"order_id": "O1", "refund": None, "note": None}]}]
    block = {"order_id": "shops[*].orders[*].order_id",
             "reason":   "shops[*].orders[*].refund?.reason",
             "note":     "shops[*].orders[*].note?"}
    assert _extract(block, shops) == [
        {"order_id": "O1", "reason": None, "note": None, "source": "shops/S1/orders/0"},
    ]


@pytest.mark.parametrize("block", [
    {"reason": "shops[*].orders[*].refund?.reason"},              # refund? on the record path
    {"order_id": "shops[*].orders[*].order_id",
     "reason":   "shops[*].orders[*].refund?.reason"},            # refund? in one field
])
def test_question_mark_part_that_is_not_an_object_raises(block):
    # Silent wrong before: the order was treated as if it had no refund.
    shops = [{"shop_id": "S1", "orders": [{"order_id": "O1", "refund": "yes"}]}]
    with pytest.raises(ValueError, match="'refund' should be an object, got str"):
        _extract(block, shops)


# ---------------- data that must be there ----------------

def test_required_field_missing_raises():
    shops = [{"shop_id": "S1", "orders": [{}]}]
    with pytest.raises(ValueError) as error:
        _extract({"order_id": "shops[*].orders[*].order_id"}, shops)
    assert str(error.value) == "shops/S1/orders/0: missing 'order_id' (for order_id)"


def test_required_field_that_is_null_raises():
    # Silent wrong before: null came through as None.
    shops = [{"shop_id": "S1", "orders": [{"order_id": None}]}]
    with pytest.raises(ValueError, match="missing 'order_id'"):
        _extract({"order_id": "shops[*].orders[*].order_id"}, shops)


def test_required_object_missing_raises():
    # address has no ?, so a shop without one is an error, not None.
    block = {"shop_id": "shops[*].shop_id", "city": "shops[*].address.city"}
    with pytest.raises(ValueError) as error:
        _extract(block, [{"shop_id": "S1"}])
    assert str(error.value) == "shops/S1: missing 'address' (for city)"


def test_required_object_on_the_record_path_missing_raises():
    # Every own field goes through address, so it is on the record path.
    block = {"city": "shops[*].address.city", "street": "shops[*].address.street"}
    with pytest.raises(ValueError) as error:
        _extract(block, [{"shop_id": "S1"}])
    assert str(error.value) == "shops/S1: missing 'address'"


def test_missing_parent_field_names_the_parent():
    # The shop has no name, so the error points at the shop, not at its order.
    block = {"shop_name": "shops[*].name", "total": "shops[*].orders[*].total"}
    with pytest.raises(ValueError) as error:
        _extract(block, [{"shop_id": "S1", "orders": [{"total": 1}]}])
    assert str(error.value) == "shops/S1: missing 'name' (for shop_name)"


def test_list_that_is_not_a_list_raises():
    with pytest.raises(ValueError, match="shops/S1/orders: should be a list, got dict"):
        _extract({"total": "shops[*].orders[*].total"},
                 [{"shop_id": "S1", "orders": {"total": 1}}])


def test_list_item_that_is_not_an_object_raises():
    with pytest.raises(ValueError, match="shops/S1/orders/1: should be an object, got int"):
        _extract({"total": "shops[*].orders[*].total"},
                 [{"shop_id": "S1", "orders": [{"total": 1}, 5]}])


def test_dataset_not_given_raises():
    with pytest.raises(ValueError, match="no data was given for 'shops'"):
        extract({"shop_id": "shops[*].shop_id"}, {}, IDS)


# ---------------- checking a mapping ----------------
# A mistake in the mapping must stop with a message that names the line,
# not with an IndexError or KeyError from somewhere inside the engine.

GOOD_BLOCK = {"shop_id": "shops[*].shop_id", "total": "shops[*].orders[*].total"}


def _mapping_error(mapping, ids=IDS) -> str:
    with pytest.raises(ValueError) as error:
        check_mapping(mapping, ids)
    return str(error.value)


def test_good_mapping_passes():
    check_mapping({"orders": GOOD_BLOCK, "orders_twice": [GOOD_BLOCK, GOOD_BLOCK]}, IDS)


@pytest.mark.parametrize("path, problem", [
    ("shops.orders[*].total",     "'shops.orders[*].total' must start with shops[*]"),
    ("warehouses[*].total",       "'warehouses[*].total' must start with shops[*]"),
    ("shops[*].orders[*]",        "must end with a field name, not a list"),
    ("shops[*].orders[0].total",  "'orders[0]' is not a valid step"),
    ("shops[*].orders[*]?.total", "'orders[*]?' is not a valid step"),
    ("shops[*]..total",           "has an empty step"),
    (42,                          "a path must be text or None, got 42"),
])
def test_bad_path_is_named(path, problem):
    message = _mapping_error({"orders": {"shop_id": "shops[*].shop_id", "total": path}})
    assert message.startswith("orders.total: ")
    assert problem in message


def test_fields_from_different_lists_raise():
    block = {"total": "shops[*].orders[*].total", "amount": "shops[*].returns[*].amount"}
    assert _mapping_error({"orders": block}) == (
        "orders: total and amount come from different lists "
        "(shops[*].orders[*] and shops[*].returns[*]); one block makes records from one list")


def test_field_that_does_not_lead_to_the_records_raises():
    ids = {"shops": "shop_id", "staff": "staff_id"}
    block = {"total": "shops[*].orders[*].total", "staff_name": "staff[*].name"}
    assert _mapping_error({"orders": block}, ids) == (
        "orders.staff_name: 'staff[*].name' does not lead to this block's records "
        "(shops[*].orders[*])")


def test_block_with_only_none_raises():
    assert _mapping_error({"orders": {"manager": None}}) == (
        "orders: needs at least one path, not only None")


def test_source_cannot_be_mapped():
    message = _mapping_error({"orders": {"shop_id": "shops[*].shop_id",
                                         "source": "shops[*].shop_id"}})
    assert message.startswith("orders.source: `source` is added automatically")


def test_block_that_is_not_a_dict_raises():
    assert _mapping_error({"orders": "shops[*].shop_id"}) == (
        "orders: expected a dict of Liquet field: path, got str")


def test_error_names_the_block_in_a_list():
    message = _mapping_error({"orders": [GOOD_BLOCK, {"total": "shops[*].orders[*]"}]})
    assert message.startswith("orders[1].total: ")


def test_extract_checks_its_block_too():
    with pytest.raises(ValueError, match="orders.total: 'shops.total' must start with shops"):
        extract({"total": "shops.total"}, {"shops": []}, IDS, name="orders")