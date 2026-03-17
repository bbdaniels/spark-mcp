"""Spark Email MCP Server -- local SQLite reads + Gmail API draft creation."""

from mcp.server.fastmcp import FastMCP

from spark_mcp.db import (
    check_databases,
    get_conversation,
    get_message,
    list_accounts,
    list_folders,
    list_recent,
    search_contacts,
    search_emails,
)

mcp = FastMCP("spark-email")


@mcp.tool()
def spark_list_accounts() -> str:
    """List all email accounts configured in Spark Desktop.
    Returns account names, types, and PKs for use as filters in other tools."""
    status = check_databases()
    if status != "ok":
        return status
    return list_accounts()


@mcp.tool()
def spark_search(query: str, account: int | None = None, limit: int = 20) -> str:
    """Full-text search across all Spark email accounts.
    Uses Spark's built-in FTS5 index to search message bodies, subjects, senders, and recipients.

    Args:
        query: Search terms (supports FTS5 syntax: AND, OR, NOT, "exact phrase", prefix*)
        account: Optional account PK to filter by (get PKs from spark_list_accounts)
        limit: Max results to return (default 20)
    """
    status = check_databases()
    if status != "ok":
        return status
    return search_emails(query, account=account, limit=limit)


@mcp.tool()
def spark_get_message(message_pk: int) -> str:
    """Read a specific email message including full body text and attachments.

    Args:
        message_pk: The message PK from search results or recent messages list.
    """
    status = check_databases()
    if status != "ok":
        return status
    return get_message(message_pk)


@mcp.tool()
def spark_get_conversation(conversation_pk: int, limit: int = 50) -> str:
    """Read an email conversation/thread -- all messages in order.

    Args:
        conversation_pk: The conversation PK from search results (shown as conv=N).
        limit: Max messages to return (default 50).
    """
    status = check_databases()
    if status != "ok":
        return status
    return get_conversation(conversation_pk, limit=limit)


@mcp.tool()
def spark_recent(account: int | None = None, limit: int = 20, inbox_only: bool = True) -> str:
    """List recent emails, optionally filtered by account.

    Args:
        account: Optional account PK to filter by.
        limit: Max results (default 20).
        inbox_only: If True (default), only show inbox messages.
    """
    status = check_databases()
    if status != "ok":
        return status
    return list_recent(account=account, limit=limit, inbox_only=inbox_only)


@mcp.tool()
def spark_search_contacts(query: str, limit: int = 20) -> str:
    """Search Spark contacts by name or email address.

    Args:
        query: Name or email to search for (partial match).
        limit: Max results (default 20).
    """
    status = check_databases()
    if status != "ok":
        return status
    return search_contacts(query, limit=limit)


@mcp.tool()
def spark_list_folders(account: int | None = None) -> str:
    """List email folders/labels across all accounts.

    Args:
        account: Optional account PK to filter by.
    """
    status = check_databases()
    if status != "ok":
        return status
    return list_folders(account=account)


@mcp.tool()
def spark_create_draft(
    to: str,
    subject: str,
    body: str,
    cc: str = "",
    bcc: str = "",
) -> str:
    """Create an email draft in Personal Gmail. The draft appears in Gmail Drafts
    and syncs to Spark, where you can review, edit the From address, and send.

    Args:
        to: Recipient email address(es), comma-separated.
        subject: Email subject line.
        body: Plain-text email body.
        cc: Optional CC address(es), comma-separated.
        bcc: Optional BCC address(es), comma-separated.
    """
    from spark_mcp.gmail import create_draft

    return create_draft(to=to, subject=subject, body=body, cc=cc, bcc=bcc)


@mcp.tool()
def spark_draft_auth_status() -> str:
    """Check whether Gmail OAuth is configured for draft creation."""
    from spark_mcp.gmail import check_auth

    return check_auth()


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
