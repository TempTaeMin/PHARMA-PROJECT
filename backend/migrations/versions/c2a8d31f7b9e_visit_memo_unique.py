"""visits_memo: UNIQUE(visit_log_id, user_id) 추가

Revision ID: c2a8d31f7b9e
Revises: b1f3a92d4e6c
Create Date: 2026-05-04

한 사용자가 한 visit 에 여러 VisitMemo(댓글)를 못 만들게 하기 위함 — 동시 정리 race
방지 + "원본+댓글" 모델의 1인-1댓글 invariant 강제.

기존 데이터: 본 마이그 시점에 같은 (visit_log_id, user_id) 가 둘 이상이면 가장 오래된
것만 남기고 나머지 삭제. raw_memo 가 NULL/빈 것은 우선 제거 후, 그래도 중복이면
오래된 것 유지.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c2a8d31f7b9e'
down_revision: Union[str, None] = 'b1f3a92d4e6c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 동일 (visit_log_id, user_id) 중복 정리 — 가장 오래된 row 만 남기고 삭제
    op.execute(
        """
        DELETE FROM visits_memo
         WHERE id IN (
           SELECT id FROM (
             SELECT id,
                    ROW_NUMBER() OVER (
                      PARTITION BY visit_log_id, user_id
                      ORDER BY created_at ASC, id ASC
                    ) AS rn
               FROM visits_memo
              WHERE visit_log_id IS NOT NULL
           ) sub
          WHERE sub.rn > 1
         )
        """
    )
    with op.batch_alter_table('visits_memo', schema=None) as batch_op:
        batch_op.create_unique_constraint(
            'uq_visit_memo_visit_user', ['visit_log_id', 'user_id']
        )


def downgrade() -> None:
    with op.batch_alter_table('visits_memo', schema=None) as batch_op:
        batch_op.drop_constraint('uq_visit_memo_visit_user', type_='unique')
