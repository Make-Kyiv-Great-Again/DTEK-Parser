import os
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()

# Setup templates directory relative to this file
templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
templates = Jinja2Templates(directory=templates_dir)

@router.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Render the main interactive map page."""
    return templates.TemplateResponse(request, "index.html")

@router.get("/StatusCoordinates/Demo", response_class=HTMLResponse)
async def read_status_coordinates_demo(request: Request):
    """Render the coordinates-based geolocation map demo page."""
    return templates.TemplateResponse(request, "status_coordinates_demo.html")