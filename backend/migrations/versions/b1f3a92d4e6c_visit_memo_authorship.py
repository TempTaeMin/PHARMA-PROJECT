"""visit_logs: notes/post_notes 작성자·시각 컬럼 추가

Revision ID: b1f3a92d4e6c
Revises: a0db4d78f885
Create Date: 2026-05-04

공유 일정에서 누가 언제 결과 메모/사전 메모를 정리했는지 추적하기 위한 컬럼 추가.
기존 행은 created_at + visit owner(user_id) 로 backfill — 정확하진 않지만
"누가 처음 만들었는지" 까지는 보존된다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b1f3a92d4e6c'
down_revision: Union[str, None] = 'a0db4d78f885'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('visit_logs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('notes_author_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('notes_updated_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('post_notes_author_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('post_notes_updated_at', sa.DateTime(), nullable=True))
        batch_op.create_foreign_key(
            'fk_visit_logs_notes_author',
            'users', ['notes_author_id'], ['id'], ondelete='SET NULL',
        )
        batch_op.create_foreign_key(
            'fk_visit_logs_post_notes_author',
            'users', ['post_notes_author_id'], ['id'], ondelete='SET NULL',
        )

    # backfill: 기존 메모는 visit owner 가 created_at 에 작성했다고 가정
    op.execute(
        """
        UPDATE visit_logs
           SET notes_author_id = user_id,
               notes_updated_at = created_at
         WHERE notes IS NOT NULL AND notes != ''
        """
    )
    op.execute(
        """
        UPDATE visit_logs
           SET post_notes_author_id = user_id,
               post_notes_updated_at = created_at
         WHERE post_notes IS NOT NULL AND post_notes != ''
        """
    )


def downgrade() -> None:
    with op.batch_alter_table('visit_logs', schema=None) as batch_op:
        batch_op.drop_constraint('fk_visit_logs_post_notes_author', type_='foreignkey')
        batch_op.drop_constraint('fk_visit_logs_notes_author', type_='foreignkey')
        batch_op.drop_column('post_notes_updated_at')
        batch_op.drop_column('post_notes_author_id')
        batch_op.drop_column('notes_updated_at')
        batch_op.drop_column('notes_author_id')
