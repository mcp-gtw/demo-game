import app.main as main


def test_app_is_built():
    assert main.app is not None
    assert main.gateway.mcp_server_name == "app"


def test_run_invokes_uvicorn(monkeypatch):
    captured = {}

    def fake_run(app, **kwargs):
        captured["app"] = app
        captured["kwargs"] = kwargs

    import uvicorn

    monkeypatch.setattr(uvicorn, "run", fake_run)
    main.run()

    assert captured["app"] is main.app
    assert "host" in captured["kwargs"]
