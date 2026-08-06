# Architecture

## Data flow

```text
ChatGPT / MCP client
        |
        | Streamable HTTP (/mcp)
        v
Google Photos Bridge
        |
        +--> ImmichProvider --> Immich REST API --> indexed private library
        |
        +--> GooglePhotosWebProvider --> localhost Chrome DevTools --> photos.google.com
```

## Design decisions

### Read-only by construction

Only search, metadata, album listing, and preview retrieval are registered as MCP tools. No mutating provider methods exist in the base interface.

### Provider isolation

The MCP surface is provider-neutral. Migrating from the browser adapter to Immich requires changing environment variables, not changing prompts or MCP tool names.

### No Google credentials in the MCP process

The direct adapter reuses a dedicated Chrome profile. It does not accept or store a Google password. The Google session remains in Chrome's profile storage.

### Session-local browser identifiers

Google Photos does not expose stable IDs through the web UI. The adapter hashes result URLs and keeps the mapping in memory. Search again after a restart.

### Preview-first retrieval

The model receives a bounded image preview through MCP Image content. This avoids moving full-resolution originals unless a future explicit original-download tool is deliberately added.

## Deployment phases

1. Direct browser adapter for immediate access to the live Google Photos library.
2. One-time Takeout import into Immich.
3. Automatic Immich mobile backup for new photos.
4. Switch `PHOTO_PROVIDER` from `google_web` to `immich`.
5. Keep the browser adapter disabled but available for migration gaps.
