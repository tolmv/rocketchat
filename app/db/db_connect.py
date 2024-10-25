from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine

import config

engine = create_async_engine(
    f"{config.POSTGRES_TYPE}://{config.POSTGRES_USER}:"
    f"{config.POSTGRES_PASSWORD}@{config.POSTGRES_HOST}:"
    f"{config.POSTGRES_PORT}/{config.POSTGRES_DB}",
    echo=True,
)

SessionLocal = async_sessionmaker(engine)
async_session = async_sessionmaker(engine, expire_on_commit=False)
