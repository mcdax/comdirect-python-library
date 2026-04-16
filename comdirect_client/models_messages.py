"""Data classes for the ``/api/messages/*`` endpoints.

The list endpoint returns document metadata in JSON. The single-document
download returns raw binary (PDF or HTML) — see ``get_document_content``
in :mod:`comdirect_client.http_api` for the Accept-header dance required.
"""

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class DocumentMetadata:
    """Metadata returned alongside each document in the list view."""

    archived: bool = False
    alreadyRead: bool = False
    predocumentExists: bool = False
    dateRead: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DocumentMetadata":
        return cls(
            archived=bool(data.get("archived", False)),
            alreadyRead=bool(data.get("alreadyRead", False)),
            predocumentExists=bool(data.get("predocumentExists", False)),
            dateRead=data.get("dateRead"),
        )


@dataclass
class Document:
    """A single document in the customer's PostBox."""

    documentId: str
    name: str
    mimeType: str
    dateCreation: Optional[str] = None
    deletable: bool = False
    advertisement: bool = False
    documentMetaData: Optional[DocumentMetadata] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Document":
        return cls(
            documentId=data["documentId"],
            name=data["name"],
            mimeType=data["mimeType"],
            dateCreation=data.get("dateCreation"),
            deletable=bool(data.get("deletable", False)),
            advertisement=bool(data.get("advertisement", False)),
            documentMetaData=(
                DocumentMetadata.from_dict(data["documentMetaData"])
                if data.get("documentMetaData")
                else None
            ),
        )


__all__ = ["Document", "DocumentMetadata"]
