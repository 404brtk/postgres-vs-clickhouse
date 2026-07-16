from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

_STATIC_DIR = Path(__file__).parent.parent.parent / "static"
_DASHBOARD_HTML = (_STATIC_DIR / "index.html").read_text()
_TRACKER_DEMO_HTML = (_STATIC_DIR / "tracker_demo.html").read_text()


@router.get("/", response_class=HTMLResponse)
def get_dashboard():
    return HTMLResponse(content=_DASHBOARD_HTML)


@router.get("/demo", response_class=HTMLResponse)
def get_tracker_demo():
    return HTMLResponse(content=_TRACKER_DEMO_HTML)
