"""feedbacks: 베타 테스터 피드백 테이블 신규

Revision ID: e7a2c5b9d1f0
Revises: c2a8d31f7b9e
Create Date: 2026-05-06

베타 테스터가 앱 안에서 보내는 버그/제안/기타 의견을 저장. user_id 는
nullable (익명 허용 + ondelete SET NULL), category 는 enum string,
handled 는 admin 처리 표시용. created_at + handled 에 인덱스.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e7a2c5b9d1f0'
down_revision: Union[str, None] = 'c2a8d31f7b9e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'feedbacks',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('category', sa.String(length=20), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('page_path', sa.String(length=255), nullable=True),
        sa.Column('user_agent', sa.String(length=500), nullable=True),
        sa.Column('handled', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    )
    op.create_index('ix_feedbacks_user_id', 'feedbacks', ['user_id'])
    op.create_index('ix_feedbacks_handled', 'feedbacks', ['handled'])
    op.create_index('ix_feedbacks_created_at', 'feedbacks', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_feedbacks_created_at', table_name='feedbacks')
    op.drop_index('ix_feedbacks_handled', table_name='feedbacks')
    op.drop_index('ix_feedbacks_user_id', table_name='feedbacks')
    op.drop_table('feedbacks')
