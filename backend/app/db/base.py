"""Declarative base for ORM models. Models are added once the data model is designed."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
