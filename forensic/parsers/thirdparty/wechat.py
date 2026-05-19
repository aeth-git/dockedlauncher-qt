"""WeChat parser — MM.sqlite (multiple SQLite databases per account)."""
import re
from typing import List

from ..base import BaseParser, ParserError
from ..utils import unix_ts, probe_tables
from ...logger import get_logger

_log = get_logger("parsers.wechat")

_BUNDLE = "com.tencent.xin"

_MSG_SQL = """
    SELECT
        MesLocalID      AS id,
        Message         AS body,
        CreateTime      AS raw_ts,
        Des             AS direction,
        FromUserName    AS sender,
        ToUserName      AS recipient,
        TableVer        AS table_ver
    FROM Chat_{table_name}
    ORDER BY CreateTime DESC
"""

_CONTACT_SQL = """
    SELECT
        UserName    AS username,
        NickName    AS nickname,
        Alias       AS alias
    FROM Friend
"""


class WeChatParser(BaseParser):
    def parse(self) -> List[dict]:
        domain = f"AppDomain-{_BUNDLE}"

        # Find MM.sqlite databases — there's one per account
        db_files = self._source.list_files(domain, "Documents/")
        mm_files = [(rel, path) for rel, path in db_files
                    if rel.endswith("MM.sqlite")]

        if not mm_files:
            raise ParserError("WeChat: MM.sqlite not found in this backup")

        all_records: List[dict] = []

        for rel_path, _ in mm_files[:5]:   # limit to 5 accounts
            try:
                conn = self._get_db(domain, rel_path)
            except (FileNotFoundError, ParserError):
                continue
            try:
                tables = probe_tables(conn)

                # Build contact map from Friend table
                contact_map: dict = {}
                if "Friend" in tables:
                    for r in conn.execute(_CONTACT_SQL).fetchall():
                        contact_map[r["username"]] = (
                            r["nickname"] or r["alias"] or r["username"]
                        )

                # Chat tables are named Chat_<md5hash>
                chat_tables = [t for t in tables if re.match(r"Chat_[0-9a-fA-F]+", t)]
                for table in chat_tables[:50]:   # limit tables scanned
                    try:
                        rows = conn.execute(
                            f"SELECT MesLocalID AS id, Message AS body, "
                            f"CreateTime AS raw_ts, Des AS direction, "
                            f"FromUserName AS sender, ToUserName AS recipient "
                            f"FROM [{table}] ORDER BY CreateTime DESC LIMIT 1000"
                        ).fetchall()
                        for r in rows:
                            sender = r["sender"] or ""
                            all_records.append({
                                "id": f"{table}_{r['id']}",
                                "timestamp": unix_ts(r["raw_ts"]),
                                "body": r["body"] or "",
                                "contact": contact_map.get(sender, sender),
                                "chat": table,
                                "direction": "Sent" if r["direction"] == 0 else "Received",
                                "app": "WeChat",
                            })
                    except Exception:
                        continue
            finally:
                conn.close()

        if not all_records:
            raise ParserError("WeChat: no messages found in MM.sqlite databases")

        all_records.sort(key=lambda r: r.get("timestamp") or "", reverse=True)
        _log.info("WeChat: %d total messages", len(all_records))
        return all_records
