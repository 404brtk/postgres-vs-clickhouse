from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def get_dashboard():
    with open("static/index.html", "r") as f:
        return HTMLResponse(content=f.read())


@router.get("/demo", response_class=HTMLResponse)
def get_tracker_demo():
    with open("static/tracker_demo.html", "r") as f:
        return HTMLResponse(content=f.read())
