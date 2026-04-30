"""Webserver to allow editing of user data of the airline database.

This is entirely independent of the MCP server, but must run in the same process
since it shares the same in-memory database instance. It is registering routes
using the FastMCP class, but it's unrelated to the MCP protocol itself and just
adds flask routes.

This should not need frequent changes in most deployments."""

from pathlib import Path
from fastmcp import FastMCP
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse
from .database import AirlineDatabase


def register_web_routes(mcp: FastMCP, database: AirlineDatabase) -> None:
    """Attach web routes to the FastMCP server while sharing the database."""

    db = database

    @mcp.custom_route("/", methods=["GET"])
    async def root(_: Request) -> HTMLResponse:
        ui_path = Path(__file__).parent.parent.parent / "ui" / "index.html"
        if not ui_path.exists():
            return HTMLResponse(
                "<html><body><h1>UI Not Found</h1></body></html>",
                status_code=404,
            )
        # On Windows, Path.read_text() defaults to a legacy encoding (e.g. cp1252),
        # which can fail for UTF-8 assets. Serve the UI as UTF-8.
        try:
            html = ui_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            html = ui_path.read_text(encoding="utf-8", errors="replace")
        return HTMLResponse(html)

    @mcp.custom_route("/static/{filename}", methods=["GET"])
    async def static_files(request: Request) -> FileResponse:
        """Serve static assets (images, CSS, JS) from src/mcp_airline/static/."""
        filename = request.path_params.get("filename", "")
        # Reject empty names, path traversal, and absolute paths.
        if not filename or ".." in filename or filename.startswith(("/", "\\")):
            raise HTTPException(status_code=400, detail="Invalid filename")

        static_dir = (Path(__file__).parent / "static").resolve()
        file_path = (static_dir / filename).resolve()

        # Defense-in-depth: ensure the resolved path stays inside static_dir.
        try:
            file_path.relative_to(static_dir)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid path")

        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail="Not found")

        return FileResponse(file_path)

    @mcp.custom_route("/api/login", methods=["POST"])
    async def login(request: Request) -> JSONResponse:
        try:
            payload = await request.json()
            user_id = payload.get("user_id")
            if not isinstance(user_id, str) or not user_id:
                return JSONResponse({"error": "user_id is required"}, status_code=400)

            user = db.get_user(user_id)
            return JSONResponse({"success": True, "user_id": user["user_id"]})
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=404)

    @mcp.custom_route("/api/profile/{user_id}", methods=["GET"])
    async def get_profile(request: Request) -> JSONResponse:
        user_id = request.path_params.get("user_id")
        if not user_id:
            return JSONResponse({"error": "user_id is required"}, status_code=400)

        try:
            user = db.get_user(user_id)
            return JSONResponse(user)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=404)

    @mcp.custom_route("/api/profile/{user_id}", methods=["PUT"])
    async def update_profile(request: Request) -> JSONResponse:
        user_id = request.path_params.get("user_id")
        if not user_id:
            return JSONResponse({"error": "user_id is required"}, status_code=400)

        updates = await request.json()

        try:
            user = db.get_user(user_id)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=404)

        if updates.get("name"):
            name_updates = updates["name"]
            if "first_name" in name_updates:
                user["name"]["first_name"] = name_updates["first_name"]
            if "last_name" in name_updates:
                user["name"]["last_name"] = name_updates["last_name"]

        if updates.get("address"):
            for field in ["address1", "address2", "city", "state", "zip", "country"]:
                if field in updates["address"]:
                    user["address"][field] = updates["address"][field]

        if "email" in updates:
            user["email"] = updates["email"]

        if "saved_passengers" in updates:
            user["saved_passengers"] = updates["saved_passengers"]

        if "payment_methods" in updates:
            user["payment_methods"] = updates["payment_methods"]

        return JSONResponse({"success": True, "user": user})
