"""Structured ACL audit logging.

Provides structured JSON logging for every ACL decision, enabling
security audit trails and compliance reporting.
"""

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("acl.audit")


class ACLAuditLogger:
    """Structured audit logger for ACL decisions.

    Emits structured JSON log entries for each ACL enforcement action.
    Fields: request_id, tenant_id, user_id, action, doc_id, result, stage,
    entitlements_hash.
    """

    def __init__(
        self,
        request_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        entitlements_hash: Optional[str] = None,
    ):
        self.request_id = request_id
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.entitlements_hash = entitlements_hash

    def log_decision(
        self,
        action: str,
        result: str,
        stage: str,
        doc_id: Optional[str] = None,
        detail: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log a single ACL decision.

        Args:
            action: The action being checked (e.g. "filter_search", "check_doc_access")
            result: "allow" or "deny"
            stage: Pipeline stage (e.g. "vector_search", "expansion_adjacent")
            doc_id: Document ID (if applicable)
            detail: Additional detail dict
        """
        entry = {
            "event": "acl_decision",
            "request_id": self.request_id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "entitlements_hash": self.entitlements_hash,
            "action": action,
            "result": result,
            "stage": stage,
        }
        if doc_id:
            entry["doc_id"] = doc_id
        if detail:
            entry["detail"] = detail

        logger.info(json.dumps(entry, default=str))

    def log_batch_filter(
        self,
        stage: str,
        total: int,
        allowed: int,
        denied: int,
    ) -> None:
        """Log a batch filtering decision.

        Args:
            stage: Pipeline stage
            total: Total items before filter
            allowed: Items that passed
            denied: Items that were filtered out
        """
        self.log_decision(
            action="batch_filter",
            result="partial" if denied > 0 else "allow_all",
            stage=stage,
            detail={"total": total, "allowed": allowed, "denied": denied},
        )
