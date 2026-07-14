"""首次启动种子数据：建表 + 权限 + 角色 + 超级管理员。

幂等：已存在超级管理员则跳过。
"""
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import Base, engine
from app.core.security import hash_password
from app.models.document import Document
from app.models.rbac import Permission, Role, User

# (codename, 描述, 资源类型)
PERMISSIONS = [
    ("user:read", "查看用户", "api"),
    ("user:create", "创建用户", "api"),
    ("user:update", "修改用户", "api"),
    ("user:delete", "删除用户", "api"),
    ("role:read", "查看角色与权限", "api"),
    ("role:manage", "管理角色权限", "api"),
    ("sheet:create", "创建表格", "sheet"),
    ("sheet:read", "查看表格", "sheet"),
    ("sheet:update", "编辑表格", "sheet"),
    ("sheet:delete", "删除表格", "sheet"),
    ("project:read", "查看项目数据", "api"),
    ("statistics:read", "查看统计", "api"),
    ("page:admin", "管理后台页面", "page"),
    ("page:sheet", "表格编辑页面", "page"),
]

# 角色 -> 权限编码集合
ROLE_PERMS = {
    "superadmin": {p[0] for p in PERMISSIONS},
    "admin": {
        "user:read", "user:create", "user:update", "user:delete",
        "role:read", "role:manage",
        "sheet:create", "sheet:read", "sheet:update", "sheet:delete",
        "project:read", "statistics:read",
        "page:admin", "page:sheet",
    },
    "project_manager": {
        "sheet:read", "sheet:update",
        "project:read", "statistics:read", "page:sheet",
    },
    "employee": {"sheet:read", "sheet:update", "page:sheet"},
    "guest": {"sheet:read", "project:read", "statistics:read", "page:sheet"},
}

ROLE_DESC = {
    "superadmin": "超级管理员（全部权限）",
    "admin": "管理员（用户/表格管理）",
    "project_manager": "项目负责人（指定项目数据）",
    "employee": "普通员工（授权数据编辑）",
    "guest": "访客（只读）",
}


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def seed(db: Session) -> None:
    init_db()

    # 权限
    perm_map: dict[str, Permission] = {}
    for name, desc, rtype in PERMISSIONS:
        perm = db.query(Permission).filter(Permission.name == name).first()
        if perm is None:
            perm = Permission(name=name, description=desc, resource_type=rtype)
            db.add(perm)
            db.flush()
        perm_map[name] = perm

    # 角色
    role_map: dict[str, Role] = {}
    for role_name, perm_set in ROLE_PERMS.items():
        role = db.query(Role).filter(Role.name == role_name).first()
        if role is None:
            role = Role(name=role_name, description=ROLE_DESC.get(role_name))
            db.add(role)
            db.flush()
        role.permissions = [perm_map[p] for p in perm_set if p in perm_map]
        role_map[role_name] = role

    # 超级管理员
    admin = (
        db.query(User)
        .filter(User.username == settings.SUPERADMIN_USERNAME)
        .first()
    )
    if admin is None:
        admin = User(
            username=settings.SUPERADMIN_USERNAME,
            email=settings.SUPERADMIN_EMAIL,
            hashed_password=hash_password(settings.SUPERADMIN_PASSWORD),
            is_active=True,
        )
        admin.roles.append(role_map["superadmin"])
        db.add(admin)

    db.flush()  # 确保 admin.id 已生成

    # 示例文档（幂等）：一个项目文件夹 + 一张普通表格 + 一张结构化焊接库
    folder = (
        db.query(Document)
        .filter(Document.name == "焊接数据库", Document.owner_id == admin.id)
        .first()
    )
    if folder is None:
        folder = Document(
            name="焊接数据库", is_folder=True, owner_id=admin.id, project_id="A"
        )
        db.add(folder)
        db.flush()

    if (
        db.query(Document)
        .filter(Document.name == "管线焊口记录表", Document.owner_id == admin.id)
        .first()
        is None
    ):
        db.add(
            Document(
                name="管线焊口记录表",
                is_folder=False,
                owner_id=admin.id,
                parent_id=folder.id,
                project_id="A",
            )
        )

    # 结构化焊接库（与大屏同源，数据由迁移脚本 / Excel 导入填充）
    if (
        db.query(Document)
        .filter(Document.name == "尿素信华焊接数据库", Document.owner_id == admin.id)
        .first()
        is None
    ):
        db.add(
            Document(
                name="尿素信华焊接数据库",
                is_folder=False,
                doc_type="welding_db",
                owner_id=admin.id,
                parent_id=folder.id,
                project_id="A",
            )
        )

    db.commit()


if __name__ == "__main__":
    from app.core.database import SessionLocal

    with SessionLocal() as s:
        seed(s)
    print("Seed 完成。")
