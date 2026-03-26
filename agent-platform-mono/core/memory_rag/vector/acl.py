from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Sequence


class VectorStoreAdapter(ABC):
    @abstractmethod
    def create_collection(self, name: str, schema: Dict[str, Any]) -> None:
        ...

    @abstractmethod
    def upsert(self, collection: str, items: Sequence[Dict[str, Any]]) -> None:
        ...

    @abstractmethod
    def add_texts(
        self,
        collection: str,
        texts: List[str],
        metadatas: List[Dict[str, Any]],
        ids: List[str] | None = None,
    ) -> List[str]:
        ...

    @abstractmethod
    def search(
        self,
        collection: str,
        query_vector: List[float],
        top_k: int,
        filter_ast: Dict[str, Any] | None = None,
        with_vectors: bool = False,
    ) -> List[Dict[str, Any]]:
        ...

    @abstractmethod
    def delete(self, collection: str, ids: List[str]) -> int:
        ...

    @abstractmethod
    def by_ids(self, collection: str, ids: List[str]) -> List[Dict[str, Any]]:
        ...

    @abstractmethod
    def list_collections(self) -> List[str]:
        ...
