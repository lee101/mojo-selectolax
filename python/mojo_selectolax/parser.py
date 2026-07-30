"""Compatibility names for selectolax.parser."""

from .lexbor import LexborHTMLParser, LexborNode, SelectolaxError

HTMLParser = LexborHTMLParser
Node = LexborNode

__all__ = ["HTMLParser", "Node", "SelectolaxError"]
