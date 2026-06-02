#!/usr/bin/env python3
import base64, tempfile, os, contextlib
from pathlib import Path
import uvicorn
from starlette.applications import Starlette
from starlette.responses import JSONResponse, Response
from starlette.routing import Route, Mount
from starlette.requests import Request
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from markitdown import MarkItDown

_sec = TransportSecuritySettings(enable_dns_rebinding_protection=False)
mcp = FastMCP("markitdown-pdf", stateless_http=True, json_response=False, transport_security=_sec, streamable_http_path="/markitdown")
_md = MarkItDown(enable_plugins=False)

@mcp.tool()
def convert_pdf_base64_to_markdown(base64_data: str, filename: str = "document.pdf") -> str:
    """Convert base64-encoded file to Markdown. Args: base64_data: base64 content, filename: for format detection."""
    raw = base64.b64decode(base64_data)
    suffix = Path(filename).suffix or ".pdf"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(raw); tmp_path = tmp.name
    try:
        return _md.convert(tmp_path).text_content or "(no text)"
    finally:
        os.unlink(tmp_path)

@mcp.tool()
def convert_url_to_markdown(url: str) -> str:
    """Fetch URL and convert to Markdown. Args: url: URL to fetch."""
    return _md.convert(url).text_content or "(no text)"

async def oauth_meta(r):
    b = str(r.base_url).rstrip("/")
    return JSONResponse({"issuer":b,"authorization_endpoint":f"{b}/oauth/authorize","token_endpoint":f"{b}/oauth/token","registration_endpoint":f"{b}/oauth/register","response_types_supported":["code"],"grant_types_supported":["authorization_code"],"code_challenge_methods_supported":["S256"],"token_endpoint_auth_methods_supported":["none"]})

async def prot_res(r):
    b = str(r.base_url).rstrip("/")
    return JSONResponse({"resource":b,"authorization_servers":[b]})

async def oauth_register(r):
    body = await r.json()
    return JSONResponse({"client_id":"markitdown-client","client_id_issued_at":0,"redirect_uris":body.get("redirect_uris",[]),"grant_types":["authorization_code"],"response_types":["code"],"token_endpoint_auth_method":"none"})

async def oauth_authorize(r):
    p = dict(r.query_params); uri = p.get("redirect_uri",""); state = p.get("state","")
    sep = "&" if "?" in uri else "?"
    return Response(status_code=302, headers={"Location":f"{uri}{sep}code=mdcode123&state={state}"})

async def oauth_token(r):
    return JSONResponse({"access_token":"markitdown-cloud-token","token_type":"bearer","expires_in":86400})

http_app = mcp.streamable_http_app()
session_mgr = mcp.session_manager

@contextlib.asynccontextmanager
async def lifespan(app):
    async with session_mgr.run():
        yield

routes = [
    Route("/.well-known/oauth-authorization-server", oauth_meta),
    Route("/.well-known/oauth-protected-resource", prot_res),
    Route("/oauth/register", oauth_register, methods=["POST"]),
    Route("/oauth/authorize", oauth_authorize),
    Route("/oauth/token", oauth_token, methods=["POST"]),
    Route("/", lambda r: JSONResponse({"status":"ok","service":"markitdown-mcp"})),
    Mount("/", app=http_app),
]
app = Starlette(routes=routes, lifespan=lifespan)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
