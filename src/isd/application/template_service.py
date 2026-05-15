from __future__ import annotations

from dataclasses import dataclass

from isd.application.ids import make_id, utc_now
from isd.domain.enums import TemplateScope
from isd.domain.models import ApiResponse, ErrorBody, Template
from isd.infrastructure.repositories.template_repository import TemplateRepository


@dataclass
class TemplateService:
    template_repo: TemplateRepository

    def list_templates(self, payload: dict) -> ApiResponse[list[dict]]:
        scope_text = (payload.get("scope") or "").strip().upper()
        if scope_text:
            scope = TemplateScope(scope_text)
            rows = self.template_repo.list_by_scope(scope.value)
        else:
            rows = self.template_repo.list_all()
        return ApiResponse(success=True, data=[row.model_dump(mode="json") for row in rows])

    def get_template(self, payload: dict) -> ApiResponse[dict]:
        template_id = str(payload.get("templateId") or "").strip()
        if not template_id:
            return ApiResponse(
                success=False,
                error=ErrorBody(code="MISSING_TEMPLATE_ID", message="templateId is required"),
            )
        row = self.template_repo.get(template_id)
        if not row:
            return ApiResponse(
                success=False,
                error=ErrorBody(code="TEMPLATE_NOT_FOUND", message="Template not found"),
            )
        return ApiResponse(success=True, data=row.model_dump(mode="json"))

    def save_template(self, payload: dict) -> ApiResponse[dict]:
        name = str(payload.get("name") or "").strip()
        scope_text = str(payload.get("scope") or "TASK").strip().upper()
        description = payload.get("description")
        template_payload = payload.get("payload") or {}
        overwrite_strategy = str(payload.get("overwriteStrategy") or "OVERWRITE").strip().upper()
        requested_id = str(payload.get("templateId") or "").strip() or None

        if not name:
            return ApiResponse(
                success=False,
                error=ErrorBody(code="MISSING_TEMPLATE_NAME", message="name is required"),
            )

        try:
            scope = TemplateScope(scope_text)
        except ValueError:
            return ApiResponse(
                success=False,
                error=ErrorBody(code="INVALID_TEMPLATE_SCOPE", message=f"Unsupported scope: {scope_text}"),
            )

        existing = self.template_repo.find_by_scope_name(scope.value, name)
        if requested_id:
            row = self.template_repo.get(requested_id)
            if row:
                existing = row

        if existing and overwrite_strategy == "REJECT":
            return ApiResponse(
                success=False,
                error=ErrorBody(
                    code="TEMPLATE_EXISTS",
                    message=f"Template already exists for scope/name: {scope.value}/{name}",
                ),
            )

        if existing and overwrite_strategy == "CREATE_NEW":
            template_id = make_id("tpl")
            actual_name = f"{name}_{utc_now().replace(':', '').replace('-', '')}"
            created_at = utc_now()
        elif existing:
            template_id = existing.id
            actual_name = name
            created_at = existing.created_at
        else:
            template_id = requested_id or make_id("tpl")
            actual_name = name
            created_at = utc_now()

        row = Template(
            id=template_id,
            name=actual_name,
            description=description,
            scope=scope,
            is_default=bool(payload.get("isDefault", False)),
            payload=template_payload,
            created_at=created_at,
            updated_at=utc_now(),
        )
        saved = self.template_repo.upsert(row)
        return ApiResponse(success=True, data=saved.model_dump(mode="json"))

    def delete_template(self, payload: dict) -> ApiResponse[dict]:
        template_id = str(payload.get("templateId") or "").strip()
        if not template_id:
            return ApiResponse(
                success=False,
                error=ErrorBody(code="MISSING_TEMPLATE_ID", message="templateId is required"),
            )
        deleted = self.template_repo.delete(template_id)
        if not deleted:
            return ApiResponse(
                success=False,
                error=ErrorBody(code="TEMPLATE_NOT_FOUND", message="Template not found"),
            )
        return ApiResponse(success=True, data={"templateId": template_id, "deleted": True})
