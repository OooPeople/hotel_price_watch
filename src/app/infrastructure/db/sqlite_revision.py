"""SQLite 查詢結果版本 token helper。"""

from __future__ import annotations

import hashlib
from sqlite3 import Connection


def rows_revision_token(
    connection: Connection,
    query: str,
    parameters: tuple[object, ...] = (),
) -> str:
    """把指定查詢結果轉成穩定 hash，供 web fragment 版本判斷。"""
    rows = connection.execute(query, parameters).fetchall()
    digest = hashlib.sha256()
    for row in rows:
        for key in row.keys():
            value = row[key]
            digest.update(str(key).encode("utf-8"))
            digest.update(b"=")
            digest.update(str(value if value is not None else "").encode("utf-8"))
            digest.update(b"\x1f")
        digest.update(b"\x1e")
    return digest.hexdigest()


def hash_revision_parts(parts: tuple[str, ...]) -> str:
    """合併多個子版本 token，避免上層知道各資料表細節。"""
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\x1e")
    return digest.hexdigest()
