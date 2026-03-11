# spark-mcp

Read-only MCP server for [Spark Desktop](https://sparkmailapp.com/) email. Queries Spark's local SQLite databases directly -- no IMAP connections, no API keys, no network access.

## Quick Start with Claude Code

```bash
# 1. Clone and install
git clone https://github.com/bbdaniels/spark-mcp.git
cd spark-mcp && pip install -e .

# 2. Register the MCP server (one-liner)
claude mcp add spark-email -- spark-mcp
```

That's it. Restart Claude Code and you can search, read, and browse your Spark email.

## What it does

Gives Claude (or any MCP client) read-only access to your Spark email:

- **Search** across all accounts using Spark's full-text search index
- **Read** individual messages with full body text
- **Browse** recent inbox, conversation threads, folders, contacts

## Requirements

- macOS with Spark Desktop installed
- Python 3.10+
- `mcp` Python package

## Install

```bash
git clone https://github.com/bbdaniels/spark-mcp.git
cd spark-mcp
pip install -e .
```

## Register with Claude Code

```bash
claude mcp add spark-email -- spark-mcp
```

This registers the `spark-mcp` console script (installed by `pip install -e .`) as an MCP server named `spark-email`. You can also use the module entry point:

```bash
claude mcp add spark-email -- python3 -m spark_mcp.server
```

## Tools

| Tool | Description |
|------|-------------|
| `spark_list_accounts` | List configured email accounts |
| `spark_search` | Full-text search across all accounts |
| `spark_get_message` | Read a specific message with body and attachments |
| `spark_get_conversation` | Read an email thread |
| `spark_recent` | List recent inbox messages |
| `spark_search_contacts` | Search contacts by name or email |
| `spark_list_folders` | List folders/labels per account |

## Security

- All database access is **read-only** (SQLite `?mode=ro`)
- No network connections -- reads only from local disk
- No credentials needed -- uses Spark's existing local cache
