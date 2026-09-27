"""DuckLake target URI parsing."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote_plus, urlsplit


@dataclass(frozen=True)
class CatalogURI:
    """Resolved DuckLake target."""

    catalog_uri: str  # sqlite:/path or postgresql://...
    storage_root: str  # local path or s3://...


def parse_target(target: str) -> CatalogURI:
    """Parse an ``omnisus`` target string.

    Forms accepted:
        ``ducklake:./omnisus.ducklake``
            -> sqlite catalog at ``./omnisus-catalog.sqlite``
            -> storage at ``./omnisus.ducklake/``
        ``ducklake:postgresql://user:pwd@host/db?storage=s3://bucket/lake``
            -> postgres catalog
            -> storage at ``s3://bucket/lake``
    """
    if not target.startswith("ducklake:"):
        raise ValueError("target must start with 'ducklake:'")
    body = target[len("ducklake:") :]

    if body.startswith(("postgresql://", "postgres://")):
        try:
            split = urlsplit(body)
        except ValueError:
            raise ValueError("invalid postgres target URI") from None
        storage = []
        kept = []
        for part in split.query.split("&"):
            key, _, value = part.partition("=")
            if unquote_plus(key) == "storage":
                storage.append(unquote_plus(value))
            elif part:
                kept.append(part)
        if len(storage) != 1 or not storage[0]:
            raise ValueError("postgres target requires exactly one ?storage=<path or s3 uri>")
        # Rebuilt by hand: urlunsplit restores the empty authority of a
        # ``postgresql:///?host=…`` DSN only for schemes it knows, and libpq
        # rejects the ``postgresql:/?host=…`` it produced instead.
        clean_url = body.partition("?")[0]
        if kept:
            clean_url += "?" + "&".join(kept)
        if split.fragment:
            clean_url += "#" + split.fragment
        return CatalogURI(catalog_uri=clean_url, storage_root=storage[0])

    storage_path = Path(body).expanduser().resolve()
    catalog_path = storage_path.with_name(storage_path.stem + "-catalog.sqlite")
    return CatalogURI(
        catalog_uri=f"sqlite:{catalog_path}",
        storage_root=str(storage_path),
    )


DATA_DIR_ENV = "OMNISUS_DATA_DIR"


def data_dir() -> Path:
    """The default lake's directory: ``$OMNISUS_DATA_DIR``, else ``data/raw`` under the cwd.

    Read at call time, so a notebook can set the variable after ``import omnisus``.
    On Colab the working directory is ``/content``, so the default is ``/content/data/raw``.
    """
    if env := os.environ.get(DATA_DIR_ENV):
        return Path(env)
    return Path.cwd() / "data" / "raw"


def set_lake_dir(path: str | os.PathLike[str]) -> Path:
    """Keep the default lake in ``path`` for the rest of this session.

    Every call without ``target`` (``load``, ``LakeReader``, ``import_*``) then reads
    and writes the lake there. On Colab, point it at the mounted Google Drive so the
    lake survives the runtime. It sets ``$OMNISUS_DATA_DIR``, which scripts can set
    directly instead. The folder is created by the first import.

    Args:
        path: The lake's folder; ``~`` and relative paths are resolved now.

    Returns:
        The absolute folder.

    Examples:
        >>> import omnisus as sus
        >>> sus.set_lake_dir("/content/drive/MyDrive/omnisus")  # doctest: +SKIP
        PosixPath('/content/drive/MyDrive/omnisus')
    """
    folder = Path(path).expanduser().resolve()
    os.environ[DATA_DIR_ENV] = str(folder)
    return folder


def resolve_target(target: str | None) -> str:
    """``target`` itself, or the default lake in :func:`data_dir` when it is ``None``."""
    return target if target is not None else f"ducklake:{data_dir() / 'omnisus.ducklake'}"
