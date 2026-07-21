"""阶段一冒烟测试：用 TestClient 对 SQLite 模式跑通注册/登录/RBAC。"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"
if os.path.exists("test.db"):
    os.remove("test.db")

from fastapi.testclient import TestClient
from app.main import app

with TestClient(app) as client:
    # 1. 健康检查
    r = client.get("/health")
    assert r.status_code == 200, r.text
    print("[OK] /health")

    # 2. 超级管理员已 seed
    r = client.post("/api/login", json={"account": "admin", "password": "Admin@123456"})
    assert r.status_code == 200, r.text
    admin_token = r.json()["access_token"]
    print("[OK] 超级管理员登录")
    headers = {"Authorization": f"Bearer {admin_token}"}

    # 3. 当前用户
    r = client.get("/api/me", headers=headers)
    assert r.status_code == 200 and r.json()["username"] == "admin"
    print("[OK] /api/me")

    # 4. 角色与权限列表
    r = client.get("/api/roles", headers=headers)
    assert r.status_code == 200 and len(r.json()) >= 5
    print(f"[OK] /api/roles 数量={len(r.json())}")
    r = client.get("/api/permissions", headers=headers)
    assert r.status_code == 200 and len(r.json()) >= 10
    print(f"[OK] /api/permissions 数量={len(r.json())}")

    # 5. 开放注册（默认 employee）
    r = client.post("/api/register", json={
        "username": "zhangsan", "password": "Test@123", "phone": "13800000001"
    })
    assert r.status_code == 201, r.text
    print("[OK] 开放注册 zhangsan (employee)")

    # 6. 员工登录并验证只有 sheet 权限
    r = client.post("/api/login", json={"account": "zhangsan", "password": "Test@123"})
    zhang_token = r.json()["access_token"]
    zh = {"Authorization": f"Bearer {zhang_token}"}
    r = client.get("/api/users", headers=zh)
    assert r.status_code == 403, "员工不应能查看用户列表"
    print("[OK] 员工访问 /api/users 被 RBAC 拦截(403)")

    # 7. 管理员创建用户并分配角色
    r = client.post("/api/users", headers=headers, json={
        "username": "manager1", "password": "Test@123",
        "email": "m1@example.com", "role_names": ["project_manager"]
    })
    assert r.status_code == 201, r.text
    assert any(role["name"] == "project_manager" for role in r.json()["roles"])
    print("[OK] 管理员创建 manager1(project_manager)")

    # 8. 管理员查看用户列表
    r = client.get("/api/users", headers=headers)
    assert r.status_code == 200 and len(r.json()) >= 3
    print(f"[OK] /api/users 数量={len(r.json())}")

    # 9. 禁用用户（非超级管理员）
    uid = r.json()[1]["id"]
    r = client.patch(f"/api/users/{uid}", headers=headers, json={"is_active": False})
    assert r.status_code == 200 and r.json()["is_active"] is False
    print("[OK] 禁用用户")

    # 10. 保护超级管理员
    r = client.patch("/api/users/1", headers=headers, json={"is_active": False})
    assert r.status_code == 403, "应禁止禁用超级管理员"
    print("[OK] 保护超级管理员(403)")

    # ===== 第二阶段：文档管理与表格保存/加载 =====
    # 11. 根目录列表应包含 seed 的示例文件夹（parent_id 省略=查根）
    r = client.get("/api/documents", headers=headers)
    assert r.status_code == 200, r.text
    names = [d["name"] for d in r.json()]
    assert "焊接数据库" in names, f"缺少示例文件夹, got {names}"
    print(f"[OK] 根目录文档列表 数量={len(r.json())} 含示例文件夹")

    # 12. 创建文件夹
    r = client.post("/api/documents", headers=headers,
                    json={"name": "项目B", "is_folder": True, "project_id": "B"})
    assert r.status_code == 201, r.text
    folder_b = r.json()
    print("[OK] 创建文件夹 项目B")

    # 13. 在文件夹下创建表格
    r = client.post("/api/documents", headers=headers, json={
        "name": "焊口台账", "is_folder": False,
        "parent_id": folder_b["id"], "project_id": "B"})
    assert r.status_code == 201, r.text
    sheet = r.json()
    assert sheet["has_data"] is False
    print("[OK] 创建表格 焊口台账")

    # 14. 获取表格元信息（本地 Univer workbook 接口已下线）
    r = client.get(f"/api/sheets/{sheet['id']}", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["id"] == sheet["id"]
    assert r.json()["name"] == "焊口台账"
    assert r.json()["record_count"] == 0
    print("[OK] 获取表格元信息")

    # 15. 重命名表格
    r = client.patch(f"/api/documents/{sheet['id']}", headers=headers,
                     json={"name": "焊口台账V2"})
    assert r.status_code == 200 and r.json()["name"] == "焊口台账V2"
    print("[OK] 重命名表格")

    # 16. 软删除表格（普通列表不可见）
    r = client.delete(f"/api/documents/{sheet['id']}", headers=headers)
    assert r.status_code == 204, r.text
    r = client.get(f"/api/documents?parent_id={folder_b['id']}", headers=headers)
    assert all(d["id"] != sheet["id"] for d in r.json())
    print("[OK] 软删除表格")

    # 17. 回收站可见 + 恢复
    r = client.get(f"/api/documents?parent_id={folder_b['id']}&include_deleted=true",
                   headers=headers)
    assert any(d["id"] == sheet["id"] and d["is_deleted"] for d in r.json())
    r = client.post(f"/api/documents/{sheet['id']}/restore", headers=headers)
    assert r.status_code == 200 and r.json()["is_deleted"] is False
    print("[OK] 回收站可见并恢复表格")

    # 18. 搜索
    r = client.get("/api/documents?q=焊口", headers=headers)
    assert any("焊口" in d["name"] for d in r.json())
    print("[OK] 搜索文档")

    # 19. 员工无 sheet:create 权限应被拦截（employee 仅有 read/update）
    r = client.post("/api/documents", headers=zh,
                    json={"name": "不应创建", "is_folder": False})
    assert r.status_code == 403, "员工无 sheet:create 应被拦截"
    print("[OK] 员工创建表格被 RBAC 拦截(403)")

print("\n=== 阶段一 + 阶段二 后端冒烟测试全部通过 ===")
