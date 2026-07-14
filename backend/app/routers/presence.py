"""在线协作（presence）WebSocket。

- /ws/presence?doc={doc_id}&token={jwt}
- 连接即注册为「正在编辑该文档」；断开自动移除。
- 客户端可发送 {type:"cursor", cursor:{row,col}} 广播自己的光标位置。
- 服务端向同房间的所有连接广播 {type:"presence", users:[{id,name,color,cursor}]}。

在线状态用于「多人同时在线」感知；配合 /save_rows 的版本冲突检测实现防覆盖保存。
"""
import json
import time
from typing import Any, Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.database import SessionLocal
from app.core.security import decode_token
from app.models.rbac import User

router = APIRouter()

# 用户 id -> 颜色（远程光标/头像配色）
_COLORS = [
    "#ef4444", "#f59e0b", "#10b981", "#3b82f6",
    "#8b5cf6", "#ec4899", "#14b8a6", "#f97316",
]


def _color_for(uid: int) -> str:
    return _COLORS[uid % len(_COLORS)]


class _Presence:
    def __init__(self) -> None:
        # doc_id -> { user_id: {ws, name, color, cursor, last} }
        self.docs: dict[int, dict[int, dict[str, Any]]] = {}

    def add(self, doc_id: int, user: User, ws: WebSocket) -> None:
        self.docs.setdefault(doc_id, {})[user.id] = {
            "ws": ws,
            "name": user.username,
            "color": _color_for(user.id),
            "cursor": None,
            "last": time.time(),
        }

    def remove(self, doc_id: int, user_id: int) -> None:
        room = self.docs.get(doc_id)
        if room and user_id in room:
            del room[user_id]
        if room and not room:
            self.docs.pop(doc_id, None)

    def set_cursor(self, doc_id: int, user_id: int, cursor: Optional[dict]) -> None:
        room = self.docs.get(doc_id)
        entry = room.get(user_id) if room else None
        if entry:
            entry["cursor"] = cursor
            entry["last"] = time.time()

    def snapshot(self, doc_id: int) -> list[dict]:
        room = self.docs.get(doc_id, {})
        return [
            {"id": uid, "name": v["name"], "color": v["color"], "cursor": v["cursor"]}
            for uid, v in room.items()
        ]

    async def broadcast(self, doc_id: int) -> None:
        msg = json.dumps({"type": "presence", "users": self.snapshot(doc_id)})
        room = self.docs.get(doc_id, {})
        for v in list(room.values()):
            try:
                await v["ws"].send_text(msg)
            except Exception:
                pass


_pm = _Presence()


@router.websocket("/ws/presence")
async def ws_presence(
    websocket: WebSocket,
    doc_id: int = Query(...),
    token: str = Query(...),
):
    # 鉴权
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            await websocket.close(code=1008)
            return
        user_id = int(payload["sub"])
    except Exception:
        await websocket.close(code=1008)
        return

    db = SessionLocal()
    try:
        user = db.get(User, user_id)
    finally:
        db.close()
    if user is None or not user.is_active:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    _pm.add(doc_id, user, websocket)
    await _pm.broadcast(doc_id)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            if msg.get("type") in ("cursor", "ping"):
                _pm.set_cursor(doc_id, user.id, msg.get("cursor"))
                await _pm.broadcast(doc_id)
    except WebSocketDisconnect:
        _pm.remove(doc_id, user.id)
        await _pm.broadcast(doc_id)
    except Exception:
        _pm.remove(doc_id, user.id)
        try:
            await _pm.broadcast(doc_id)
        except Exception:
            pass
