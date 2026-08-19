"""Interfaz web. Capa delgada sobre el orquestador."""

from .app import app, crear_app

__all__ = ["app", "crear_app"]
