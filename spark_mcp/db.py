"""Read-only SQLite access to Spark Desktop's local email databases."""

import os
import sqlite3
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

SPARK_DATA = os.path.expanduser(
    "~/Library/Application Support/Spark Desktop/core-data"
)

MESSAGES_DB = os.path.join(SPARK_DATA, "messages.sqlite")
SEARCH_DB = os.path.join(SPARK_DATA, "search_fts5.sqlite")
CACHE_DB = os.path.join(SPARK_DATA, "cache.sqlite")


class _HTMLStripper(HTMLParser):
    """Strip HTML tags, return plain text."""

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str):
        self._parts.append(data)

    def get_text(self) -> str:
        return "".join(self._parts)


def strip_html(html: str) -> str:
    s = _HTMLStripper()
    s.feed(html)
    return s.get_text()


def _ts_to_iso(ts: int | None) -> str:
    """Convert Unix timestamp to ISO 8601 string."""
    if ts is None or ts == 0:
        return ""
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def get_messages_db() -> sqlite3.Connection:
    """Open a read-only connection to the messages database with cache attached."""
    uri = f"file:{MESSAGES_DB}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute(f"ATTACH DATABASE 'file:{CACHE_DB}?mode=ro' AS cache_db")
    return conn


def get_search_db() -> sqlite3.Connection:
    """Open a read-only connection to the FTS5 search database."""
    uri = f"file:{SEARCH_DB}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def check_databases() -> str:
    """Check that Spark databases exist and are readable."""
    missing = []
    for name, path in [("messages", MESSAGES_DB), ("search", SEARCH_DB), ("cache", CACHE_DB)]:
        if not Path(path).exists():
            missing.append(name)
    if missing:
        return f"Missing databases: {', '.join(missing)}. Is Spark Desktop installed?"
    return "ok"


# --- Query functions ---


ACCOUNT_TYPES = {
    0: "Gmail",
    1: "iCloud",
    2: "IMAP",
    3: "Exchange",
    4: "Outlook",
    5: "Yahoo",
    30: "Google Workspace",
    33: "Exchange (EWS)",
}


def list_accounts() -> str:
    conn = get_messages_db()
    try:
        rows = conn.execute(
            "SELECT pk, accountType, accountTitle, ownerFullName FROM accounts ORDER BY orderNumber"
        ).fetchall()
        if not rows:
            return "No accounts found."
        lines = []
        for r in rows:
            atype = ACCOUNT_TYPES.get(r["accountType"], f"Type {r['accountType']}")
            lines.append(f"- [{r['pk']}] {r['accountTitle']} ({atype}) -- {r['ownerFullName'] or ''}")
        return "\n".join(lines)
    finally:
        conn.close()


