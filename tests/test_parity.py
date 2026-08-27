from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
from selectolax.lexbor import LexborHTMLParser as UpstreamParser

from mojo_selectolax import HTMLParser, LexborHTMLParser
from mojo_selectolax.css import SelectorError


def snapshot(parser, query: str):
    return [
        (node.tag, node.attributes, node.text(), node.html)
        for node in parser.css(query)
    ]


@pytest.mark.parametrize(
    "source",
    [
        "<div><p>A<b>B</b>C</p></div>",
        "<title>T</title><main id=x disabled class='a b'>Hi &amp; bye<br>tail</main>",
        "<ul><li>a</li><li>b</li></ul>",
        "plain text",
        "<section data-x='1'><img src=x><hr><input disabled></section>",
    ],
)
def test_parse_snapshot_matches_lexbor(source):
    assert snapshot(LexborHTMLParser(source), "*") == snapshot(UpstreamParser(source), "*")


def test_parser_alias_matches_public_name():
    assert HTMLParser("<p>x</p>").css_first("p").text() == "x"


def test_bytes_and_raw_html_match_lexbor():
    source = b"<main>caf\xc3\xa9</main>"
    ours, theirs = LexborHTMLParser(source), UpstreamParser(source)
    assert ours.raw_html == theirs.raw_html == source
    assert ours.text() == theirs.text() == "café"


def test_entities_decode_in_text_and_attributes():
    source = "<a title='A &amp; B'>&lt;x&gt; &#169;</a>"
    ours, theirs = LexborHTMLParser(source), UpstreamParser(source)
    assert ours.css_first("a").attributes == theirs.css_first("a").attributes
    assert ours.css_first("a").text() == theirs.css_first("a").text()
    assert ours.css_first("a").html == theirs.css_first("a").html


def test_empty_attribute_is_none_but_serializes_empty():
    node = LexborHTMLParser("<input disabled>").css_first("input")
    reference = UpstreamParser("<input disabled>").css_first("input")
    assert node.attributes == reference.attributes == {"disabled": None}
    assert node.html == reference.html == '<input disabled="">'


def test_implicit_li_close_matches_html5_behavior():
    source = "<ul><li>a<li>b<li><b>c</b></ul>"
    ours, theirs = LexborHTMLParser(source), UpstreamParser(source)
    assert snapshot(ours, "li") == snapshot(theirs, "li")


def test_implicit_p_close_for_block_element():
    source = "<p>before<div>inside</div><p>after"
    ours, theirs = LexborHTMLParser(source), UpstreamParser(source)
    assert [(n.tag, n.text()) for n in ours.body.iter()] == [
        (n.tag, n.text()) for n in theirs.body.iter()
    ]


@pytest.mark.parametrize(
    "source, query",
    [
        ("<dl><dt>a<dd>b<dt>c</dl>", "dt, dd"),
        ("<select><option>a<option>b</select>", "option"),
        ("<table><tr><td>a<td>b<tr><th>c</table>", "tr, td, th"),
    ],
)
def test_other_optional_end_tags_match(source, query):
    ours, theirs = LexborHTMLParser(source), UpstreamParser(source)
    assert snapshot(ours, query) == snapshot(theirs, query)


def test_script_is_scanned_as_raw_text():
    source = "<script>if (a < b) x = '<not-a-tag>';</script><p>done</p>"
    ours, theirs = LexborHTMLParser(source), UpstreamParser(source)
    assert ours.css_first("script").text() == theirs.css_first("script").text()
    assert ours.css_first("p").text() == theirs.css_first("p").text()


@pytest.mark.parametrize(
    "source, query",
    [
        ("<div>1 < 2</div>", "div"),
        ("<a href=/path/to>x</a>", "a"),
        ("<script>&amp; < x</script>", "script"),
        ("<style>&amp;</style>", "style"),
    ],
)
def test_text_less_than_urls_and_raw_entities_match(source, query):
    ours, theirs = LexborHTMLParser(source), UpstreamParser(source)
    assert snapshot(ours, query) == snapshot(theirs, query)


