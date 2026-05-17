"""Siri Analytics parser — SiriAnalytics.db."""
from typing import List

from .base import BaseParser, ParserError
from .utils import apple_ts, probe_tables
from ..logger import get_logger

_log = get_logger("parsers.siri_analytics")

_DB = ("HomeDomain", "Library/Assistant/SiriAnalytics.db")

# Known tables and the iOS version ranges they appear in
_IOS12_SESSION_TABLE = "SiriSession"
_IOS12_REQUEST_TABLE = "SiriRequest"
_IOS15_PRED_TABLE = "AppPrediction"
_EXTRA_TABLES = ("IntentDefinition", "SiriShortcut")


class SiriAnalyticsParser(BaseParser):
    def parse(self) -> List[dict]:
        conn = self._get_db(*_DB)
        try:
            tables = probe_tables(conn)
            _log.info("SiriAnalytics tables: %s", tables)

            records = []

            if _IOS12_SESSION_TABLE in tables and _IOS12_REQUEST_TABLE in tables:
                records = self._parse_session_request(conn)
            elif _IOS15_PRED_TABLE in tables:
                records = self._parse_app_prediction(conn)
            elif "IntentDefinition" in tables:
                records = self._parse_intent_definition(conn)
            elif "SiriShortcut" in tables:
                records = self._parse_siri_shortcut(conn)
            else:
                raise ParserError(
                    f"No known Siri table found. Tables present: {tables}"
                )

            _log.info("SiriAnalytics: %d records", len(records))
            return records
        finally:
            conn.close()

    def _parse_session_request(self, conn) -> List[dict]:
        """iOS 12-14: join SiriSession + SiriRequest."""
        sql = """
            SELECT
                r.session_id,
                s.startDate,
                r.intent,
                r.bundleID,
                r.latency_ms
            FROM SiriRequest r
            LEFT JOIN SiriSession s ON s.id = r.session_id
            ORDER BY s.startDate DESC
            LIMIT 10000
        """
        rows = conn.execute(sql).fetchall()
        records = []
        for row in rows:
            records.append({
                "timestamp": apple_ts(row[1]),
                "intent": row[2] or "",
                "app_bundle_id": row[3] or "",
                "latency_ms": row[4],
                "session_id": row[0],
            })
        return records

    def _parse_app_prediction(self, conn) -> List[dict]:
        """iOS 15+: AppPrediction table."""
        sql = """
            SELECT bundleId, rank, timestamp
            FROM AppPrediction
            ORDER BY timestamp DESC
            LIMIT 10000
        """
        rows = conn.execute(sql).fetchall()
        records = []
        for row in rows:
            records.append({
                "timestamp": apple_ts(row[2]),
                "intent": f"AppPrediction rank={row[1]}",
                "app_bundle_id": row[0] or "",
                "latency_ms": None,
                "session_id": None,
            })
        return records

    def _parse_intent_definition(self, conn) -> List[dict]:
        """Fallback: IntentDefinition table."""
        sql = "SELECT * FROM IntentDefinition LIMIT 10000"
        cur = conn.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        records = []
        for row in rows:
            r = dict(zip(cols, row))
            records.append({
                "timestamp": None,
                "intent": r.get("intent") or r.get("name") or "",
                "app_bundle_id": r.get("bundleID") or r.get("bundle_id") or "",
                "latency_ms": None,
                "session_id": None,
            })
        return records

    def _parse_siri_shortcut(self, conn) -> List[dict]:
        """Fallback: SiriShortcut table."""
        sql = "SELECT * FROM SiriShortcut LIMIT 10000"
        cur = conn.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        records = []
        for row in rows:
            r = dict(zip(cols, row))
            records.append({
                "timestamp": None,
                "intent": r.get("intent") or r.get("shortcutTitle") or "",
                "app_bundle_id": r.get("bundleID") or r.get("bundle_id") or "",
                "latency_ms": None,
                "session_id": None,
            })
        return records
