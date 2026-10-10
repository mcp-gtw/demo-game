from fastapi import FastAPI
from starlette.responses import HTMLResponse

app = FastAPI()
visits = {"selected": 0, "unrelated": 0}


@app.get("/connector_platform_oauth_redirect")
async def selected_callback():
    visits["selected"] += 1
    return HTMLResponse('<link rel="icon" href="data:,"><h1>Client callback</h1>')


@app.post("/unrelated")
async def unrelated_callback():
    visits["unrelated"] += 1
    return HTMLResponse("<h1>Unexpected callback</h1>")


@app.get("/stats")
async def callback_stats():
    return visits