def test_comment_node_navigation_matches():
    source = "<div>a<!--note--><span>b</span></div>"
    ours, theirs = LexborHTMLParser(source), UpstreamParser(source)
    ours_nodes = [(n.tag, n.comment_content) for n in ours.css_first("div").traverse(True)]
    their_nodes = [(n.tag, n.comment_content) for n in theirs.css_first("div").traverse(True)]
    assert ours_nodes == their_nodes


def test_node_navigation_matches():
    source = "<div>left<span>x</span>right<b>y</b></div>"
    ours, theirs = LexborHTMLParser(source), UpstreamParser(source)
    for query in ("div", "span", "b"):
        a, b = ours.css_first(query), theirs.css_first(query)
        attrs = ("tag",)
        assert tuple(getattr(a, name) for name in attrs) == tuple(
            getattr(b, name) for name in attrs
        )
        assert (a.parent and a.parent.tag) == (b.parent and b.parent.tag)
        assert (a.child and a.child.tag) == (b.child and b.child.tag)
        assert (a.prev and a.prev.tag) == (b.prev and b.prev.tag)
        assert (a.next and a.next.tag) == (b.next and b.next.tag)
        assert (a.last_child and a.last_child.tag) == (b.last_child and b.last_child.tag)


def test_iter_and_traverse_match():
    source = "<div> a <span>x</span> <b> y </b></div>"
    ours, theirs = LexborHTMLParser(source), UpstreamParser(source)
    a, b = ours.css_first("div"), theirs.css_first("div")
    assert [(n.tag, n.text(False)) for n in a.iter(True)] == [
        (n.tag, n.text(False)) for n in b.iter(True)
    ]
    assert [(n.tag, n.text(False)) for n in a.traverse(True)] == [
        (n.tag, n.text(False)) for n in b.traverse(True)
    ]


@pytest.mark.parametrize(
    "args",
    [
        (),
        (False,),
        (True, "|", False, False),
        (True, "|", True, False),
        (True, "|", True, True),
    ],
)
def test_text_options_match(args):
    source = "<div> a <span>x</span> <b> y </b></div>"
    ours, theirs = LexborHTMLParser(source), UpstreamParser(source)
    assert ours.css_first("div").text(*args) == theirs.css_first("div").text(*args)


@pytest.mark.parametrize(
    "query",
    [
        "*",
        "DIV",
        "#second",
        ".hot",
        "p.hot.lead",
        "[disabled]",
        "[data-kind=News]",
        "[data-kind^=Ne]",
        "[data-kind$=ws]",
        "[data-kind*=ew]",
        "[class~=lead]",
        "[lang|=en]",
        "[data-kind=news i]",
        "article > p",
        "main p",
        "h2 + p",
        "h2 ~ p",
        "p, h2",
        "p:first-child",
        "p:last-child",
        "p:only-child",
        "p:nth-child(2)",
        "p:nth-child(2n+1)",
        "p:first-of-type",
        "p:last-of-type",
        "p:only-of-type",
        "p:nth-of-type(2)",
        "aside:empty",
        ":root",
        "p:not(.cold)",
    ],
)
def test_css_results_match_lexbor(query):
    source = """
    <main lang="en-US">
      <article>
        <p class="hot lead" data-kind="News">one</p>
        <h2>heading</h2>
        <p id="second" disabled class="hot">two</p>
        <p class="cold">three</p>
      </article>
      <section><p>only</p></section>
      <aside></aside>
    </main>
    """
    ours, theirs = LexborHTMLParser(source), UpstreamParser(source)
    assert [(n.tag, n.id, n.text()) for n in ours.css(query)] == [
        (n.tag, n.id, n.text()) for n in theirs.css(query)
    ]


def test_node_scoped_css_includes_scope_and_descendants():
    source = "<main><article><p>a</p></article></main><p>b</p>"
    ours, theirs = LexborHTMLParser(source), UpstreamParser(source)
    assert [(n.tag, n.text()) for n in ours.css_first("article").css("*")] == [
        (n.tag, n.text()) for n in theirs.css_first("article").css("*")
    ]


def test_css_first_default_and_strict():
    parser = LexborHTMLParser("<p>a</p><p>b</p>")
    marker = object()
    assert parser.css_first(".missing", marker) is marker
    with pytest.raises(ValueError):
        parser.css_first("p", strict=True)


