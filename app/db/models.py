from datetime import datetime

from sqlalchemy import String, Integer, Date, Boolean, Float
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column


class Base(AsyncAttrs, DeclarativeBase):
    pass


class Prompts(Base):
    __tablename__ = "prompts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    text: Mapped[str] = mapped_column(String)
    date: Mapped[datetime] = mapped_column(Date)
    instance_id: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean)

    def to_dict(self):
        return {
            "id": self.id,
            "text": self.text,
            "date": str(self.date),
            "instance_id": self.instance_id,
            "is_active": self.is_active,
        }


class Instances(Base):
    __tablename__ = "instances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    instance_name: Mapped[str] = mapped_column(String, unique=True)
    model: Mapped[str] = mapped_column(String)
    temperature: Mapped[float] = mapped_column(Float)

    def to_dict(self):
        return {
            "id": self.id,
            "instance_name": self.instance_name,
            "model": self.model,
            "temperature": self.temperature,
        }
