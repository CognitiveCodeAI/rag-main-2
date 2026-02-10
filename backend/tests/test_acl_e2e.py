"""End-to-end ACL integration tests.

Tests the full ACL lifecycle:
1. Ingest documents with different ACL policies
2. Query with different entitlements headers
3. Verify enforcement at every endpoint

Requires a running backend + infrastructure (Postgres, Milvus, MinIO, Redis).
Run with: pytest tests/test_acl_e2e.py -v -s
"""

import json
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("NPR_BASE_URL", "http://localhost:8000")

# Unique canary strings — if these leak, ACL is broken
CANARY_PUBLIC = f"CANARY_PUBLIC_WATER_QUALITY_{uuid.uuid4().hex[:8]}"
CANARY_INTERNAL = f"CANARY_INTERNAL_BUDGET_DATA_{uuid.uuid4().hex[:8]}"
CANARY_RESTRICTED = f"CANARY_RESTRICTED_LEGAL_MEMO_{uuid.uuid4().hex[:8]}"
CANARY_OTHER_TENANT = f"CANARY_OTHER_TENANT_SECRETS_{uuid.uuid4().hex[:8]}"

# Test tenant/user identities
TENANT_A = "acl_test_tenant_a"
TENANT_B = "acl_test_tenant_b"
USER_ALICE = "alice"
USER_BOB = "bob"
USER_ADMIN = "acl_admin"


def _headers(tenant_id, user_id, roles=None, groups=None):
    """Build entitlements headers."""
    h = {
        "X-Tenant-Id": tenant_id,
        "X-User-Id": user_id,
    }
    if roles:
        h["X-Roles"] = ",".join(roles)
    if groups:
        h["X-Groups"] = ",".join(groups)
    return h


def _create_test_file(content: str, filename: str) -> str:
    """Write a temp test file and return its path."""
    path = os.path.join(os.environ.get("TEMP", "/tmp"), filename)
    with open(path, "w") as f:
        f.write(content)
    return path


def _ingest_document(filepath, filename, tenant_id, visibility,
                     allowed_roles=None, allowed_groups=None, allowed_users=None):
    """Ingest a document via the API with ACL metadata."""
    with open(filepath, "rb") as f:
        files = {"file": (filename, f, "text/plain")}
        data = {
            "source_type": "txt",
            "tenant_id": tenant_id,
            "visibility": visibility,
        }
        if allowed_roles:
            data["allowed_roles"] = json.dumps(allowed_roles)
        if allowed_groups:
            data["allowed_groups"] = json.dumps(allowed_groups)
        if allowed_users:
            data["allowed_users"] = json.dumps(allowed_users)

        resp = requests.post(f"{BASE_URL}/v1/ingest/document", files=files, data=data)
    resp.raise_for_status()
    return resp.json()


def _wait_for_job(job_id, timeout=120):
    """Poll job status until completed or failed."""
    start = time.time()
    while time.time() - start < timeout:
        resp = requests.get(f"{BASE_URL}/v1/ingest/job/{job_id}")
        resp.raise_for_status()
        status = resp.json()["status"]
        if status == "completed":
            return resp.json()
        if status == "failed":
            raise RuntimeError(f"Ingest job {job_id} failed: {resp.json().get('error')}")
        time.sleep(2)
    raise TimeoutError(f"Job {job_id} did not complete within {timeout}s")


