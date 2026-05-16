"""Apple Wallet parser — payment transactions, passes, boarding passes.

Path: HomeDomain / Library/Passes/passes23.sqlite
Tables:
  payment_transaction — Apple Pay transactions (merchant, amount, lat/lon, timestamp)
  pass — boarding passes, loyalty cards, event tickets
"""
from typing import List

from .base import BaseParser, ParserError
from .utils import apple_ts, probe_tables
from ..logger import get_logger

_log = get_logger("parsers.wallet")

_WALLET_DB = ("HomeDomain", "Library/Passes/passes23.sqlite")

_TRANSACTIONS_SQL = """
    SELECT
        ZMERCHANTNAME           AS merchant,
        ZAMOUNT                 AS amount,
        ZCURRENCYCODE           AS currency,
        ZLATITUDE               AS lat,
        ZLONGITUDE              AS lon,
        ZTIMESTAMP              AS raw_ts,
        ZPAYMENTINSTRUMENTLASTFOUR AS card_last4,
        ZPAYMENTINSTRUMENTTYPE  AS card_type
    FROM ZPAYMENTTRANSACTION
    ORDER BY ZTIMESTAMP DESC
"""

_PASSES_SQL = """
    SELECT
        ZPASSTYPE               AS pass_type,
        ZDESCRIPTION            AS description,
        ZORGANIZATIONNAME       AS org_name,
        ZSERIALNUMBER           AS serial,
        ZEXPIRATIONDATE         AS raw_expiry,
        ZRELEVANTDATE           AS raw_relevant
    FROM ZPASS
    ORDER BY ZRELEVANTDATE DESC
    LIMIT 1000
"""


class WalletParser(BaseParser):
    def parse(self) -> List[dict]:
        try:
            conn = self._get_db(*_WALLET_DB)
        except FileNotFoundError:
            raise ParserError("Apple Wallet passes23.sqlite not found in this backup")
        try:
            tables = probe_tables(conn)
            records = []

            if "ZPAYMENTTRANSACTION" in tables:
                for r in conn.execute(_TRANSACTIONS_SQL).fetchall():
                    amount = r["amount"]
                    try:
                        amount_fmt = f"{float(amount):.2f} {r['currency'] or ''}"
                    except (TypeError, ValueError):
                        amount_fmt = str(amount or "")
                    records.append({
                        "type": "Apple Pay",
                        "timestamp": apple_ts(r["raw_ts"]),
                        "merchant": r["merchant"] or "",
                        "amount": amount_fmt,
                        "card": f"···{r['card_last4'] or ''} {r['card_type'] or ''}".strip(),
                        "lat": r["lat"],
                        "lon": r["lon"],
                        "description": "",
                    })

            if "ZPASS" in tables:
                for r in conn.execute(_PASSES_SQL).fetchall():
                    records.append({
                        "type": r["pass_type"] or "Pass",
                        "timestamp": apple_ts(r["raw_relevant"]),
                        "merchant": r["org_name"] or "",
                        "amount": "",
                        "card": r["serial"] or "",
                        "lat": None,
                        "lon": None,
                        "description": r["description"] or "",
                    })

            _log.info("Wallet: %d records", len(records))
            if not records:
                raise ParserError("Apple Wallet: no transactions or passes found")
            return records
        finally:
            conn.close()
