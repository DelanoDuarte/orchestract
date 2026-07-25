from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routers import agents, documents, organizations, storage, workflows
from app.domain.shared.exceptions import ConflictError, DomainError, NotFoundError
from app.web.routes import org_router, root_router

app = FastAPI(title="Orchestract", description="Contract & document workflow orchestrator")


@app.exception_handler(NotFoundError)
async def handle_not_found(request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ConflictError)
async def handle_conflict(request: Request, exc: ConflictError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(DomainError)
async def handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


app.include_router(organizations.router, prefix="/api/v1")
app.include_router(agents.router, prefix="/api/v1")
app.include_router(workflows.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(storage.router, prefix="/api/v1")

app.mount("/static", StaticFiles(directory="app/web/static"), name="static")
app.include_router(root_router)
app.include_router(org_router)
