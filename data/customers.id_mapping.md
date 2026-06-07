# Customer ID Mapping

Customer IDs in `customers.json` are generated deterministically so that re-seeds
and different team members produce identical IDs.

**Rule:** `cus_` + the first 8 base62 characters (MSB-first) of
`sha1("helios:" + <old_customer_id>)`.

Base62 alphabet: `0-9A-Za-z`.

| Old ID | New ID |
|---|---|
| CUST-001 | cus_5WvnX4nq |
| CUST-002 | cus_XIEADwIa |
| CUST-003 | cus_Jmvq4zyy |
| CUST-004 | cus_MAMb9OM3 |
| CUST-005 | cus_aH6NpKo2 |
| CUST-006 | cus_FdW0mTBh |
| CUST-007 | cus_EefCMtdz |
| CUST-008 | cus_6UsFXSus |
| CUST-009 | cus_CbaPTAUZ |
| CUST-010 | cus_Ku2D362J |
| CUST-011 | cus_7HDEtA36 |
| CUST-012 | cus_S2stD40i |
| CUST-013 | cus_SEkngbR4 |
| CUST-014 | cus_1SncV5mg |
| CUST-015 | cus_8CvG6zl7 |
| CUST-016 | cus_Nh3rZUr7 |
| CUST-017 | cus_6fUvli6z |
| CUST-018 | cus_TkJrN9QT |

The mapping is committed as literals in `customers.json` — no code path computes
these on the fly.
