# Plan

## Done: one backend, one frontend

The two existing tools, **Creator Discovery** and the **Asset Generation
Studio**, now live in one structure, with no new features:

- **backend**: a FastMCP server, the only writer. Claude connects to it
  directly.
- **frontend**: one Streamlit app (Explore / Create) that calls the backend
  through MCP and reads images from the data folder read-only.
- **Packaging**: uv (`pyproject.toml` + `uv.lock`), one Docker image, two
  Compose services.
- **Storage**: the file tree, as before. No database until something needs one.

## Principles to keep

- The backend is the only writer; every client goes through MCP tools.
- Tools are thin wrappers; logic stays in `backend/<tool>/`.
- Local first. No hosting or auth for now.
- Only build what makes the next piece of content faster.

## Not now

These came up and were set aside. Each would be its own plan:

- **A database**, once a feature actually needs one.
- **Pieces, stages and lineage** (a content system of record). Until then the
  Brand pipeline stays in Todoist.
- **People and outlets** saved from Explore.
- **Analytics and publishing**: Buffer covers both.
- **WordPress** as a tool.
