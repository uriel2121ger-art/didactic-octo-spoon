"""CSV export helpers for product catalog and inventory listings."""
from __future__ import annotations

import csv
from typing import Iterable, Mapping

HEADERS = [
    "SKU",
    "Descripción",
    "Tipo",
    "Departamento",
    "Proveedor",
    "Precio Costo",
    "Precio Venta",
    "Precio Mayoreo",
    "Inventario",
    "Min",
    "Max",
    "Fecha actualización",
]


def _row_from_product(product: Mapping[str, object]) -> list[object]:
    return [
        product.get("sku", ""),
        product.get("name", ""),
        product.get("sale_type", ""),
        product.get("department") or product.get("category") or "",
        product.get("provider") or "",
        product.get("cost", ""),
        product.get("price", ""),
        product.get("price_wholesale", ""),
        product.get("stock", ""),
        product.get("min_stock", ""),
        product.get("max_stock", ""),
        product.get("updated_at", ""),
    ]


def export_product_catalog_to_csv(products: Iterable[Mapping[str, object]], filepath: str) -> None:
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(HEADERS)
        for product in products:
            writer.writerow(_row_from_product(product))


def export_inventory_to_csv(products: Iterable[Mapping[str, object]], filepath: str) -> None:
    inventory_products = [p for p in products if p.get("uses_inventory", True)]
    export_product_catalog_to_csv(inventory_products, filepath)
