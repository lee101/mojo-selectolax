# mojo-selectolax

Fast HTML parsing and CSS selection implemented in
[Mojo](https://www.modular.com/mojo) and exposed to Python through a
selectolax-shaped API.

```python
from mojo_selectolax import LexborHTMLParser

tree = LexborHTMLParser("""
<main>
  <article class="product" data-stock="yes">
    <a href="/tea">Tea &amp; biscuits</a>
  </article>
</main>
""")

link = tree.css_first("article.product[data-stock] > a")
print(link.attributes["href"])  # /tea
print(link.text())              # Tea & biscuits
```

This is a standalone implementation. It does not bind or embed Lexbor. The
covered API is parity-tested against
[selectolax 0.4.11](https://pypi.org/project/selectolax/), using its preferred
`selectolax.lexbor` backend.

## Covered subset

The parser accepts `str` or UTF-8 `bytes` and exposes `LexborHTMLParser`,
`HTMLParser`, `LexborNode`, and `Node`. The two parser names share the Mojo
backend.

Implemented parser and node behavior includes:

- synthetic `html`, `head`, and `body` elements; void elements; comments;
  raw-text `script` and `style` content; and common optional-end-tag recovery
  for `p`, `li`, `dt`/`dd`, `option`, `tr`, and `td`/`th`;
- `root`, `head`, `body`, `raw_html`, `html`, `inner_html`, `tag`,
  `attributes`/`attrs`, `id`, `parent`, `child`, `last_child`, `prev`, and
  `next`;
- `text()` with the upstream `deep`, `separator`, `strip`, and `skip_empty`
  options, including HTML entity decoding;
- `iter()`, `traverse()`, `tags()`, `clone()`, `scripts_contain()`, and
  `script_srcs_contain()`;
- `css()`, `css_first()`, `css_matches()`, and `any_css_matches()`.

CSS matching covers:

- type, universal, ID, and class selectors;
- `[attr]`, `=`, `^=`, `$=`, `*=`, `~=`, and `|=` attribute selectors, plus
  the `i` flag for equality;
- descendant, child, adjacent-sibling, and general-sibling combinators;
- selector groups;
- `:first-child`, `:last-child`, `:only-child`, `:nth-child()`,
  `:first-of-type`, `:last-of-type`, `:only-of-type`, `:nth-of-type()`,
  `:empty`, `:root`, and a single-simple-selector `:not()`.

The behavioral suite parity-tests each capability listed above against the
real upstream package.

## Not covered

This is not yet a complete HTML5 tree-construction implementation. The
adoption-agency algorithm, full table foster parenting, foreign SVG/MathML
namespaces, encoding detection, and fragment parsing semantics are outside the
current subset. On markup that depends on those rules, use upstream selectolax.

DOM mutation, advanced selector chaining, pretty-print formatting, CSS
escapes, and functional selectors such as `:has()`, `:is()`, `:where()`, and
`:lexbor-contains()` are also not implemented. Unsupported CSS raises
`SelectorError` instead of returning a plausible but incorrect result.

The package imports as `mojo_selectolax`, so adopting it requires changing the
import. Covered class and method names follow upstream.

## Install

The repository carries its Mojo compiler pin and all Python dependencies:

```bash
pixi install
pixi run build
pixi run test
```

`pixi run build` creates `dist/libmojo-selectolax.so`. The Python binding also
rebuilds a missing or stale library on first import. Set
`MOJO_SELECTOLAX_LIB=/absolute/path/to/libmojo-selectolax.so` to use a
prebuilt library.

Run the benchmark through its locked pixi task:

```bash
pixi run bench
```

## Performance

Measured on an Intel Xeon E5-2697 v4 at 2.30 GHz, 72 logical CPUs, Linux
x86-64. The input is a 1,909,594-byte catalog with 12,000 product records.
Times are the best of seven warm runs. A ratio above 1 means mojo-selectolax is
faster. The benchmark checks result counts before timing.

| case | mojo-selectolax | selectolax 0.4.11 | ratio |
| --- | ---: | ---: | ---: |
| parse 1.9 MB document | 8.592 ms | 63.043 ms | 7.34x faster |
| select `article.product` | 3.121 ms | 9.358 ms | 3.00x faster |
| select `.featured > a.link` | 1.698 ms | 8.330 ms | 4.90x faster |
| select `[data-stock='3'] .price` | 2.401 ms | 7.791 ms | 3.24x faster |
| parse + complex select | 11.366 ms | 73.085 ms | 6.43x faster |
| first `article.product` | 0.003 ms | 0.006 ms | 1.84x faster |
| matches `article.product` | 0.003 ms | 0.006 ms | 1.78x faster |
| scoped select `.price` | 0.005 ms | 0.005 ms | 1.13x faster |

These numbers describe the covered, regular catalog-shaped workload. They are
not a claim of full HTML5 equivalence.

The parser and matcher are branch-heavy byte and tree-table traversals with
well under two arithmetic operations per byte moved, so there is no GPU path:
transfer and launch overhead would dominate. Selection also stays serial. The
measured scans are only a few milliseconds, while parallel ordered result
collection would add thread-launch and compaction overhead.

## How it works

Python owns the input and every output allocation. The UTF-8 source is a
contiguous `uint8` buffer. Mojo tokenizes it once into a compact tree table
with 16 `int64` fields per node and a separate six-field attribute table.
Links are integer row indices, so traversal does not allocate objects or chase
Python references.

The small CSS compiler in Python turns a query into fixed-width condition,
compound, and selector-group tables. Immutable compiled plans and their buffer
addresses are cached. One ctypes call passes those tables and the parsed tree
to Mojo. The matcher walks in document order and evaluates combinators without
crossing the FFI again. A dedicated first-match entry point returns immediately
without allocating an output array, and scoped list queries size their output
for the subtree rather than the full document. Python materializes node wrapper
objects only for matches.

Selection output uses a thread-local NumPy scratch buffer that grows on demand
and caches its validated FFI address. Repeated queries therefore avoid output
allocation and address discovery while concurrent queries remain isolated.

All buffers cross the C ABI as integer addresses. The exported Mojo functions
use `@export("...")` with `abi("C")`, reconstruct
`UnsafePointer[..., AnyOrigin[mut=True]]` values inside the boundary, and do
not allocate. Case-sensitive attribute and class comparisons use SIMD loads
with an explicit scalar remainder loop. Entity decoding and HTML serialization
remain in Python, where they are not part of the parse/select hot path.

## License

MIT
