from fastapi import APIRouter, Depends, Form, UploadFile

from app.api.deps import get_document_service
from app.api.schemas import DocumentOut, DocumentVersionImport, DocumentVersionOut
from app.application.document_service import DocumentService

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(document_id: int, service: DocumentService = Depends(get_document_service)):
    return await service.get(document_id)


@router.post("/{document_id}/versions", response_model=DocumentVersionOut, status_code=201)
async def upload_version(
    document_id: int,
    file: UploadFile,
    uploaded_by: str = Form(...),
    notes: str | None = Form(default=None),
    service: DocumentService = Depends(get_document_service),
):
    content = await file.read()
    return await service.upload_version(
        document_id,
        content,
        file.filename or "file",
        file.content_type or "application/octet-stream",
        uploaded_by,
        notes,
    )


@router.post("/{document_id}/versions/import", response_model=DocumentVersionOut, status_code=201)
async def import_version(
    document_id: int,
    payload: DocumentVersionImport,
    service: DocumentService = Depends(get_document_service),
):
    return await service.import_version_from_external(
        document_id, payload.connection_id, payload.external_file_id, payload.uploaded_by, payload.notes
    )
