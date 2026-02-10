"""ACL management API endpoints."""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.acl.dependencies import require_entitlements
from app.acl.models import Entitlements
from app.acl.policy import PolicyUpdateService
from app.db.session import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/acl", tags=["acl"])


class PolicyUpdateRequest(BaseModel):
    """Request to update a document's ACL policy."""

    visibility: Optional[str] = Field(
        default=None, description="Visibility: public, internal, or restricted"
    )
    allowed_roles: Optional[List[str]] = Field(
        default=None, description="Roles allowed to access (for internal visibility)"
    )
    allowed_groups: Optional[List[str]] = Field(
        default=None, description="Groups allowed to access (for internal visibility)"
    )
    allowed_users: Optional[List[str]] = Field(
        default=None, description="Users allowed to access (for restricted visibility)"
    )


class PolicyResponse(BaseModel):
    """Response with document ACL policy."""

    doc_id: str
    tenant_id: Optional[str] = None
    visibility: Optional[str] = None
    allowed_roles: Optional[List[str]] = None
    allowed_groups: Optional[List[str]] = None
    allowed_users: Optional[List[str]] = None
    policy_version: Optional[int] = None
    acl_updated_at: Optional[str] = None


@router.put("/documents/{doc_id}/policy", response_model=PolicyResponse)
def update_document_policy(
    doc_id: str,
    request: PolicyUpdateRequest,
    db: Session = Depends(get_session),
    entitlements: Entitlements = Depends(require_entitlements),
):
    """Update a document's ACL policy.

    Requires admin role. Increments policy_version and propagates
    changes to Milvus scalar fields.
    """
    if not entitlements.is_admin:
        raise HTTPException(
            status_code=403, detail="Admin role required to update ACL policies"
        )

    svc = PolicyUpdateService(db)
    try:
        doc = svc.update_policy(
            doc_id=doc_id,
            visibility=request.visibility,
            allowed_roles=request.allowed_roles,
            allowed_groups=request.allowed_groups,
            allowed_users=request.allowed_users,
        )
        db.commit()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    policy = svc.get_policy(doc_id)
    return PolicyResponse(**policy)


@router.get("/documents/{doc_id}/policy", response_model=PolicyResponse)
def get_document_policy(
    doc_id: str,
    db: Session = Depends(get_session),
    entitlements: Entitlements = Depends(require_entitlements),
):
    """Get a document's current ACL policy.

    Requires admin role.
    """
    if not entitlements.is_admin:
        raise HTTPException(
            status_code=403, detail="Admin role required to view ACL policies"
        )

    svc = PolicyUpdateService(db)
    policy = svc.get_policy(doc_id)
    if policy is None:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")

    return PolicyResponse(**policy)
