"""Module 6: Inventory Engine.

Refreshes hardware + software inventory hourly and pushes it over the WS.
"""
from .engine import InventoryEngine  # noqa: F401

__all__ = ["InventoryEngine"]
