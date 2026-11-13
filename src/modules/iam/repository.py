from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.iam.models import User, UserRole


class UserRepository:
    """Async repository for User persistence and query operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: UUID) -> User | None:
        """Fetch a single user by primary key UUID."""
        stmt = select(User).where(User.id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> User | None:
        """Fetch a single user by exact username."""
        stmt = select(User).where(User.username == username)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        """Fetch a single user by normalized email."""
        stmt = select(User).where(User.email == email.lower())
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_username_or_email(self, identifier: str) -> User | None:
        """Fetch a user matching either username or lowercase email."""
        cleaned = identifier.strip()
        stmt = select(User).where(or_(User.username == cleaned, User.email == cleaned.lower()))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_users(
        self,
        *,
        offset: int,
        limit: int,
        role: UserRole | None = None,
        is_active: bool | None = None,
    ) -> tuple[list[User], int]:
        """Return paginated users and total matching count."""
        filters = []
        if role is not None:
            filters.append(User.role == role)
        if is_active is not None:
            filters.append(User.is_active == is_active)

        count_stmt = select(func.count(User.id)).where(*filters)
        total = (await self.session.execute(count_stmt)).scalar_one()

        data_stmt = (
            select(User)
            .where(*filters)
            .order_by(User.created_at.desc(), User.username.asc())
            .offset(offset)
            .limit(limit)
        )
        users = list((await self.session.execute(data_stmt)).scalars().all())
        return users, total

    async def create(self, user: User) -> User:
        """Persist a new user entity and refresh database-generated attributes."""
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def update(self, user: User) -> User:
        """Commit changes to an existing user entity and refresh its state."""
        await self.session.commit()
        await self.session.refresh(user)
        return user
