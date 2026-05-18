"""multi-head 머지: d4f8e1a3b2c5 + f8b3c2a5d9e1

운영 환경에 d4f8(multiteam_and_announce_period) 까지 적용된 상태에서 신규
f8b3(memo_template_team) 이 들어오면서 두 head 가 생긴 것을 단일 head 로 합친다.
실제 스키마 변경은 없음.

Revision ID: g4a9d2c7e3b8
Revises: d4f8e1a3b2c5, f8b3c2a5d9e1
Create Date: 2026-05-19
"""
from typing import Sequence, Union


revision: str = 'g4a9d2c7e3b8'
down_revision: Union[str, Sequence[str], None] = ('d4f8e1a3b2c5', 'f8b3c2a5d9e1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
