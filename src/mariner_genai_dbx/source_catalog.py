"""Allowlisted Unity Catalog Volume browsing and PDF access."""

from __future__ import annotations

from collections import deque
from pathlib import PurePosixPath

from .errors import (
    DatabricksAuthenticationError,
    InvalidSourcePathError,
    SourceCatalogError,
)
from .models import VolumeCatalog


MAX_DIRECTORY_ENTRIES = 1000
MAX_SEARCH_OBJECTS = 5000
MAX_SEARCH_RESULTS = 50


class DatabricksVolumeCatalogService:
    def __init__(self, catalogs: tuple[VolumeCatalog, ...], *, workspace_client):
        self._catalogs = {catalog.id: catalog for catalog in catalogs}
        self._workspace_client = workspace_client

    def catalogs(self) -> list[dict[str, str]]:
        return [
            {"id": catalog.id, "label": catalog.label}
            for catalog in self._catalogs.values()
        ]

    def list_children(self, catalog_id: str, path: str, cursor: str | None):
        if cursor:
            raise InvalidSourcePathError("Pagination cursor is not supported")
        catalog = self._catalog(catalog_id)
        relative_path = self._relative_path(path, folder=True)
        entries = self._list(catalog, relative_path)
        return {
            "catalogId": catalog.id,
            "path": relative_path,
            "entries": entries[:MAX_DIRECTORY_ENTRIES],
            "cursor": None,
            "truncated": len(entries) > MAX_DIRECTORY_ENTRIES,
        }

    def search(self, query: str):
        normalized_query = query.strip()
        if not 2 <= len(normalized_query) <= 80:
            raise InvalidSourcePathError("Invalid source search")
        tokens = normalized_query.casefold().split()
        results = []
        scanned = 0
        truncated = False

        for catalog in self._catalogs.values():
            folders = deque([""])
            while folders and scanned < MAX_SEARCH_OBJECTS:
                folder = folders.popleft()
                for entry in self._list(catalog, folder):
                    scanned += 1
                    if entry["type"] == "folder":
                        folders.append(entry["path"])
                    elif all(token in entry["path"].casefold() for token in tokens):
                        results.append(
                            {
                                "catalogId": catalog.id,
                                "catalogLabel": catalog.label,
                                **entry,
                            }
                        )
                    if scanned >= MAX_SEARCH_OBJECTS:
                        truncated = bool(folders)
                        break
            if scanned >= MAX_SEARCH_OBJECTS:
                truncated = True
                break

        results.sort(
            key=lambda item: (
                not item["name"].casefold().startswith(tokens[0]),
                item["name"].casefold(),
                item["catalogLabel"].casefold(),
            )
        )
        if len(results) > MAX_SEARCH_RESULTS:
            results = results[:MAX_SEARCH_RESULTS]
            truncated = True
        return {"query": normalized_query, "results": results, "truncated": truncated}

    def open_document(self, catalog_id: str, path: str):
        catalog = self._catalog(catalog_id)
        relative_path = self._relative_path(path, folder=False)
        return {
            "catalogId": catalog.id,
            "path": relative_path,
            "label": PurePosixPath(relative_path).name,
            "embeddable": True,
        }

    def download_document(self, catalog_id: str, path: str):
        catalog = self._catalog(catalog_id)
        relative_path = self._relative_path(path, folder=False)
        try:
            return self._workspace_client.files.download(
                file_path=self._absolute_path(catalog, relative_path)
            )
        except Exception as error:
            self._raise_safe_error(error)

    def reference_for_location(self, location: str | None) -> dict | None:
        if not location:
            return None
        matches = [
            catalog
            for catalog in self._catalogs.values()
            if location.startswith(f"{catalog.volume_path}/")
        ]
        if not matches:
            return None
        catalog = max(matches, key=lambda item: len(item.volume_path))
        relative = location[len(catalog.volume_path) + 1 :]
        try:
            relative = self._relative_path(relative, folder=False)
        except InvalidSourcePathError:
            return None
        return {"catalogId": catalog.id, "path": relative}

    def _list(self, catalog: VolumeCatalog, relative_folder: str) -> list[dict]:
        absolute_path = self._absolute_path(catalog, relative_folder)
        try:
            raw_entries = self._workspace_client.files.list_directory_contents(
                directory_path=absolute_path
            )
            entries = []
            for item in raw_entries:
                item_path = _field(item, "path")
                if not isinstance(item_path, str):
                    continue
                relative_path = self._strip_root(catalog, item_path)
                is_directory = bool(_field(item, "is_directory"))
                if not is_directory and PurePosixPath(relative_path).suffix.lower() != ".pdf":
                    continue
                entries.append(
                    {
                        "type": "folder" if is_directory else "document",
                        "name": PurePosixPath(relative_path).name,
                        "path": relative_path,
                        "embeddable": not is_directory,
                    }
                )
        except Exception as error:
            self._raise_safe_error(error)
        entries.sort(key=lambda item: (item["type"] != "folder", item["name"].casefold()))
        return entries

    def _catalog(self, catalog_id: str) -> VolumeCatalog:
        try:
            return self._catalogs[catalog_id]
        except KeyError as error:
            raise InvalidSourcePathError("Unknown source catalog") from error

    @staticmethod
    def _relative_path(path: str, *, folder: bool) -> str:
        if not isinstance(path, str) or path.startswith("/") or "\\" in path or "\0" in path:
            raise InvalidSourcePathError("Invalid source path")
        normalized = path.strip("/")
        if "//" in path or any(part in {".", ".."} for part in normalized.split("/")):
            raise InvalidSourcePathError("Invalid source path")
        if not folder and (
            not normalized or PurePosixPath(normalized).suffix.lower() != ".pdf"
        ):
            raise InvalidSourcePathError("A PDF document path is required")
        return normalized

    @staticmethod
    def _absolute_path(catalog: VolumeCatalog, relative_path: str) -> str:
        return (
            f"{catalog.volume_path}/{relative_path}"
            if relative_path
            else catalog.volume_path
        )

    @staticmethod
    def _strip_root(catalog: VolumeCatalog, absolute_path: str) -> str:
        prefix = f"{catalog.volume_path}/"
        if not absolute_path.startswith(prefix):
            raise SourceCatalogError("The Volume returned a path outside its approved root")
        return absolute_path[len(prefix) :].strip("/")

    @staticmethod
    def _raise_safe_error(error: Exception):
        status_code = getattr(error, "status_code", None)
        text = f"{type(error).__name__} {error}".casefold()
        if status_code in {401, 403} or any(
            marker in text
            for marker in ("401", "403", "unauthenticated", "permission denied")
        ):
            raise DatabricksAuthenticationError(
                "Databricks denied access to the approved Volume"
            ) from error
        raise SourceCatalogError("The approved Volume is temporarily unavailable") from error


def _field(value, name):
    return value.get(name) if isinstance(value, dict) else getattr(value, name, None)
