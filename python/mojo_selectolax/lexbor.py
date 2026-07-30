"""Selectolax-compatible parser objects backed by Mojo."""

from __future__ import annotations

from html import escape, unescape
from typing import Iterator

import numpy as np

from ._lib import addr, lib
from .css import SelectorError, compile_selector, name_hash

NF = 16
AF = 6
K_DOCUMENT = 0
K_ELEMENT = 1
K_TEXT = 2
K_COMMENT = 3
VOID = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}
SYNTHETIC_TAGS = {-1: "html", -2: "head", -3: "body"}


class SelectolaxError(RuntimeError):
    pass


class LexborHTMLParser:
    def __init__(
        self,
        html: str | bytes,
        is_fragment: bool = False,
        fragment_tag: str = "div",
        fragment_namespace: str = "html",
    ) -> None:
        if not isinstance(html, (str, bytes)):
            raise TypeError("html must be str or bytes")
        self._raw = html.encode("utf-8") if isinstance(html, str) else bytes(html)
        storage = self._raw or b"\0"
        self._source = np.frombuffer(storage, dtype=np.uint8)
        less_thans = self._raw.count(b"<")
        node_capacity = max(16, less_thans * 2 + 8)
        attr_capacity = max(16, less_thans * 4 + self._raw.count(b"=") + 8)
        while True:
            self._nodes = np.empty((node_capacity, NF), dtype=np.int64)
            self._attrs = np.empty((attr_capacity, AF), dtype=np.int64)
            meta = np.zeros(3, dtype=np.int64)
            count = int(
                lib().msx_parse(
                    addr(self._source),
                    len(self._raw),
                    addr(self._nodes),
                    node_capacity,
                    addr(self._attrs),
                    attr_capacity,
                    addr(meta),
                )
            )
            if count >= 0:
                if count > node_capacity or int(meta[0]) > attr_capacity:
                    raise SelectolaxError("HTML parser returned an invalid buffer count")
                break
            if int(meta[2]) == 1 and node_capacity < len(self._raw) + 8:
                node_capacity = min(len(self._raw) + 8, node_capacity * 2)
                continue
            if int(meta[2]) == 2 and attr_capacity < len(self._raw) // 2 + 8:
                attr_capacity = min(len(self._raw) // 2 + 8, attr_capacity * 2)
                continue
            raise SelectolaxError(
                f"HTML parse capacity error {int(meta[2])} at byte {int(meta[1])}"
            )
        self._nodes = self._nodes[:count]
        self._attrs = self._attrs[: int(meta[0])]
        self._addresses = (
            addr(self._source),
            addr(self._nodes),
            addr(self._attrs),
        )
        self._scope_capacities: dict[int, int] = {}
        self._cache: list[LexborNode | None] = [None] * count
        self._is_fragment = is_fragment
        self._fragment_tag = fragment_tag
        self._fragment_namespace = fragment_namespace

    def _node(self, node_id: int) -> "LexborNode":
        node = self._cache[node_id]
        if node is None:
            node = LexborNode(self, node_id)
            self._cache[node_id] = node
        return node

    @property
    def root(self) -> "LexborNode":
        return self._node(1)

    @property
    def head(self) -> "LexborNode":
        return self._node(2)

    @property
    def body(self) -> "LexborNode":
        return self._node(3)

    @property
    def raw_html(self) -> bytes:
        return self._raw

    @property
    def html(self) -> str:
        return self.root.html

    @property
    def inner_html(self) -> str:
        return self.root.inner_html

    def html_pretty(self, indent: int = 0, **_: object) -> str:
        return self.html

    def inner_html_pretty(self, indent: int = 0, **_: object) -> str:
        return self.inner_html

    def _select_ids(
        self, query: str, scope: int = 0, limit: int | None = None
    ) -> np.ndarray:
        plan = compile_selector(query)
        max_capacity = len(self._nodes)
        if scope:
            max_capacity = self._scope_capacities.get(scope, 0)
            if not max_capacity:
                max_capacity = int(
                    lib().msx_subtree_count(
                        self._addresses[1], len(self._nodes), scope
                    )
                )
                if max_capacity < 0 or max_capacity > len(self._nodes):
                    raise SelectolaxError("selector returned an invalid subtree size")
                self._scope_capacities[scope] = max_capacity
        capacity = max_capacity if limit is None else min(limit, max_capacity)
        result = np.empty(capacity, dtype=np.int64)
        source_addr, nodes_addr, attrs_addr = self._addresses
        steps_addr, groups_addr, conditions_addr, values_addr = plan.addresses
        count = int(
            lib().msx_select(
                source_addr,
                nodes_addr,
                len(self._nodes),
                attrs_addr,
                steps_addr,
                groups_addr,
                len(plan.groups),
                conditions_addr,
                values_addr,
                addr(result),
                capacity,
                scope,
            )
        )
        if count < 0 or count > capacity:
            raise SelectolaxError("selector returned an invalid result count")
        return result[:count]

    def _select_first_id(self, query: str, scope: int = 0) -> int:
        plan = compile_selector(query)
        source_addr, nodes_addr, attrs_addr = self._addresses
        steps_addr, groups_addr, conditions_addr, values_addr = plan.addresses
        node_id = int(
            lib().msx_select_first(
                source_addr,
                nodes_addr,
                len(self._nodes),
                attrs_addr,
                steps_addr,
                groups_addr,
                len(plan.groups),
                conditions_addr,
                values_addr,
                scope,
            )
        )
        if node_id < -1 or node_id >= len(self._nodes):
            raise SelectolaxError("selector returned an invalid node index")
        return node_id

    def css(self, query: str) -> list["LexborNode"]:
        return [self._node(int(index)) for index in self._select_ids(query)]

    def css_first(
        self, query: str, default: object = None, strict: bool = False
    ) -> "LexborNode | object":
        if strict:
            ids = self._select_ids(query, limit=2)
            if len(ids) > 1:
                raise ValueError("Expected a single match")
            return self._node(int(ids[0])) if len(ids) else default
        node_id = self._select_first_id(query)
        return self._node(node_id) if node_id >= 0 else default

    def css_matches(self, selector: str) -> bool:
        return self._select_first_id(selector) >= 0

    def any_css_matches(self, selectors: tuple[str, ...]) -> bool:
        return any(self.css_matches(selector) for selector in selectors)

    def tags(self, name: str) -> list["LexborNode"]:
        if not name or len(name) > 100:
            raise ValueError("tag name must contain between 1 and 100 characters")
        wanted = name_hash(name)
        return [node for node in self.root.traverse() if node.tag_id == wanted]

    def text(
        self,
        deep: bool = True,
        separator: str = "",
        strip: bool = False,
        skip_empty: bool = False,
    ) -> str:
        return self.root.text(deep, separator, strip, skip_empty)

    def scripts_contain(self, query: str) -> bool:
        return any(query in node.text() for node in self.tags("script"))

    def script_srcs_contain(self, queries: str | tuple[str, ...]) -> bool:
        terms = (queries,) if isinstance(queries, str) else queries
        return any(
            any(term in (node.attributes.get("src") or "") for term in terms)
            for node in self.tags("script")
        )

    def clone(self) -> "LexborHTMLParser":
        return type(self)(
            self._raw,
            is_fragment=self._is_fragment,
            fragment_tag=self._fragment_tag,
            fragment_namespace=self._fragment_namespace,
        )

    def select(self, query: str | None = None):
        return self.css(query or "*")

    def strip_tags(self, tags: list[str], recursive: bool = False) -> None:
        raise NotImplementedError("DOM mutation is not part of the covered subset")

    def unwrap_tags(self, tags: list[str], delete_empty: bool = False) -> None:
        raise NotImplementedError("DOM mutation is not part of the covered subset")

    def merge_text_nodes(self) -> None:
        raise NotImplementedError("DOM mutation is not part of the covered subset")


class LexborNode:
    __slots__ = ("_parser", "_id")

    def __init__(self, parser: LexborHTMLParser, node_id: int) -> None:
        self._parser = parser
        self._id = node_id

    def _field(self, offset: int) -> int:
        return int(self._parser._nodes[self._id, offset])

    def _related(self, offset: int) -> "LexborNode | None":
        node_id = self._field(offset)
        return self._parser._node(node_id) if node_id >= 0 else None

    @property
    def parser(self) -> LexborHTMLParser:
        return self._parser

    @property
    def mem_id(self) -> int:
        return self._id

    @property
    def tag_id(self) -> int:
        return self._field(8)

    @property
    def tag(self) -> str:
        kind = self._field(0)
        if kind == K_DOCUMENT:
            return "#document"
        if kind == K_TEXT:
            return "-text"
        if kind == K_COMMENT:
            return "-comment"
        start, length = self._field(6), self._field(7)
        if start < 0:
            return SYNTHETIC_TAGS[start]
        return self._parser._raw[start : start + length].decode("utf-8").lower()

    @property
    def parent(self) -> "LexborNode | None":
        return self._related(1)

    @property
    def child(self) -> "LexborNode | None":
        return self._related(2)

    @property
    def first_child(self) -> "LexborNode | None":
        return self.child

    @property
    def last_child(self) -> "LexborNode | None":
        return self._related(3)

    @property
    def prev(self) -> "LexborNode | None":
        return self._related(4)

    @property
    def next(self) -> "LexborNode | None":
        return self._related(5)

    @property
    def attributes(self) -> dict[str, str | None]:
        result: dict[str, str | None] = {}
        start, count = self._field(11), self._field(12)
        for index in range(start, start + count):
            row = self._parser._attrs[index]
            name_start, name_len = int(row[0]), int(row[1])
            name = self._parser._raw[name_start : name_start + name_len].decode("utf-8").lower()
            value_start, value_len = int(row[3]), int(row[4])
            value = None
            if value_len >= 0:
                value = unescape(
                    self._parser._raw[value_start : value_start + value_len].decode("utf-8")
                )
            if name not in result:
                result[name] = value
        return result

    @property
    def attrs(self) -> dict[str, str | None]:
        return self.attributes

    @property
    def id(self) -> str | None:
        return self.attributes.get("id")

    @property
    def raw_value(self) -> bytes:
        if not self.is_text_node:
            raise NotImplementedError("raw_value is supported on text nodes only")
        start, length = self._field(9), self._field(10)
        return self._parser._raw[start : start + length]

    @property
    def comment_content(self) -> str | None:
        if not self.is_comment_node:
            return None
        start, length = self._field(9), self._field(10)
        return self._parser._raw[start : start + length].decode("utf-8")

    @property
    def is_document_node(self) -> bool:
        return self._field(0) == K_DOCUMENT

    @property
    def is_element_node(self) -> bool:
        return self._field(0) == K_ELEMENT

    @property
    def is_text_node(self) -> bool:
        return self._field(0) == K_TEXT

    @property
    def is_comment_node(self) -> bool:
        return self._field(0) == K_COMMENT

    @property
    def is_empty_text_node(self) -> bool:
        return self.is_text_node and not self.text().strip()

    def _children(self) -> Iterator["LexborNode"]:
        child = self.child
        while child is not None:
            yield child
            child = child.next

    def iter(self, include_text: bool = False, skip_empty: bool = False):
        for child in self._children():
            if child.is_element_node or (
                include_text
                and (not skip_empty or not child.is_empty_text_node)
            ):
                yield child

    def traverse(self, include_text: bool = False, skip_empty: bool = False):
        if self.is_element_node or self.is_document_node or (
            include_text and (not skip_empty or not self.is_empty_text_node)
        ):
            yield self
        for child in self._children():
            yield from child.traverse(include_text, skip_empty)

    def _text_chunks(self, deep: bool) -> list[str]:
        chunks: list[str] = []
        candidates = self.traverse(include_text=True) if deep else self._children()
        for node in candidates:
            if node.is_text_node:
                chunks.append(node._decoded_text())
        return chunks

    def _decoded_text(self) -> str:
        start, length = self._field(9), self._field(10)
        value = self._parser._raw[start : start + length].decode("utf-8")
        parent = self.parent
        if parent is not None and parent.tag in {"script", "style"}:
            return value
        return unescape(value)

    def text(
        self,
        deep: bool = True,
        separator: str = "",
        strip: bool = False,
        skip_empty: bool = False,
    ) -> str:
        if self.is_text_node or self.is_comment_node:
            start, length = self._field(9), self._field(10)
            value = self._parser._raw[start : start + length].decode("utf-8")
            return self._decoded_text() if self.is_text_node else value
        chunks = self._text_chunks(deep)
        if skip_empty:
            chunks = [chunk for chunk in chunks if chunk]
        if strip:
            chunks = [chunk.strip() for chunk in chunks]
        return separator.join(chunks)

    @property
    def text_content(self) -> str:
        return self.text(deep=False)

    def _serialize(self) -> str:
        if self.is_document_node:
            return "".join(child._serialize() for child in self._children())
        if self.is_text_node:
            if self.parent is not None and self.parent.tag in {"script", "style"}:
                return self.text()
            return escape(self.text(), quote=False)
        if self.is_comment_node:
            return f"<!--{self.comment_content or ''}-->"
        attrs = "".join(
            f' {name}="{escape(value or "", quote=True)}"'
            for name, value in self.attributes.items()
        )
        opening = f"<{self.tag}{attrs}>"
        if self.tag in VOID:
            return opening
        return opening + "".join(child._serialize() for child in self._children()) + f"</{self.tag}>"

    @property
    def html(self) -> str:
        return self._serialize()

    @property
    def inner_html(self) -> str:
        return "".join(child._serialize() for child in self._children())

    def html_pretty(self, indent: int = 0, **_: object) -> str:
        return self.html

    def inner_html_pretty(self, indent: int = 0, **_: object) -> str:
        return self.inner_html

    def css(self, query: str) -> list["LexborNode"]:
        return [
            self._parser._node(int(index))
            for index in self._parser._select_ids(query, self._id)
        ]

    def css_first(
        self, query: str, default: object = None, strict: bool = False
    ) -> "LexborNode | object":
        if strict:
            ids = self._parser._select_ids(query, self._id, limit=2)
            if len(ids) > 1:
                raise ValueError("Expected a single match")
            return self._parser._node(int(ids[0])) if len(ids) else default
        node_id = self._parser._select_first_id(query, self._id)
        return self._parser._node(node_id) if node_id >= 0 else default

    def css_matches(self, selector: str) -> bool:
        return self._parser._select_first_id(selector, self._id) >= 0

    def any_css_matches(self, selectors: tuple[str, ...]) -> bool:
        return any(self.css_matches(selector) for selector in selectors)

    def scripts_contain(self, query: str) -> bool:
        return any(query in node.text() for node in self.css("script"))

    def script_srcs_contain(self, queries: str | tuple[str, ...]) -> bool:
        terms = (queries,) if isinstance(queries, str) else queries
        return any(
            any(term in (node.attributes.get("src") or "") for term in terms)
            for node in self.css("script")
        )

    def select(self, query: str | None = None):
        return self.css(query or "*")

    def clone(self) -> "LexborNode":
        cloned = type(self._parser)(self.html)
        return cloned.body.child or cloned.body

    def decompose(self, recursive: bool = True) -> None:
        raise NotImplementedError("DOM mutation is not part of the covered subset")

    remove = decompose

    def unwrap(self, delete_empty: bool = False) -> None:
        raise NotImplementedError("DOM mutation is not part of the covered subset")

    def __repr__(self) -> str:
        return f"<LexborNode {self.tag!r} at {self._id}>"