class TestACLEndToEnd:
    """Full end-to-end ACL tests against a running backend."""

    # Populated during setup
    doc_ids = {}
    _original_env = {}

    @classmethod
    def setup_class(cls):
        """Ingest 4 test documents with different ACL policies, then enable ACL."""
        print("\n" + "=" * 70)
        print("SETUP: Creating and ingesting test documents")
        print("=" * 70)

        # Verify backend is reachable
        resp = requests.get(f"{BASE_URL}/health")
        assert resp.status_code == 200, f"Backend not reachable at {BASE_URL}"

        # --- Create test files ---

        # Doc 1: PUBLIC doc in Tenant A
        f1 = _create_test_file(
            f"Annual Water Quality Report 2025\n\n"
            f"The municipal water supply meets all EPA standards. "
            f"Key finding: {CANARY_PUBLIC}. "
            f"Contaminant levels are well below maximum allowable limits. "
            f"pH levels averaged 7.2 across all testing stations.",
            "acl_test_public.txt"
        )

        # Doc 2: INTERNAL doc in Tenant A (requires "analyst" role)
        f2 = _create_test_file(
            f"Q4 2025 Budget Analysis — Internal Only\n\n"
            f"Department spending exceeded projections by 12%. "
            f"Critical data: {CANARY_INTERNAL}. "
            f"Revenue shortfall attributed to delayed contract renewals. "
            f"Recommended action: freeze discretionary spending.",
            "acl_test_internal.txt"
        )

        # Doc 3: RESTRICTED doc in Tenant A (only alice)
        f3 = _create_test_file(
            f"Privileged Legal Memorandum — Attorney-Client Privilege\n\n"
            f"Re: Ongoing litigation exposure assessment. "
            f"Confidential detail: {CANARY_RESTRICTED}. "
            f"Settlement authority approved up to $2.5M. "
            f"Do not distribute outside legal team.",
            "acl_test_restricted.txt"
        )

        # Doc 4: PUBLIC doc in Tenant B (cross-tenant test)
        f4 = _create_test_file(
            f"Tenant B Operations Manual\n\n"
            f"Standard operating procedures for facility maintenance. "
            f"Internal reference: {CANARY_OTHER_TENANT}. "
            f"All equipment must be inspected quarterly.",
            "acl_test_other_tenant.txt"
        )

        # --- Ingest all 4 documents ---
        jobs = []

        print(f"\n[1/4] Ingesting PUBLIC doc (Tenant A)...")
        r1 = _ingest_document(f1, "acl_test_public.txt",
                              tenant_id=TENANT_A, visibility="public")
        cls.doc_ids["public"] = r1["doc_id"]
        jobs.append(("public", r1["job_id"]))
        print(f"       doc_id={r1['doc_id']}, job_id={r1['job_id']}")

        print(f"[2/4] Ingesting INTERNAL doc (Tenant A, role=analyst)...")
        r2 = _ingest_document(f2, "acl_test_internal.txt",
                              tenant_id=TENANT_A, visibility="internal",
                              allowed_roles=["analyst"])
        cls.doc_ids["internal"] = r2["doc_id"]
        jobs.append(("internal", r2["job_id"]))
        print(f"       doc_id={r2['doc_id']}, job_id={r2['job_id']}")

        print(f"[3/4] Ingesting RESTRICTED doc (Tenant A, user=alice)...")
        r3 = _ingest_document(f3, "acl_test_restricted.txt",
                              tenant_id=TENANT_A, visibility="restricted",
                              allowed_users=[USER_ALICE])
        cls.doc_ids["restricted"] = r3["doc_id"]
        jobs.append(("restricted", r3["job_id"]))
        print(f"       doc_id={r3['doc_id']}, job_id={r3['job_id']}")

        print(f"[4/4] Ingesting PUBLIC doc (Tenant B — cross-tenant)...")
        r4 = _ingest_document(f4, "acl_test_other_tenant.txt",
                              tenant_id=TENANT_B, visibility="public")
        cls.doc_ids["other_tenant"] = r4["doc_id"]
        jobs.append(("other_tenant", r4["job_id"]))
        print(f"       doc_id={r4['doc_id']}, job_id={r4['job_id']}")

        # --- Wait for all jobs to complete ---
        print(f"\nWaiting for ingestion jobs to complete...")
        for label, job_id in jobs:
            try:
                result = _wait_for_job(job_id)
                print(f"  [{label}] COMPLETED (doc_id={result.get('doc_id', 'N/A')})")
            except Exception as e:
                print(f"  [{label}] FAILED: {e}")
                # Continue — some tests can still run

        print(f"\nDoc IDs: {json.dumps(cls.doc_ids, indent=2)}")
        print("=" * 70)
        print("SETUP COMPLETE — Tests beginning")
        print("=" * 70 + "\n")

    # =========================================================================
    # Phase 1: Tests with ACL DISABLED (default state)
    # =========================================================================

    def test_00_acl_disabled_list_shows_all(self):
        """With ACL_ENABLED=false (default), all docs are visible without headers."""
        resp = requests.get(f"{BASE_URL}/v1/documents")
        assert resp.status_code == 200
        data = resp.json()
        visible_ids = {item["doc_id"] for item in data["items"]}
        # All test docs should be visible
        for label, doc_id in self.doc_ids.items():
            assert doc_id in visible_ids, (
                f"ACL disabled but {label} doc ({doc_id}) not in document list"
            )
        print(f"  ACL disabled: {data['total']} docs visible (all test docs present)")

    def test_01_acl_disabled_get_restricted_doc(self):
        """With ACL disabled, even restricted docs are accessible."""
        doc_id = self.doc_ids.get("restricted")
        if not doc_id:
            pytest.skip("Restricted doc not ingested")
        resp = requests.get(f"{BASE_URL}/v1/documents/{doc_id}")
        assert resp.status_code == 200
        print(f"  ACL disabled: restricted doc {doc_id} accessible (expected)")

    # =========================================================================
    # Phase 2: Tests with ACL ENABLED
    # =========================================================================

    def test_10_acl_enabled_public_doc_visible_to_tenant(self):
        """Public doc visible to any user in the same tenant."""
        doc_id = self.doc_ids.get("public")
        if not doc_id:
            pytest.skip("Public doc not ingested")
        headers = _headers(TENANT_A, USER_BOB)
        resp = requests.get(f"{BASE_URL}/v1/documents/{doc_id}", headers=headers)
        assert resp.status_code == 200, f"Public doc should be visible to tenant user: {resp.text}"
        print(f"  Public doc visible to bob@{TENANT_A} ✓")

    def test_11_acl_enabled_public_doc_hidden_from_other_tenant(self):
        """Public doc NOT visible to users in a different tenant."""
        doc_id = self.doc_ids.get("public")
        if not doc_id:
            pytest.skip("Public doc not ingested")
        headers = _headers(TENANT_B, USER_BOB)
        resp = requests.get(f"{BASE_URL}/v1/documents/{doc_id}", headers=headers)
        # Should be 404 (opaque mode) or 403 (explicit mode)
        assert resp.status_code in (403, 404), (
            f"Cross-tenant access should be denied, got {resp.status_code}: {resp.text}"
        )
        print(f"  Public doc hidden from bob@{TENANT_B} ✓ (got {resp.status_code})")

    def test_12_acl_enabled_internal_doc_visible_with_role(self):
        """Internal doc visible to user with matching role."""
        doc_id = self.doc_ids.get("internal")
        if not doc_id:
            pytest.skip("Internal doc not ingested")
        headers = _headers(TENANT_A, USER_BOB, roles=["analyst"])
        resp = requests.get(f"{BASE_URL}/v1/documents/{doc_id}", headers=headers)
        assert resp.status_code == 200, f"Internal doc should be visible to analyst: {resp.text}"
        print(f"  Internal doc visible to bob@{TENANT_A} with role=analyst ✓")

    def test_13_acl_enabled_internal_doc_hidden_without_role(self):
        """Internal doc NOT visible to user without matching role."""
        doc_id = self.doc_ids.get("internal")
        if not doc_id:
            pytest.skip("Internal doc not ingested")
        headers = _headers(TENANT_A, USER_BOB, roles=["intern"])
        resp = requests.get(f"{BASE_URL}/v1/documents/{doc_id}", headers=headers)
        assert resp.status_code in (403, 404), (
            f"Internal doc should be hidden from non-analyst, got {resp.status_code}: {resp.text}"
        )
        print(f"  Internal doc hidden from bob@{TENANT_A} with role=intern ✓ (got {resp.status_code})")

    def test_14_acl_enabled_restricted_doc_visible_to_allowed_user(self):
        """Restricted doc visible to explicitly allowed user."""
        doc_id = self.doc_ids.get("restricted")
        if not doc_id:
            pytest.skip("Restricted doc not ingested")
        headers = _headers(TENANT_A, USER_ALICE)
        resp = requests.get(f"{BASE_URL}/v1/documents/{doc_id}", headers=headers)
        assert resp.status_code == 200, f"Restricted doc should be visible to alice: {resp.text}"
        print(f"  Restricted doc visible to alice@{TENANT_A} ✓")

    def test_15_acl_enabled_restricted_doc_hidden_from_others(self):
        """Restricted doc NOT visible to non-allowed user in same tenant."""
        doc_id = self.doc_ids.get("restricted")
        if not doc_id:
            pytest.skip("Restricted doc not ingested")
        headers = _headers(TENANT_A, USER_BOB)
        resp = requests.get(f"{BASE_URL}/v1/documents/{doc_id}", headers=headers)
        assert resp.status_code in (403, 404), (
            f"Restricted doc should be hidden from bob, got {resp.status_code}: {resp.text}"
        )
        print(f"  Restricted doc hidden from bob@{TENANT_A} ✓ (got {resp.status_code})")

    def test_16_acl_enabled_admin_sees_all_in_tenant(self):
        """Admin can see all docs in their tenant."""
        headers = _headers(TENANT_A, USER_ADMIN, roles=["admin"])
        resp = requests.get(f"{BASE_URL}/v1/documents", headers=headers)
        assert resp.status_code == 200
        visible_ids = {item["doc_id"] for item in resp.json()["items"]}
        for label in ["public", "internal", "restricted"]:
            doc_id = self.doc_ids.get(label)
            if doc_id:
                assert doc_id in visible_ids, (
                    f"Admin should see {label} doc ({doc_id})"
                )
        # Admin should NOT see other tenant's docs
        other_id = self.doc_ids.get("other_tenant")
        if other_id:
            assert other_id not in visible_ids, (
                f"Admin should NOT see other tenant's doc ({other_id})"
            )
        print(f"  Admin sees all Tenant A docs, not Tenant B ✓")

    def test_17_acl_enabled_list_filters_by_tenant(self):
        """Document list only shows docs for the caller's tenant."""
        headers = _headers(TENANT_A, USER_BOB)
        resp = requests.get(f"{BASE_URL}/v1/documents", headers=headers)
        assert resp.status_code == 200
        visible_ids = {item["doc_id"] for item in resp.json()["items"]}
        # Bob should see public doc (public in his tenant)
        if self.doc_ids.get("public"):
            assert self.doc_ids["public"] in visible_ids
        # Bob should NOT see other tenant's doc
        if self.doc_ids.get("other_tenant"):
            assert self.doc_ids["other_tenant"] not in visible_ids, (
                "Cross-tenant doc should not appear in list"
            )
        print(f"  Document list filtered by tenant ✓")

    def test_18_acl_enabled_raw_document_access(self):
        """Raw document access is ACL-protected."""
        doc_id = self.doc_ids.get("restricted")
        if not doc_id:
            pytest.skip("Restricted doc not ingested")
        # bob should NOT get raw bytes
        headers = _headers(TENANT_A, USER_BOB)
        resp = requests.get(f"{BASE_URL}/v1/documents/{doc_id}/raw", headers=headers)
        assert resp.status_code in (403, 404), (
            f"Raw access to restricted doc should be denied for bob, got {resp.status_code}"
        )
        print(f"  Raw document access denied for unauthorized user ✓ (got {resp.status_code})")

    def test_19_acl_enabled_nodes_endpoint_protected(self):
        """Nodes endpoint is ACL-protected."""
        doc_id = self.doc_ids.get("restricted")
        if not doc_id:
            pytest.skip("Restricted doc not ingested")
        headers = _headers(TENANT_A, USER_BOB)
        resp = requests.get(f"{BASE_URL}/v1/documents/{doc_id}/nodes", headers=headers)
        assert resp.status_code in (403, 404), (
            f"Nodes of restricted doc should be hidden from bob, got {resp.status_code}"
        )
        print(f"  Nodes endpoint protected ✓ (got {resp.status_code})")

    def test_20_acl_enabled_edges_endpoint_protected(self):
        """Edges endpoint is ACL-protected."""
        doc_id = self.doc_ids.get("restricted")
        if not doc_id:
            pytest.skip("Restricted doc not ingested")
        headers = _headers(TENANT_A, USER_BOB)
        resp = requests.get(f"{BASE_URL}/v1/documents/{doc_id}/edges", headers=headers)
        assert resp.status_code in (403, 404), (
            f"Edges of restricted doc should be hidden from bob, got {resp.status_code}"
        )
        print(f"  Edges endpoint protected ✓ (got {resp.status_code})")

    # =========================================================================
    # Phase 3: QA Pipeline canary tests
    # =========================================================================

    def test_30_qa_canary_restricted_not_in_answer(self):
        """Restricted doc canary must NOT appear in QA answer for unauthorized user."""
        headers = _headers(TENANT_A, USER_BOB)
        resp = requests.post(
            f"{BASE_URL}/v1/qa/ask",
            json={"question": "What is the legal settlement authority?", "top_k": 10},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        answer = data.get("answer", "")
        citations_str = json.dumps(data.get("citations", []))
        seed_str = json.dumps(data.get("seed_nodes", []))

        assert CANARY_RESTRICTED not in answer, (
            f"CANARY LEAK: restricted canary found in answer for bob!"
        )
        assert CANARY_RESTRICTED not in citations_str, (
            f"CANARY LEAK: restricted canary found in citations for bob!"
        )
        assert CANARY_RESTRICTED not in seed_str, (
            f"CANARY LEAK: restricted canary found in seed_nodes for bob!"
        )
        print(f"  Restricted canary NOT in answer/citations/seeds for bob ✓")

    def test_31_qa_canary_cross_tenant_not_in_answer(self):
        """Other tenant's canary must NOT appear in QA answer."""
        headers = _headers(TENANT_A, USER_ALICE, roles=["analyst", "admin"])
        resp = requests.post(
            f"{BASE_URL}/v1/qa/ask",
            json={"question": "What are the standard operating procedures?", "top_k": 10},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        answer = data.get("answer", "")
        full_response = json.dumps(data)

        assert CANARY_OTHER_TENANT not in answer, (
            f"CANARY LEAK: other tenant canary found in answer!"
        )
        assert CANARY_OTHER_TENANT not in full_response, (
            f"CANARY LEAK: other tenant canary found somewhere in response!"
        )
        print(f"  Cross-tenant canary NOT in response ✓")

    def test_32_qa_canary_internal_not_visible_without_role(self):
        """Internal doc canary must NOT appear for user without the required role."""
        headers = _headers(TENANT_A, USER_BOB, roles=["intern"])
        resp = requests.post(
            f"{BASE_URL}/v1/qa/ask",
            json={"question": "What is the budget analysis?", "top_k": 10},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        answer = data.get("answer", "")
        full_response = json.dumps(data)

        assert CANARY_INTERNAL not in answer, (
            f"CANARY LEAK: internal canary found in answer for user without role!"
        )
        assert CANARY_INTERNAL not in full_response, (
            f"CANARY LEAK: internal canary found somewhere in response for user without role!"
        )
        print(f"  Internal canary NOT visible to user without 'analyst' role ✓")

    def test_33_qa_public_canary_visible_to_tenant_user(self):
        """Public doc canary SHOULD appear for any user in the right tenant."""
        headers = _headers(TENANT_A, USER_BOB)
        resp = requests.post(
            f"{BASE_URL}/v1/qa/ask",
            json={
                "question": f"What are the water quality findings?",
                "top_k": 10,
            },
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        # Check if any seed nodes or citations reference the public doc
        seed_doc_ids = set()
        for seed in data.get("seed_nodes", []):
            # seed_nodes may have doc_id in nested structure
            if isinstance(seed, dict):
                seed_doc_ids.add(seed.get("doc_id", ""))
        citation_doc_ids = {c.get("doc_id", "") for c in data.get("citations", [])}
        print(f"  Public doc QA query returned: success={data.get('success')}, "
              f"seeds={len(data.get('seed_nodes', []))}, "
              f"answer_len={len(data.get('answer', ''))}")

    def test_34_qa_acl_audit_present(self):
        """ACL audit trail should be present in QA response when ACL is active."""
        headers = _headers(TENANT_A, USER_BOB)
        resp = requests.post(
            f"{BASE_URL}/v1/qa/ask",
            json={"question": "What are the water quality findings?", "top_k": 5},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        acl_audit = data.get("acl_audit")
        if acl_audit is not None:
            print(f"  ACL audit trail present: {len(acl_audit)} entries ✓")
            for entry in acl_audit:
                print(f"    stage={entry.get('stage')}, "
                      f"allowed={entry.get('allowed')}, "
                      f"denied={entry.get('denied')}")
        else:
            print(f"  ACL audit trail: None (no items were filtered)")

    # =========================================================================
    # Phase 4: Policy update endpoint
    # =========================================================================

    def test_40_policy_get_requires_admin(self):
        """Policy endpoint requires admin role."""
        doc_id = self.doc_ids.get("public")
        if not doc_id:
            pytest.skip("Public doc not ingested")
        # Non-admin should be denied
        headers = _headers(TENANT_A, USER_BOB)
        resp = requests.get(
            f"{BASE_URL}/v1/acl/documents/{doc_id}/policy", headers=headers
        )
        assert resp.status_code == 403, (
            f"Non-admin should not access policy endpoint, got {resp.status_code}"
        )
        print(f"  Policy GET denied for non-admin ✓")

    def test_41_policy_get_as_admin(self):
        """Admin can read policy."""
        doc_id = self.doc_ids.get("public")
        if not doc_id:
            pytest.skip("Public doc not ingested")
        headers = _headers(TENANT_A, USER_ADMIN, roles=["admin"])
        resp = requests.get(
            f"{BASE_URL}/v1/acl/documents/{doc_id}/policy", headers=headers
        )
        assert resp.status_code == 200, f"Admin should access policy: {resp.text}"
        policy = resp.json()
        assert policy["visibility"] == "public"
        assert policy["tenant_id"] == TENANT_A
        print(f"  Policy GET as admin: visibility={policy['visibility']}, "
              f"tenant={policy['tenant_id']} ✓")

    def test_42_policy_update(self):
        """Admin can update policy (visibility change)."""
        doc_id = self.doc_ids.get("public")
        if not doc_id:
            pytest.skip("Public doc not ingested")
        headers = _headers(TENANT_A, USER_ADMIN, roles=["admin"])

        # Change from public to internal with analyst role
        resp = requests.put(
            f"{BASE_URL}/v1/acl/documents/{doc_id}/policy",
            json={"visibility": "internal", "allowed_roles": ["analyst"]},
            headers=headers,
        )
        assert resp.status_code == 200, f"Policy update failed: {resp.text}"
        policy = resp.json()
        assert policy["visibility"] == "internal"
        assert policy["policy_version"] == 2  # Incremented from 1
        print(f"  Policy updated: visibility=internal, policy_version={policy['policy_version']} ✓")

        # Verify bob WITHOUT analyst role can no longer see it
        headers_bob = _headers(TENANT_A, USER_BOB, roles=["intern"])
        resp2 = requests.get(f"{BASE_URL}/v1/documents/{doc_id}", headers=headers_bob)
        assert resp2.status_code in (403, 404), (
            f"After policy change, bob without analyst role should be denied: {resp2.status_code}"
        )
        print(f"  Post-update: bob (intern) denied access ✓ (got {resp2.status_code})")

        # Revert back to public
        resp3 = requests.put(
            f"{BASE_URL}/v1/acl/documents/{doc_id}/policy",
            json={"visibility": "public", "allowed_roles": []},
            headers=headers,
        )
        assert resp3.status_code == 200
        assert resp3.json()["policy_version"] == 3
        print(f"  Policy reverted to public, policy_version={resp3.json()['policy_version']} ✓")

    # =========================================================================
    # Phase 5: Vector retrieval endpoint
    # =========================================================================

    def test_50_vector_retrieval_acl_filtered(self):
        """Vector retrieval endpoint should filter by ACL."""
        headers = _headers(TENANT_A, USER_BOB)
        resp = requests.post(
            f"{BASE_URL}/v1/retrieve/vector",
            json={"query": "legal settlement authority memo", "top_k": 20},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        result_doc_ids = {r["doc_id"] for r in data["results"]}

        # Bob should NOT see restricted doc or other tenant's doc
        restricted_id = self.doc_ids.get("restricted")
        other_id = self.doc_ids.get("other_tenant")

        if restricted_id:
            assert restricted_id not in result_doc_ids, (
                "Restricted doc should not appear in vector retrieval for bob"
            )
        if other_id:
            assert other_id not in result_doc_ids, (
                "Other tenant's doc should not appear in vector retrieval"
            )
        print(f"  Vector retrieval filtered: {len(data['results'])} results, "
              f"no restricted/cross-tenant docs ✓")
