"""WebSocket 알림 매니저

실시간 알림을 위한 WebSocket 연결 관리 및 메시지 브로드캐스트.
Celery 태스크에서도 호출 가능하도록 sync/async 양쪽 지원.
"""
import json
import asyncio
import logging
from datetime import datetime
from typing import Optional
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class NotificationManager:
    """WebSocket 연결을 관리하고 알림을 브로드캐스트합니다."""

    def __init__(self):
        # 활성 WebSocket 연결 {user_id: [websocket, ...]}
        self._connections: dict[str, list[WebSocket]] = {}
        # 알림 히스토리 (인메모리, 향후 Redis/DB로 전환)
        self._notification_history: list[dict] = []
        self._max_history = 100

    # ==============================
    # 연결 관리
    # ==============================
    async def connect(self, websocket: WebSocket, user_id: str = "default"):
        """WebSocket 연결을 수락하고 등록합니다."""
        await websocket.accept()
        if user_id not in self._connections:
            self._connections[user_id] = []
        self._connections[user_id].append(websocket)

        logger.info(f"WebSocket 연결: user={user_id} (총 {self.active_count}개)")

        # 연결 시 미읽은 알림 전송
        unread = [n for n in self._notification_history if not n.get("read")]
        if unread:
            await websocket.send_json({
                "type": "unread_notifications",
                "data": unread[-10:],  # 최근 10개만
                "count": len(unread),
            })

    async def disconnect(self, websocket: WebSocket, user_id: str = "default"):
        """WebSocket 연결을 해제합니다."""
        if user_id in self._connections:
            self._connections[user_id] = [
                ws for ws in self._connections[user_id] if ws != websocket
            ]
            if not self._connections[user_id]:
                del self._connections[user_id]

        logger.info(f"WebSocket 해제: user={user_id} (남은 연결: {self.active_count}개)")

    @property
    def active_count(self) -> int:
        """활성 연결 수"""
        return sum(len(conns) for conns in self._connections.values())

    # ==============================
    # 메시지 전송
    # ==============================
    async def broadcast(self, message: dict, user_id: str = None):
        """모든 연결(또는 특정 사용자)에게 메시지를 브로드캐스트합니다."""
        # 히스토리에 저장
        self._add_to_history(message)

        targets = (
            {user_id: self._connections.get(user_id, [])} if user_id
            else self._connections
        )

        disconnected = []
        sent_count = 0

        for uid, connections in targets.items():
            for ws in connections:
                try:
                    await ws.send_json(message)
                    sent_count += 1
                except Exception as e:
                    logger.warning(f"WebSocket 전송 실패 (user={uid}): {e}")
                    disconnected.append((uid, ws))

        # 끊어진 연결 정리
        for uid, ws in disconnected:
            await self.disconnect(ws, uid)

        logger.info(f"브로드캐스트: {sent_count}개 연결에 전송 완료")

    def broadcast_sync(self, message: dict, user_id: str = None):
        """Celery 태스크 등 동기 컨텍스트에서 호출 가능한 브로드캐스트.
        
        실행 중인 이벤트 루프가 없으면 히스토리에만 저장하고,
        다음 WebSocket 폴링 시 전달됩니다.
        """
        self._add_to_history(message)

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.broadcast(message, user_id))
        except RuntimeError:
            # 이벤트 루프 없음 (Celery worker 등)
            # → 히스토리에 저장만 하고, WebSocket 폴링 시 전달
            logger.info(f"동기 브로드캐스트: 히스토리에 저장 (연결 시 전달)")

    async def send_to_user(self, user_id: str, message: dict):
        """특정 사용자에게만 메시지를 전송합니다."""
        await self.broadcast(message, user_id=user_id)

    # ==============================
    # 알림 히스토리
    # ==============================
    def _add_to_history(self, message: dict):
        """알림 히스토리에 추가"""
        message.setdefault("id", f"notif_{len(self._notification_history) + 1}")
        message.setdefault("created_at", datetime.now().isoformat())
        message.setdefault("read", False)

        self._notification_history.append(message)

        # 히스토리 크기 제한
        if len(self._notification_history) > self._max_history:
            self._notification_history = self._notification_history[-self._max_history:]

    def get_history(self, limit: int = 20, unread_only: bool = False) -> list[dict]:
        """알림 히스토리 조회"""
        items = self._notification_history
        if unread_only:
            items = [n for n in items if not n.get("read")]
        return items[-limit:]

    def mark_as_read(self, notification_id: str) -> bool:
        """알림을 읽음 처리"""
        for n in self._notification_history:
            if n.get("id") == notification_id:
                n["read"] = True
                return True
        return False

    def mark_all_as_read(self):
        """전체 알림 읽음 처리"""
        for n in self._notification_history:
            n["read"] = True


# 싱글톤 인스턴스
notification_manager = NotificationManager()
