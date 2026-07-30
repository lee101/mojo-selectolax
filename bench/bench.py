"""Benchmark Mojo parsing and CSS selection against selectolax/Lexbor."""

from __future__ import annotations

import math
import os
import platform
import sys
import time

sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"),
)

from mojo_selectolax import LexborHTMLParser as MojoParser  # noqa: E402
from selectolax.lexbor import LexborHTMLParser as ReferenceParser  # noqa: E402


def best_time(function, repeat: int = 7) -> float:
    best = math.inf
    for _ in range(repeat):
        start = time.perf_counter()
        function()
        best = min(best, time.perf_counter() - start)
    return best


def document(cards: int = 12_000) -> bytes:
    rows = [
        (
            f'<article class="product {"featured" if i % 11 == 0 else "regular"}" '
            f'data-stock="{i % 7}"><h2>Item {i}</h2>'
            f'<a class="link" href="/p/{i}">Buy &amp; save</a>'
            f'<span class="price">${i % 997}.99</span></article>'
        )
        for i in range(cards)
    ]
    return (
        "<!doctype html><html><head><title>Catalog</title></head><body><main>"
        + "".join(rows)
        + "</main></body></html>"
    ).encode()


def machine() -> str:
    model = platform.processor()
    if not model or model.lower() in {"x86_64", "amd64"}:
        try:
            with open("/proc/cpuinfo", encoding="utf-8") as handle:
                model = next(
                    line.split(":", 1)[1].strip()
                    for line in handle
                    if line.startswith("model name")
                )
        except (OSError, StopIteration):
            model = "unknown CPU"
    return f"{model}; {os.cpu_count()} logical CPUs; {platform.system()} {platform.machine()}"


def main() -> None:
    html = document()
    mojo_tree = MojoParser(html)
    reference_tree = ReferenceParser(html)
    mojo_article = mojo_tree.css_first("article")
    reference_article = reference_tree.css_first("article")

    cases = [
        (
            f"parse {len(html) / 1_000_000:.1f} MB document",
            lambda: MojoParser(html),
            lambda: ReferenceParser(html),
        ),
        (
            "select article.product",
            lambda: mojo_tree.css("article.product"),
            lambda: reference_tree.css("article.product"),
        ),
        (
            "select .featured > a.link",
            lambda: mojo_tree.css(".featured > a.link"),
            lambda: reference_tree.css(".featured > a.link"),
        ),
        (
            "select [data-stock='3'] .price",
            lambda: mojo_tree.css("[data-stock='3'] .price"),
            lambda: reference_tree.css("[data-stock='3'] .price"),
        ),
        (
            "parse + complex select",
            lambda: MojoParser(html).css("article.featured[data-stock] > a.link"),
            lambda: ReferenceParser(html).css("article.featured[data-stock] > a.link"),
        ),
        (
            "first article.product",
            lambda: mojo_tree.css_first("article.product"),
            lambda: reference_tree.css_first("article.product"),
        ),
        (
            "matches article.product",
            lambda: mojo_tree.css_matches("article.product"),
            lambda: reference_tree.css_matches("article.product"),
        ),
        (
            "scoped select .price",
            lambda: mojo_article.css(".price"),
            lambda: reference_article.css(".price"),
        ),
    ]

    print(f"Machine: {machine()}")
    print(f"Input: {len(html):,} bytes, 12,000 product records")
    print()
    print("| case | mojo-selectolax | selectolax 0.4.11 | ratio |")
    print("| --- | ---: | ---: | ---: |")
    for name, ours, theirs in cases:
        ours_result = ours()
        theirs_result = theirs()
        if hasattr(ours_result, "__len__") and hasattr(theirs_result, "__len__"):
            if len(ours_result) != len(theirs_result):
                raise AssertionError(
                    f"{name}: result count differs ({len(ours_result)} != {len(theirs_result)})"
                )
        ours_s = best_time(ours)
        theirs_s = best_time(theirs)
        ratio = theirs_s / ours_s
        label = "faster" if ratio >= 1 else "slower"
        print(
            f"| {name} | {ours_s * 1e3:.3f} ms | {theirs_s * 1e3:.3f} ms | "
            f"{ratio:.2f}x {label} |"
        )


if __name__ == "__main__":
    main()
