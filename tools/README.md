# Tools Directory

This directory contains external tools and utilities that support the NORTH AI system but are not part of the core application.

## mcp-server-weaviate/

**Purpose**: Model Context Protocol (MCP) server for Weaviate integration

**Language**: Go

**Source**: External MCP server implementation for connecting MCP-compatible clients to Weaviate vector databases.

**Status**: Optional tool, not required for NORTH's core functionality

**Usage**: This is a separate Go application that can be compiled and used with MCP-compatible clients. It is not used by NORTH's Python codebase directly.

**Note**: This was included during development exploration of MCP capabilities. It remains here for reference but is not part of NORTH's deployment pipeline.

---

For NORTH's actual Weaviate integration, see:
- `src/agents/obsidian/atomic_document_agent.py` (Obsidian knowledge base)
- `src/agents/dropbox_v2/weaviate_indexer.py` (Dropbox documents)