def search_emails(
    query: str,
    account: int | None = None,
    limit: int = 20,
) -> str:
    """Full-text search across all accounts using Spark's FTS5 index."""
    # FTS5 must be queried on its own connection (ATTACH breaks MATCH)
    search_conn = get_search_db()
    try:
        fts_rows = search_conn.execute(
            """
            SELECT messagePk, subject AS fts_subject,
                   snippet(messagesfts, 4, '>>>', '<<<', '...', 40) AS snippet
            FROM messagesfts
            WHERE messagesfts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (query, limit * 3),  # fetch extra to allow filtering by account
        ).fetchall()
    finally:
        search_conn.close()

    if not fts_rows:
        return f"No messages found for: {query}"

    pks = [r["messagePk"] for r in fts_rows]
    snippets = {r["messagePk"]: r["snippet"] for r in fts_rows}

    conn = get_messages_db()
    try:
        placeholders = ",".join("?" * len(pks))
        sql = f"""
            SELECT m.pk, m.subject, m.messageFrom, m.messageTo,
                   m.receivedDate, m.shortBody, m.accountPk,
                   a.accountTitle
            FROM messages m
            JOIN accounts a ON a.pk = m.accountPk
            WHERE m.pk IN ({placeholders})
        """
        params: list = list(pks)
        if account is not None:
            sql += " AND m.accountPk = ?"
            params.append(account)
        sql += " ORDER BY m.receivedDate DESC"

        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    if not rows:
        return f"No messages found for: {query}"

    # Trim to limit after account filtering
    rows = rows[:limit]

    lines = []
    for r in rows:
        date = _ts_to_iso(r["receivedDate"])
        snip = snippets.get(r["pk"], r["shortBody"] or "")
        lines.append(
            f"[pk={r['pk']}] {date} | {r['accountTitle']}\n"
            f"  From: {r['messageFrom']}\n"
            f"  To: {r['messageTo']}\n"
            f"  Subject: {r['subject']}\n"
            f"  Snippet: {snip}\n"
        )
    return f"Found {len(rows)} result(s):\n\n" + "\n".join(lines)


def get_message(message_pk: int) -> str:
    """Get full message detail including body text."""
    conn = get_messages_db()
    try:
        row = conn.execute(
            """
            SELECT m.*, a.accountTitle
            FROM messages m
            JOIN accounts a ON a.pk = m.accountPk
            WHERE m.pk = ?
            """,
            (message_pk,),
        ).fetchone()
        if not row:
            return f"Message pk={message_pk} not found."

        # Get body from cache
        body_row = conn.execute(
            "SELECT data FROM cache_db.messageBodyHtml WHERE messagePk = ?",
            (message_pk,),
        ).fetchone()
        body_text = ""
        if body_row and body_row["data"]:
            raw = body_row["data"]
            html = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
            body_text = strip_html(html)

        # Get attachments
        attachments = conn.execute(
            "SELECT attachmentName, attachmentMIMEType, attachmentSize FROM messageAttachment WHERE messagePk = ?",
            (message_pk,),
        ).fetchall()

        lines = [
            f"Account: {row['accountTitle']}",
            f"Date: {_ts_to_iso(row['receivedDate'])}",
            f"From: {row['messageFrom']}",
            f"To: {row['messageTo']}",
        ]
        if row["messageCc"]:
            lines.append(f"Cc: {row['messageCc']}")
        lines.append(f"Subject: {row['subject']}")

        if attachments:
            lines.append(f"\nAttachments ({len(attachments)}):")
            for att in attachments:
                size = att["attachmentSize"] or 0
                size_str = f"{size / 1024:.0f} KB" if size > 0 else "unknown size"
                lines.append(f"  - {att['attachmentName']} ({att['attachmentMIMEType']}, {size_str})")

        lines.append(f"\n--- Body ---\n{body_text or row['shortBody'] or '(no body available)'}")
        return "\n".join(lines)
    finally:
        conn.close()


def get_conversation(conversation_pk: int, limit: int = 50) -> str:
    """Get all messages in a conversation thread."""
    conn = get_messages_db()
    try:
        conv = conn.execute(
            "SELECT c.*, a.accountTitle FROM conversations c JOIN accounts a ON a.pk = c.accountPk WHERE c.pk = ?",
            (conversation_pk,),
        ).fetchone()
        if not conv:
            return f"Conversation pk={conversation_pk} not found."

        rows = conn.execute(
            """
            SELECT pk, messageFrom, messageTo, receivedDate, subject, shortBody
            FROM messages
            WHERE conversationPk = ?
            ORDER BY receivedDate ASC
            LIMIT ?
            """,
            (conversation_pk, limit),
        ).fetchall()

        lines = [
            f"Conversation: {conv['subject']} ({conv['accountTitle']})",
            f"Messages: {conv['totalMessages']} | Unseen: {conv['unseenMessages']}",
            f"Last activity: {_ts_to_iso(conv['lastMessageDate'])}",
            "",
        ]
        for r in rows:
            date = _ts_to_iso(r["receivedDate"])
            lines.append(
                f"[pk={r['pk']}] {date} | {r['messageFrom']}\n"
                f"  {r['shortBody'] or '(no preview)'}\n"
            )
        return "\n".join(lines)
    finally:
        conn.close()


def list_recent(
    account: int | None = None,
    limit: int = 20,
    inbox_only: bool = True,
) -> str:
    """List recent messages, optionally filtered by account."""
    conn = get_messages_db()
    try:
        sql = """
            SELECT m.pk, m.subject, m.messageFrom, m.messageTo,
                   m.receivedDate, m.shortBody, m.unseen, m.starred,
                   m.conversationPk, a.accountTitle
            FROM messages m
            JOIN accounts a ON a.pk = m.accountPk
            WHERE 1=1
        """
        params: list = []
        if inbox_only:
            sql += " AND m.inInbox = 1"
        if account is not None:
            sql += " AND m.accountPk = ?"
            params.append(account)
        sql += " ORDER BY m.receivedDate DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(sql, params).fetchall()
        if not rows:
            return "No recent messages found."

        lines = []
        for r in rows:
            date = _ts_to_iso(r["receivedDate"])
            flags = ""
            if r["unseen"]:
                flags += " [UNREAD]"
            if r["starred"]:
                flags += " [STARRED]"
            lines.append(
                f"[pk={r['pk']} conv={r['conversationPk']}] {date} | {r['accountTitle']}{flags}\n"
                f"  From: {r['messageFrom']}\n"
                f"  Subject: {r['subject']}\n"
                f"  Preview: {r['shortBody'] or ''}\n"
            )
        return f"{len(rows)} recent message(s):\n\n" + "\n".join(lines)
    finally:
        conn.close()


def search_contacts(query: str, limit: int = 20) -> str:
    """Search contacts by name or email."""
    conn = get_messages_db()
    try:
        rows = conn.execute(
            """
            SELECT name, email, isImportant, category
            FROM contacts
            WHERE name LIKE ? OR email LIKE ?
            ORDER BY isImportant DESC, name
            LIMIT ?
            """,
            (f"%{query}%", f"%{query}%", limit),
        ).fetchall()
        if not rows:
            return f"No contacts matching: {query}"
        lines = []
        for r in rows:
            imp = " [important]" if r["isImportant"] else ""
            lines.append(f"- {r['name'] or '(no name)'} <{r['email']}>{imp}")
        return f"{len(rows)} contact(s):\n" + "\n".join(lines)
    finally:
        conn.close()


def list_folders(account: int | None = None) -> str:
    """List email folders/labels."""
    conn = get_messages_db()
    try:
        sql = """
            SELECT f.pk, f.folderName, f.folderPath, f.accountPk,
                   f.imapMessageCount, f.imapMessageUnseenCount,
                   a.accountTitle
            FROM folders f
            JOIN accounts a ON a.pk = f.accountPk
            WHERE 1=1
        """
        params: list = []
        if account is not None:
            sql += " AND f.accountPk = ?"
            params.append(account)
        sql += " ORDER BY a.accountTitle, f.folderPath"

        rows = conn.execute(sql, params).fetchall()
        if not rows:
            return "No folders found."

        lines = []
        current_account = None
        for r in rows:
            if r["accountTitle"] != current_account:
                current_account = r["accountTitle"]
                lines.append(f"\n{current_account}:")
            count = r["imapMessageCount"] or 0
            unseen = r["imapMessageUnseenCount"] or 0
            unseen_str = f" ({unseen} unread)" if unseen > 0 else ""
            lines.append(f"  [{r['pk']}] {r['folderPath'] or r['folderName']} -- {count} msgs{unseen_str}")
        return "\n".join(lines)
    finally:
        conn.close()
