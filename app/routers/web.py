import os
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()

# Setup templates directory relative to this file
templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
templates = Jinja2Templates(directory=templates_dir)

@router.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Render the main interactive map page."""
    return templates.TemplateResponse(request, "index.html")

@router.get("/gDemo", response_class=HTMLResponse)
async def read_gdemo(request: Request):
    """Render the geolocation coordinate demo page."""
    return templates.TemplateResponse(request, "gdemo.html")
