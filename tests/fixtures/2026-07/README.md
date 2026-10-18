# July 2026: the month after June

Made-up data, like June, written to continue June's story. It has the bank
statement, the firm's data and an answer key.

**The firm's data is a full extract, not just July.** `portfolios.json` and
`accounts.json` hold June's movements too, as a firm's database would; Liquet's
connector picks July's by date. So June's Hart entry (CE-2026-06-0008, 19 June)
is in the file but not in July's run, which is exactly why July needs what June
carried forward.

What July contains:

- **June's two carried items arrive** on 1 July: the Hart Family Trust's 5,000.00
  (L2, same reference as June's entry, 12 days late) and the Buy 300 ALBN trade
  (L3, -3,717.00, on time). July's firm data has no entry for either, because
  the firm booked both in June. Until Liquet carries items forward, July's rules
  leave L2 and L3 open.
- **Normal matches:** a withdrawal (L4), a subscription (L5), a trade settling
  T+2 (L7), and the five July fees in one transfer (L8), which add up this month.
- **B1, the Reid pair:** Thomas Reid's 5,000.00 subscription (CE-2026-07-0003)
  arrives by SWIFT as 4,985.00 (L6), with no reference: 15.00 of charges were
  deducted. No rule can pair them, and one call per item sees only half of it.
  Note that L2 (Hart, 5,000.00, still open until carried items are cleared) is
  the only bank line with Reid's amount: a decoy until June's items are handled.
- **B2, the custody fee again** (L9, -45.00): the same as June's B4, which a
  person approved in June.

The book opening (286,661.57) is June's closing after June's approved corrections,
which the firm booked dated June. Those corrections are reflected in the 30 June
balance but are not in the movements: Liquet has no kinds for correction entries
yet. Once both of June's items in transit have cleared (after L3), the bank
balance is 286,661.57, June's true cash balance.

This is test data written to fit June's story, not evidence of anything.