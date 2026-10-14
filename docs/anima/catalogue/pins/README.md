# Consumer pin register

No consumer release pins are selected yet. A catalogue entry or local path does not imply a pin. When a consumer adopts a module, record the exact producer release identity, dependencies/configuration, contract/schema versions, compatibility decision, required migration, actual caller checks, known limits, and rollback support if verified.

The two `*.json` files beside this note are producer CUT freeze records (`search.sst` CUT1, `construction.stc` CUT2), not consumer adoptions. See [STAGING-HASH-NOTE.md](STAGING-HASH-NOTE.md) for the one stale STC hash entry (7/8 match, historical values preserved).

Stage upstream updates separately. Existing runs keep their original pins unless a deliberate migration is recorded.
