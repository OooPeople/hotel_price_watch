"""FastAPI app entrypoint for the local management UI."""

from fastapi import FastAPI


def create_app() -> FastAPI:
    """Create the local web app without starting runtime services yet."""
    app = FastAPI(title="hotel_price_watch", version="0.1.0")

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
