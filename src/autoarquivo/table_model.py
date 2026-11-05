"""Gerenciamento dos dados das tabelas: modelo genérico, sem duplicatas."""

from __future__ import annotations

from typing import Any, Callable, Hashable, Iterable, Sequence

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal


class ItemTableModel(QAbstractTableModel):
    """Modelo de tabela somente-leitura para uma lista de itens imutáveis.

    * ``extractor`` converte um item na lista de valores das colunas;
    * ``key`` define a identidade usada para impedir duplicatas;
    * ``changed`` é emitido a cada alteração de conteúdo.
    """

    changed = Signal()

    def __init__(
        self,
        headers: Sequence[str],
        extractor: Callable[[Any], Sequence[Any]],
        key: Callable[[Any], Hashable] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._headers = list(headers)
        self._extract = extractor
        self._key = key or (lambda item: item)
        self._items: list[Any] = []

    # --------------------------------------------------------- API do Qt
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._items)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._headers)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        value = self._extract(self._items[index.row()])[index.column()]
        if role == Qt.ItemDataRole.DisplayRole:
            return str(value)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            align = Qt.AlignmentFlag.AlignCenter if isinstance(value, int) else (
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            return int(align.value) if hasattr(align, "value") else int(align)
        return None

    def headerData(self, section: int, orientation: Qt.Orientation,
                   role: int = Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self._headers[section]
        return None

    # --------------------------------------------------------- consultas
    def items(self) -> list[Any]:
        return list(self._items)

    def item_at(self, row: int) -> Any:
        return self._items[row]

    def __len__(self) -> int:
        return len(self._items)

    def contains(self, item: Any) -> bool:
        key = self._key(item)
        return any(self._key(i) == key for i in self._items)

    # ---------------------------------------------------------- alterações
    def add_many(self, items: Iterable[Any]) -> tuple[int, int]:
        """Adiciona itens ignorando duplicatas. Retorna ``(adicionados, ignorados)``."""
        keys = {self._key(i) for i in self._items}
        new: list[Any] = []
        skipped = 0
        for item in items:
            key = self._key(item)
            if key in keys:
                skipped += 1
                continue
            keys.add(key)
            new.append(item)
        if new:
            first = len(self._items)
            self.beginInsertRows(QModelIndex(), first, first + len(new) - 1)
            self._items.extend(new)
            self.endInsertRows()
            self.changed.emit()
        return len(new), skipped

    def add(self, item: Any) -> bool:
        return self.add_many([item])[0] == 1

    def replace(self, row: int, item: Any) -> bool:
        """Substitui a linha; falha (False) se o novo valor duplicar outra linha."""
        key = self._key(item)
        for i, other in enumerate(self._items):
            if i != row and self._key(other) == key:
                return False
        self._items[row] = item
        self.dataChanged.emit(self.index(row, 0), self.index(row, self.columnCount() - 1))
        self.changed.emit()
        return True

    def remove_rows(self, rows: Iterable[int]) -> None:
        for row in sorted(set(rows), reverse=True):
            self.beginRemoveRows(QModelIndex(), row, row)
            del self._items[row]
            self.endRemoveRows()
        self.changed.emit()

    def set_items(self, items: Iterable[Any]) -> None:
        self.beginResetModel()
        self._items = list(items)
        self.endResetModel()
        self.changed.emit()

    def clear(self) -> None:
        self.set_items([])
