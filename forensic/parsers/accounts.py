"""Accounts3.sqlite — all configured accounts (Apple ID, iCloud, email, social).

Path: HomeDomain / Library/Accounts/Accounts3.sqlite
Tables: ZACCOUNT, ZACCOUNTTYPE
"""
from typing import List

from .base import BaseParser, ParserError
from .utils import probe_tables
from ..logger import get_logger

_log = get_logger("parsers.accounts")

_ACCOUNTS_DB = ("HomeDomain", "Library/Accounts/Accounts3.sqlite")

_SQL = """
    SELECT
        a.ZUSERNAME             AS username,
        a.ZDISPLAYNAME          AS display_name,
        t.ZIDENTIFIER           AS account_type,
        t.ZDISPLAYNAME          AS type_label,
        a.ZOAUTH_STATE          AS oauth_state
    FROM ZACCOUNT a
    LEFT JOIN ZACCOUNTTYPE t ON a.ZACCOUNTTYPE = t.Z_PK
    ORDER BY t.ZIDENTIFIER, a.ZUSERNAME
"""


class AccountsParser(BaseParser):
    def parse(self) -> List[dict]:
        try:
            conn = self._get_db(*_ACCOUNTS_DB)
        except FileNotFoundError:
            raise ParserError("Accounts3.sqlite not found in this backup")
        try:
            tables = probe_tables(conn)
            if "ZACCOUNT" not in tables:
                raise ParserError("Accounts3.sqlite: ZACCOUNT table missing")
            rows = conn.execute(_SQL).fetchall()
            _log.info("Accounts: %d entries", len(rows))
            return [{
                "username": r["username"] or "",
                "display_name": r["display_name"] or "",
                "account_type": r["account_type"] or "",
                "type_label": r["type_label"] or "",
                "oauth_active": r["oauth_state"] == 1,
            } for r in rows]
        finally:
            conn.close()
