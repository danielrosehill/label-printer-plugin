# label-printer MCP server

Streamable-HTTP MCP server that renders label bitmaps and posts them to a
[print bridge](https://github.com/danielrosehill/ptouch-cube-print-bridge) driving a
Brother P-touch over USB.

Rendering is done here with PIL + `qrcode` at 12 px/mm (~305 dpi); the bridge
downscales to the 180 dpi print head and thresholds to 1-bit.

Callers can also skip the built-in renderer entirely and submit their own bitmap
to `print_image_label` — `label_canvas` reports the pixel canvas to draw onto.
That is the supported route for anything the text renderer can't express, mixed
scripts above all: it picks one font per label, so a Latin+Hebrew label prints
tofu for whichever script the chosen face lacks.

See the [repo README](../README.md) for the tool list, configuration and install.

## Run locally

```bash
uv venv .venv && source .venv/bin/activate
uv pip install -r requirements.txt
PRINT_BRIDGE_URL=http://<bridge-host>:9180 \
FONT_BOLD=fonts/Inter-ExtraBold.ttf FONT_REGULAR=fonts/Inter-Regular.ttf \
python server.py
```

## Note on the `mcp` pin

`requirements.txt` pins `mcp>=1.10,<2`. **mcp 2.0 renamed `mcp.server.fastmcp` to
`mcp.server.mcpserver`**, so an unpinned `mcp>=1.2` will resolve to 2.x and fail at
import with `ModuleNotFoundError: No module named 'mcp.server.fastmcp'`. Lift the pin
only together with porting to the 2.x API.
