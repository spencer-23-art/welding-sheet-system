"""行级数据权限作用域。

规则：
- 超级管理员(superadmin 角色 / SUPERADMIN_USERNAME) 拥有全部数据，不受任何限制。
- 普通用户：
  - assigned_projects 非空时，仅可访问 project_id 在该列表中的文档/数据；为空则不限制项目。
  - assigned_zones 非空时，仅可见/可改 zone_code 在该列表中的行；为空则不限制装置区。
- 两者可同时生效：先按项目过滤文档，再按装置区过滤行。
"""
from app.core.config import settings
from app.models.rbac import User

# 视为「拥有全部权限」的角色
_ADMIN_ROLES = {"admin", "superadmin"}


class DataScope:
    def __init__(self, is_admin: bool, project_ids: list, zone_codes: list):
        self.is_admin = is_admin
        self.project_ids = [str(p) for p in (project_ids or [])]
        self.zone_codes = [str(z) for z in (zone_codes or [])]

    @property
    def has_project_filter(self) -> bool:
        return bool(self.project_ids)

    @property
    def has_zone_filter(self) -> bool:
        return bool(self.zone_codes)

    def can_access_project(self, project_id: str | None) -> bool:
        if self.is_admin:
            return True
        if not self.project_ids:
            return True
        return (project_id or "") in self.project_ids

    def allows_zone(self, zone_code: str | None) -> bool:
        if self.is_admin:
            return True
        if not self.zone_codes:
            return True
        return (zone_code or "") in self.zone_codes


def get_data_scope(user: User) -> DataScope:
    is_admin = user.username == settings.SUPERADMIN_USERNAME or any(
        r.name in _ADMIN_ROLES for r in user.roles
    )
    projects = user.assigned_projects
    zones = user.assigned_zones
    if isinstance(projects, str):
        projects = [projects]
    if isinstance(zones, str):
        zones = [zones]
    return DataScope(is_admin, projects or [], zones or [])
