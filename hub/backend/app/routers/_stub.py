"""Helper that makes a placeholder router. Every unbuilt feature answers HTTP 501 'planned'."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"]


def stub_router(name: str, feature: str, module: str, future: bool = False) -> APIRouter:
    """name -> URL prefix /api/<name>. module is the build step (e.g. 'M2'); future=True means later scope."""
    router = APIRouter(prefix=f"/api/{name}", tags=[name])
    state = "stub" if future else "planned"
    detail = f"{feature}: " + ("future scope, stub only." if future else f"planned, built in {module}.")

    def not_built(path: str = ""):
        return JSONResponse(status_code=501, content={"status": state, "feature": feature, "module": module, "detail": detail})

    # "" catches /api/<name>, the second catches everything below it.
    router.add_api_route("", not_built, methods=METHODS, include_in_schema=False)
    router.add_api_route("/{path:path}", not_built, methods=METHODS, include_in_schema=False)
    return router
