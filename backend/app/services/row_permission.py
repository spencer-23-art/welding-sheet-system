"""Project-level data access scopes."""
from app.core.config import settings
from app.models.rbac import User

_ADMIN_ROLES = {"admin", "superadmin"}


class DataScope:
    def __init__(self, is_admin: bool, project_ids: list, zone_codes: list):
        self.is_admin = is_admin
        self.project_ids = [str(project) for project in (project_ids or [])]
        # Retained as scope data for compatibility with existing user records.
        self.zone_codes = [str(zone) for zone in (zone_codes or [])]

    def can_access_project(self, project_id: str | None) -> bool:
        if self.is_admin or not self.project_ids:
            return True
        return (project_id or "") in self.project_ids


def get_data_scope(user: User) -> DataScope:
    is_admin = user.username == settings.SUPERADMIN_USERNAME or any(
        role.name in _ADMIN_ROLES for role in user.roles
    )
    projects = user.assigned_projects
    zones = user.assigned_zones
    if isinstance(projects, str):
        projects = [projects]
    if isinstance(zones, str):
        zones = [zones]
    return DataScope(is_admin, projects or [], zones or [])
