# Google Photos Bridge MCP

A read-only MCP server that lets an AI search and inspect a private photo library without uploading tens of thousands of photos into each conversation.

## Why this bridge exists

Google removed the OAuth scopes that allowed third-party applications to read an entire Google Photos library on March 31, 2025. The current Library API can read only media created by the application. The Picker API requires manual selection and therefore cannot support autonomous search across an existing library.

This project provides two practical adapters:

1. **Immich** — the recommended provider. Import the existing Google Photos history once through Google Takeout, automatically back up new phone photos, then use Immich smart search, OCR, people, dates, places, and metadata.
2. **Google Photos Web** — a direct fallback. The MCP server attaches to a dedicated Chrome profile that is already signed in to Google Photos and drives the web interface in read-only mode.

## MCP tools

- `photo_health`
- `search_photos`
- `get_photo_info`
- `get_photo_preview`
- `list_photo_albums`

The server does not expose delete, edit, move, share, or upload operations.

## Quick start: direct Google Photos adapter

### 1. Start a dedicated Chrome profile

Linux example:

```bash
google-chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/.config/google-photos-mcp-chrome"
```

Open `https://photos.google.com/` in that Chrome window and sign in once. Keep this profile dedicated to the connector.

### 2. Install and run

```bash
cp .env.example .env
# Set PHOTO_PROVIDER=google_web
uv sync --extra dev
uv run google-photos-mcp
```

The MCP endpoint is:

```text
http://127.0.0.1:8765/mcp
```

### 3. Validate

```bash
npx -y @modelcontextprotocol/inspector
```

Connect the inspector to `http://127.0.0.1:8765/mcp` and call `photo_health`.

## Recommended setup: Immich

1. Install Immich using its official Docker Compose deployment.
2. Export the existing library through Google Takeout.
3. Import the Takeout archives with `immich-go`.
4. Enable automatic backup in the Immich Android app for new camera photos.
5. Create an Immich API key with read permissions.
6. Configure:

```dotenv
PHOTO_PROVIDER=immich
IMMICH_URL=https://photos.example.com
IMMICH_API_KEY=replace-me
```

Immich exposes stable metadata search, smart semantic search, OCR, dates, people, places, thumbnails, and originals through its API. This adapter requests only search data, metadata, album lists, and previews.

## Authentication and exposure

The safest deployment is a private machine plus a private MCP tunnel. Do not expose the Chrome debugging port to the internet.

An optional static bearer check can protect the MCP endpoint:

```dotenv
MCP_BEARER_TOKEN=generate-a-long-random-value
```

The Chrome debugging endpoint must remain bound to localhost or a private network. Never publish port `9222`.

## ChatGPT availability

Custom read/fetch MCP apps require an eligible ChatGPT plan and are configured from developer mode on the web client. As of August 2026, custom MCP apps are not available in the ChatGPT mobile app. A local MCP server must be reached through a supported remote endpoint or Secure MCP Tunnel.

## Limitations of the Google Photos Web adapter

- Google can change DOM structure and accessible labels.
- Search result IDs are session-local.
- Date ranges of 31 days or less are expanded into exact-day searches; large ranges rely on Google Photos natural-language interpretation.
- The adapter returns previews suitable for visual inspection, not guaranteed original-resolution files.
- The adapter requires a running Chrome profile with a valid Google session.

For routine use, Immich is the durable architecture. The browser adapter exists to access the live Google Photos library during migration and as a fallback.
