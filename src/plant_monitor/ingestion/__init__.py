"""Loaders for the plant files and snapshots; every data failure raises `DataLoadError`."""

from plant_monitor.ingestion.errors import DataLoadError

__all__ = ["DataLoadError"]
