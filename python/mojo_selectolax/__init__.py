"""Fast HTML parsing and CSS selection with Mojo kernels."""

from .css import SelectorError
from .lexbor import LexborHTMLParser, LexborNode, SelectolaxError
from .parser import HTMLParser, Node

__version__ = "0.1.0"
__all__ = [
    "HTMLParser",
    "LexborHTMLParser",
    "LexborNode",
    "Node",
    "SelectorError",
    "SelectolaxError",
]