@pytest.mark.parametrize("value", ["four", "five5", "seven77"])
def test_simd_attribute_equality_and_scalar_tail(value):
    source = f"<main><p data-value='{value}'>hit</p><p data-value='other'>miss</p></main>"
    ours, theirs = LexborHTMLParser(source), UpstreamParser(source)
    query = f"[data-value='{value}']"
    assert [(node.tag, node.text()) for node in ours.css(query)] == [
        (node.tag, node.text()) for node in theirs.css(query)
    ]


def test_scoped_selection_stops_at_scope_boundary():
    source = (
        "<main><article><span class='hit'>inside</span></article>"
        "<article><span class='hit'>outside</span></article></main>"
    )
    ours, theirs = LexborHTMLParser(source), UpstreamParser(source)
    ours_scope = ours.css_first("article")
    theirs_scope = theirs.css_first("article")
    assert [node.text() for node in ours_scope.css(".hit")] == [
        node.text() for node in theirs_scope.css(".hit")
    ]


def test_selection_scratch_grows_and_reuses_across_scopes():
    source = (
        "<main><article><i class='hit'>one</i></article>"
        "<section><i class='hit'>two</i><i class='hit'>three</i></section></main>"
    )
    ours, theirs = LexborHTMLParser(source), UpstreamParser(source)
    ours_article = ours.css_first("article")
    theirs_article = theirs.css_first("article")
    ours_section = ours.css_first("section")
    theirs_section = theirs.css_first("section")

    assert [node.text() for node in ours_article.css(".hit")] == [
        node.text() for node in theirs_article.css(".hit")
    ]
    assert [node.text() for node in ours_section.css(".hit")] == [
        node.text() for node in theirs_section.css(".hit")
    ]
    assert [node.text() for node in ours_article.css(".hit")] == ["one"]


def test_selection_scratch_is_isolated_between_threads():
    parser = LexborHTMLParser(
        "<main>" + "".join(
            f"<i class='group-{index % 2}'>{index}</i>" for index in range(200)
        ) + "</main>"
    )

    def select(group: int) -> list[str]:
        expected = [str(index) for index in range(group, 200, 2)]
        for _ in range(10):
            assert [node.text() for node in parser.css(f".group-{group}")] == expected
        return expected

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(select, (0, 1)))
    assert len(results[0]) == len(results[1]) == 100


def test_node_css_matches_includes_descendant():
    source = "<article><span class='hit'>inside</span></article>"
    ours, theirs = LexborHTMLParser(source), UpstreamParser(source)
    ours_article = ours.css_first("article")
    theirs_article = theirs.css_first("article")
    assert ours_article.css_matches(".hit") == theirs_article.css_matches(".hit")
    assert ours_article.css_matches("article") == theirs_article.css_matches("article")


def test_tags_and_css_matches_match():
    source = "<div><script src='/assets/app.js'>const marker = 1</script><p>x</p></div>"
    ours, theirs = LexborHTMLParser(source), UpstreamParser(source)
    assert [n.html for n in ours.tags("script")] == [n.html for n in theirs.tags("script")]
    assert ours.css_matches("div > p") == theirs.css_matches("div > p")
    assert ours.any_css_matches((".none", "script[src]")) == theirs.any_css_matches(
        (".none", "script[src]")
    )


def test_script_helpers():
    parser = LexborHTMLParser(
        "<script src='/static/vendor.js'></script><script>window.token = 7</script>"
    )
    assert parser.scripts_contain("token = 7")
    assert parser.script_srcs_contain(("missing", "vendor"))
    assert not parser.scripts_contain("not present")


def test_clone_is_independent_equivalent_tree():
    parser = LexborHTMLParser("<div><p>x</p></div>")
    cloned = parser.clone()
    assert cloned is not parser
    assert cloned.html == parser.html
    assert cloned.css_first("p").parser is cloned


def test_unsupported_selector_is_explicit():
    with pytest.raises(SelectorError, match="unsupported pseudo-class"):
        LexborHTMLParser("<p>x</p>").css("p:has(span)")


def test_ffi_buffer_validation_rejects_wrong_objects_and_strides():
    import numpy as np

    from mojo_selectolax._lib import addr

    with pytest.raises(TypeError):
        addr(bytearray(b"x"))
    with pytest.raises(ValueError, match="C-contiguous"):
        addr(np.arange(8, dtype=np.uint8)[::2])
