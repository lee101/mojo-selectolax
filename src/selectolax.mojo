"""HTML tokenizer, compact tree builder, and CSS matcher."""

from std.sys.info import simd_width_of

comptime BPtr = UnsafePointer[UInt8, AnyOrigin[mut=True]]
comptime IPtr = UnsafePointer[Int64, AnyOrigin[mut=True]]

comptime NF = 16
comptime AF = 6
comptime SF = 3
comptime CF = 6

comptime K_DOCUMENT = 0
comptime K_ELEMENT = 1
comptime K_TEXT = 2
comptime K_COMMENT = 3

comptime H_HTML = 6385308378
comptime H_HEAD = 6385291639
comptime H_BODY = 6385087027
comptime H_TITLE = 210729019943
comptime H_BASE = 6385072256
comptime H_LINK = 6385440179
comptime H_META = 6385471948
comptime H_STYLE = 210728234774
comptime H_NOSCRIPT = 7572720778618199
comptime H_TEMPLATE = 7572963354976769
comptime H_AREA = 6385054366
comptime H_BR = 5863257
comptime H_COL = 193488579
comptime H_EMBED = 210711355042
comptime H_HR = 5863455
comptime H_IMG = 193495042
comptime H_INPUT = 210716150453
comptime H_PARAM = 210723986230
comptime H_SOURCE = 6954025680758
comptime H_TRACK = 210729322394
comptime H_WBR = 193509936
comptime H_LI = 5863578
comptime H_P = 177685
comptime H_DIV = 193489480
comptime H_MAIN = 6385467242
comptime H_SECTION = 229482434843354
comptime H_ARTICLE = 229459716938729
comptime H_HEADER = 6953582598318
comptime H_FOOTER = 6953516707284
comptime H_NAV = 193500106
comptime H_UL = 5863878
comptime H_OL = 5863680
comptime H_TABLE = 210728712845
comptime H_TR = 5863851
comptime H_TD = 5863837
comptime H_TH = 5863841
comptime H_OPTION = 6953870279774
comptime H_DT = 5863325
comptime H_DD = 5863309
comptime H_SCRIPT = 6954011332538
comptime H_TEXTAREA = 7572963789832483
comptime H_PLAINTEXT = 249902447640336926


def lower(c: UInt8) -> UInt8:
    if c >= UInt8(65) and c <= UInt8(90):
        return c + UInt8(32)
    return c


def is_space(c: UInt8) -> Bool:
    return c == UInt8(32) or (c >= UInt8(9) and c <= UInt8(13))


def is_ascii_alpha(c: UInt8) -> Bool:
    return (c >= UInt8(65) and c <= UInt8(90)) or (c >= UInt8(97) and c <= UInt8(122))


def is_name_end(c: UInt8) -> Bool:
    return is_space(c) or c == UInt8(47) or c == UInt8(62) or c == UInt8(61)


def all_space(src: BPtr, start: Int, end: Int) -> Bool:
    for i in range(start, end):
        if not is_space(src[i]):
            return False
    return True


def hash_lower(src: BPtr, start: Int, length: Int) -> Int:
    var h = UInt64(5381)
    for i in range(length):
        h = (h * UInt64(33) + UInt64(lower(src[start + i]))) & UInt64(0x7FFFFFFFFFFFFFFF)
    return Int(h)


def field(nodes: IPtr, node: Int, offset: Int) -> Int:
    return Int(nodes[node * NF + offset])


def set_field(nodes: IPtr, node: Int, offset: Int, value: Int):
    nodes[node * NF + offset] = Int64(value)


def init_node(
    nodes: IPtr,
    node: Int,
    kind: Int,
    parent: Int,
    tag_start: Int,
    tag_len: Int,
    tag_hash: Int,
    data_start: Int,
    data_len: Int,
    attr_start: Int,
    attr_count: Int,
    raw_start: Int,
    raw_end: Int,
):
    var base = node * NF
    nodes[base] = Int64(kind)
    nodes[base + 1] = Int64(parent)
    nodes[base + 2] = Int64(-1)
    nodes[base + 3] = Int64(-1)
    nodes[base + 4] = Int64(-1)
    nodes[base + 5] = Int64(-1)
    nodes[base + 6] = Int64(tag_start)
    nodes[base + 7] = Int64(tag_len)
    nodes[base + 8] = Int64(tag_hash)
    nodes[base + 9] = Int64(data_start)
    nodes[base + 10] = Int64(data_len)
    nodes[base + 11] = Int64(attr_start)
    nodes[base + 12] = Int64(attr_count)
    nodes[base + 13] = Int64(raw_start)
    nodes[base + 14] = Int64(raw_end)
    nodes[base + 15] = Int64(0)


def attach(nodes: IPtr, parent: Int, child: Int):
    var last = field(nodes, parent, 3)
    set_field(nodes, child, 1, parent)
    set_field(nodes, child, 4, last)
    if last >= 0:
        set_field(nodes, last, 5, child)
    else:
        set_field(nodes, parent, 2, child)
    set_field(nodes, parent, 3, child)


def is_void(h: Int) -> Bool:
    return (
        h == H_AREA or h == H_BASE or h == H_BR or h == H_COL or h == H_EMBED
        or h == H_HR or h == H_IMG or h == H_INPUT or h == H_LINK or h == H_META
        or h == H_PARAM or h == H_SOURCE or h == H_TRACK or h == H_WBR
    )


def is_head_tag(h: Int) -> Bool:
    return (
        h == H_TITLE or h == H_BASE or h == H_LINK or h == H_META or h == H_STYLE
        or h == H_NOSCRIPT or h == H_TEMPLATE
    )


def is_raw_tag(h: Int) -> Bool:
    return h == H_SCRIPT or h == H_STYLE or h == H_TEXTAREA or h == H_TITLE or h == H_PLAINTEXT


def closes_p(h: Int) -> Bool:
    return (
        h == H_P or h == H_DIV or h == H_MAIN or h == H_SECTION or h == H_ARTICLE
        or h == H_HEADER or h == H_FOOTER or h == H_NAV or h == H_UL or h == H_OL
        or h == H_TABLE or h == H_FORM
    )


comptime H_FORM = 6385231225


def implied_parent(nodes: IPtr, current: Int, h: Int) -> Int:
    var cur = current
    if h == H_LI:
        while cur >= 4:
            if field(nodes, cur, 8) == H_LI:
                return field(nodes, cur, 1)
            cur = field(nodes, cur, 1)
    elif h == H_OPTION:
        if cur >= 4 and field(nodes, cur, 8) == H_OPTION:
            return field(nodes, cur, 1)
    elif h == H_TR:
        while cur >= 4:
            if field(nodes, cur, 8) == H_TR:
                return field(nodes, cur, 1)
            cur = field(nodes, cur, 1)
    elif h == H_TD or h == H_TH:
        while cur >= 4:
            if field(nodes, cur, 8) == H_TD or field(nodes, cur, 8) == H_TH:
                return field(nodes, cur, 1)
            cur = field(nodes, cur, 1)
    elif h == H_DT or h == H_DD:
        while cur >= 4:
            var ch = field(nodes, cur, 8)
            if ch == H_DT or ch == H_DD:
                return field(nodes, cur, 1)
            cur = field(nodes, cur, 1)
    if closes_p(h):
        cur = current
        while cur >= 4:
            if field(nodes, cur, 8) == H_P:
                return field(nodes, cur, 1)
            cur = field(nodes, cur, 1)
    return current


def find_raw_close(src: BPtr, n: Int, start: Int, tag_hash: Int) -> Int:
    var i = start
    while i + 3 < n:
        if src[i] == UInt8(60) and src[i + 1] == UInt8(47):
            var s = i + 2
            while s < n and is_space(src[s]):
                s += 1
            var e = s
            while e < n and not is_name_end(src[e]):
                e += 1
            if hash_lower(src, s, e - s) == tag_hash:
                return i
        i += 1
    return n


def emit_text(nodes: IPtr, node_count: Int, parent: Int, start: Int, end: Int) -> Int:
    if end <= start:
        return node_count
    init_node(nodes, node_count, K_TEXT, parent, -1, 0, 0, start, end - start, -1, 0, start, end)
    attach(nodes, parent, node_count)
    return node_count + 1


@export("msx_parse")
def msx_parse(
    src_addr: Int,
    n: Int,
    nodes_addr: Int,
    max_nodes: Int,
    attrs_addr: Int,
    max_attrs: Int,
    meta_addr: Int,
) abi("C") -> Int:
    if (
        src_addr == 0 or nodes_addr == 0 or attrs_addr == 0 or meta_addr == 0
        or n < 0 or max_nodes < 4 or max_attrs < 0
    ):
        return -10
    var src = BPtr(unsafe_from_address=src_addr)
    var nodes = IPtr(unsafe_from_address=nodes_addr)
    var attrs = IPtr(unsafe_from_address=attrs_addr)
    var meta = IPtr(unsafe_from_address=meta_addr)

    init_node(nodes, 0, K_DOCUMENT, -1, -1, 0, 0, -1, 0, -1, 0, 0, n)
    init_node(nodes, 1, K_ELEMENT, 0, -1, 4, H_HTML, -1, 0, -1, 0, 0, n)
    init_node(nodes, 2, K_ELEMENT, 1, -2, 4, H_HEAD, -1, 0, -1, 0, 0, n)
    init_node(nodes, 3, K_ELEMENT, 1, -3, 4, H_BODY, -1, 0, -1, 0, 0, n)
    attach(nodes, 0, 1)
    attach(nodes, 1, 2)
    attach(nodes, 1, 3)

    var node_count = 4
    var attr_count = 0
    var current = 3
    var i = 0
    var explicit_body = False

    while i < n:
        if node_count + 2 >= max_nodes:
            meta[0] = Int64(attr_count)
            meta[1] = Int64(i)
            meta[2] = Int64(1)
            return -1

        if current >= 4 and is_raw_tag(field(nodes, current, 8)):
            var close_pos = find_raw_close(src, n, i, field(nodes, current, 8))
            node_count = emit_text(nodes, node_count, current, i, close_pos)
            i = close_pos
            if i >= n:
                break

        if src[i] != UInt8(60):
            var text_end = i + 1
            while text_end < n and src[text_end] != UInt8(60):
                text_end += 1
            if (current == 1 or current == 2) and not all_space(src, i, text_end):
                current = 3
            if not (
                all_space(src, i, text_end) and (
                    current == 1 or current == 2 or (
                        current == 3 and field(nodes, 3, 2) < 0 and not explicit_body
                    )
                )
            ):
                node_count = emit_text(nodes, node_count, current, i, text_end)
            i = text_end
            continue

        if i + 3 < n and src[i + 1] == UInt8(33) and src[i + 2] == UInt8(45) and src[i + 3] == UInt8(45):
            var end = i + 4
            while end + 2 < n and not (
                src[end] == UInt8(45) and src[end + 1] == UInt8(45) and src[end + 2] == UInt8(62)
            ):
                end += 1
            var content_end = end
            if end + 2 < n:
                end += 3
            else:
                end = n
            init_node(nodes, node_count, K_COMMENT, current, -1, 0, 0, i + 4, content_end - (i + 4), -1, 0, i, end)
            attach(nodes, current, node_count)
            node_count += 1
            i = end
            continue

        if i + 1 < n and src[i + 1] == UInt8(33):
            var end = i + 2
            while end < n and src[end] != UInt8(62):
                end += 1
            i = end + 1 if end < n else n
            continue

        if i + 1 < n and src[i + 1] == UInt8(63):
            var end = i + 2
            while end < n and src[end] != UInt8(62):
                end += 1
            i = end + 1 if end < n else n
            continue

        var closing = i + 1 < n and src[i + 1] == UInt8(47)
        var name_start = i + 2 if closing else i + 1
        if name_start >= n or not is_ascii_alpha(src[name_start]):
            node_count = emit_text(nodes, node_count, current, i, i + 1)
            i += 1
            continue
        var name_end = name_start
        while name_end < n and not is_name_end(src[name_end]):
            name_end += 1
        if name_end == name_start:
            node_count = emit_text(nodes, node_count, current, i, i + 1)
            i += 1
            continue
        var tag_hash = hash_lower(src, name_start, name_end - name_start)

        if closing:
            var end = name_end
            while end < n and src[end] != UInt8(62):
                end += 1
            if end < n:
                end += 1
            var cur = current
            while cur >= 1:
                if field(nodes, cur, 8) == tag_hash:
                    set_field(nodes, cur, 14, end)
                    current = field(nodes, cur, 1)
                    if current < 1:
                        current = 3
                    break
                cur = field(nodes, cur, 1)
            i = end
            continue

        var local_attr_start = attr_count
        var pos = name_end
        var self_closing = False
        while pos < n and src[pos] != UInt8(62):
            while pos < n and is_space(src[pos]):
                pos += 1
            if pos >= n or src[pos] == UInt8(62):
                break
            if src[pos] == UInt8(47):
                self_closing = True
                pos += 1
                continue
            var an_start = pos
            while pos < n and not is_name_end(src[pos]):
                pos += 1
            var an_len = pos - an_start
            if an_len == 0:
                pos += 1
                continue
            while pos < n and is_space(src[pos]):
                pos += 1
            var value_start = -1
            var value_len = -1
            var quote = 0
            if pos < n and src[pos] == UInt8(61):
                pos += 1
                while pos < n and is_space(src[pos]):
                    pos += 1
                if pos < n and (src[pos] == UInt8(34) or src[pos] == UInt8(39)):
                    quote = Int(src[pos])
                    pos += 1
                    value_start = pos
                    while pos < n and Int(src[pos]) != quote:
                        pos += 1
                    value_len = pos - value_start
                    if pos < n:
                        pos += 1
                else:
                    value_start = pos
                    while pos < n and not is_space(src[pos]) and src[pos] != UInt8(62):
                        pos += 1
                    value_len = pos - value_start
            if attr_count >= max_attrs:
                meta[0] = Int64(attr_count)
                meta[1] = Int64(pos)
                meta[2] = Int64(2)
                return -2
            var abase = attr_count * AF
            attrs[abase] = Int64(an_start)
            attrs[abase + 1] = Int64(an_len)
            attrs[abase + 2] = Int64(hash_lower(src, an_start, an_len))
            attrs[abase + 3] = Int64(value_start)
            attrs[abase + 4] = Int64(value_len)
            attrs[abase + 5] = Int64(quote)
            attr_count += 1

        var tag_end = pos + 1 if pos < n else n
        if tag_hash == H_HTML:
            set_field(nodes, 1, 11, local_attr_start)
            set_field(nodes, 1, 12, attr_count - local_attr_start)
            set_field(nodes, 1, 13, i)
            current = 1
        elif tag_hash == H_HEAD:
            set_field(nodes, 2, 11, local_attr_start)
            set_field(nodes, 2, 12, attr_count - local_attr_start)
            set_field(nodes, 2, 13, i)
            current = 2
        elif tag_hash == H_BODY:
            set_field(nodes, 3, 11, local_attr_start)
            set_field(nodes, 3, 12, attr_count - local_attr_start)
            set_field(nodes, 3, 13, i)
            current = 3
            explicit_body = True
        else:
            if current == 2 and not is_head_tag(tag_hash):
                current = 3
            var parent = implied_parent(nodes, current, tag_hash)
            if not explicit_body and current == 3 and field(nodes, 3, 2) < 0 and is_head_tag(tag_hash):
                parent = 2
            current = parent
            init_node(
                nodes, node_count, K_ELEMENT, parent, name_start, name_end - name_start,
                tag_hash, -1, 0, local_attr_start, attr_count - local_attr_start, i, tag_end,
            )
            attach(nodes, parent, node_count)
            if not self_closing and not is_void(tag_hash):
                current = node_count
            node_count += 1
        i = tag_end

    var cur = current
    while cur >= 1:
        if field(nodes, cur, 14) <= field(nodes, cur, 13):
            set_field(nodes, cur, 14, n)
        cur = field(nodes, cur, 1)
    meta[0] = Int64(attr_count)
    meta[1] = Int64(n)
    meta[2] = Int64(0)
    return node_count


def source_query_equal(
    source: BPtr,
    source_start: Int,
    source_len: Int,
    query: BPtr,
    query_start: Int,
    query_len: Int,
    insensitive: Bool,
) -> Bool:
    if source_len != query_len:
        return False
    comptime W = simd_width_of[DType.float64]()
    var i = 0
    if not insensitive:
        while i + W <= source_len:
            var source_vec = source.load[width=W](source_start + i)
            var query_vec = query.load[width=W](query_start + i)
            if not source_vec.eq(query_vec).reduce_and():
                return False
            i += W
    while i < source_len:
        var a = source[source_start + i]
        var b = query[query_start + i]
        if insensitive:
            a = lower(a)
            b = lower(b)
        if a != b:
            return False
        i += 1
    return True


def find_attr(attrs: IPtr, nodes: IPtr, node: Int, name_hash: Int) -> Int:
    var start = field(nodes, node, 11)
    var count = field(nodes, node, 12)
    for i in range(count):
        var attr = start + i
        if Int(attrs[attr * AF + 2]) == name_hash:
            return attr
    return -1


def word_contains(source: BPtr, start: Int, length: Int, query: BPtr, qstart: Int, qlen: Int) -> Bool:
    var i = 0
    while i < length:
        while i < length and is_space(source[start + i]):
            i += 1
        var s = i
        while i < length and not is_space(source[start + i]):
            i += 1
        if source_query_equal(source, start + s, i - s, query, qstart, qlen, False):
            return True
    return False


def bytes_contains(
    source: BPtr, start: Int, length: Int, query: BPtr, qstart: Int, qlen: Int, insensitive: Bool
) -> Bool:
    if qlen == 0:
        return True
    if qlen > length:
        return False
    for i in range(length - qlen + 1):
        if source_query_equal(source, start + i, qlen, query, qstart, qlen, insensitive):
            return True
    return False


def element_position(nodes: IPtr, node: Int, of_type: Bool) -> Int:
    var pos = 1
    var prev = field(nodes, node, 4)
    var h = field(nodes, node, 8)
    while prev >= 0:
        if field(nodes, prev, 0) == K_ELEMENT and (not of_type or field(nodes, prev, 8) == h):
            pos += 1
        prev = field(nodes, prev, 4)
    return pos


def element_reverse_position(nodes: IPtr, node: Int, of_type: Bool) -> Int:
    var pos = 1
    var nxt = field(nodes, node, 5)
    var h = field(nodes, node, 8)
    while nxt >= 0:
        if field(nodes, nxt, 0) == K_ELEMENT and (not of_type or field(nodes, nxt, 8) == h):
            pos += 1
        nxt = field(nodes, nxt, 5)
    return pos


def nth_matches(pos: Int, a: Int, b: Int) -> Bool:
    if a == 0:
        return pos == b
    var delta = pos - b
    return delta % a == 0 and delta // a >= 0


def condition_matches(
    source: BPtr,
    nodes: IPtr,
    attrs: IPtr,
    node: Int,
    conds: IPtr,
    cond: Int,
    query: BPtr,
) -> Bool:
    var base = cond * CF
    var raw_op = Int(conds[base])
    var negate = raw_op < 0
    var op = -raw_op if negate else raw_op
    var arg = Int(conds[base + 1])
    var qstart = Int(conds[base + 2])
    var qlen = Int(conds[base + 3])
    var a = Int(conds[base + 4])
    var b = Int(conds[base + 5])
    var matched = False

    if op == 1:
        matched = field(nodes, node, 8) == arg
    elif op >= 2 and op <= 9:
        var attr = find_attr(attrs, nodes, node, arg)
        if op == 2:
            matched = attr >= 0
        elif attr >= 0:
            var value_start = Int(attrs[attr * AF + 3])
            var value_len = Int(attrs[attr * AF + 4])
            if value_len < 0:
                value_len = 0
                value_start = 0
            if op == 3:
                matched = source_query_equal(source, value_start, value_len, query, qstart, qlen, False)
            elif op == 4:
                matched = value_len >= qlen and source_query_equal(source, value_start, qlen, query, qstart, qlen, False)
            elif op == 5:
                matched = value_len >= qlen and source_query_equal(source, value_start + value_len - qlen, qlen, query, qstart, qlen, False)
            elif op == 6:
                matched = bytes_contains(source, value_start, value_len, query, qstart, qlen, False)
            elif op == 7:
                matched = word_contains(source, value_start, value_len, query, qstart, qlen)
            elif op == 8:
                matched = (
                    source_query_equal(source, value_start, value_len, query, qstart, qlen, False)
                    or (
                        value_len > qlen and source[value_start + qlen] == UInt8(45)
                        and source_query_equal(source, value_start, qlen, query, qstart, qlen, False)
                    )
                )
            else:
                matched = source_query_equal(source, value_start, value_len, query, qstart, qlen, True)
    elif op == 20:
        matched = element_position(nodes, node, False) == 1
    elif op == 21:
        matched = element_reverse_position(nodes, node, False) == 1
    elif op == 22:
        matched = element_position(nodes, node, False) == 1 and element_reverse_position(nodes, node, False) == 1
    elif op == 23:
        matched = nth_matches(element_position(nodes, node, False), a, b)
    elif op == 24:
        matched = element_position(nodes, node, True) == 1
    elif op == 25:
        matched = element_reverse_position(nodes, node, True) == 1
    elif op == 26:
        matched = element_position(nodes, node, True) == 1 and element_reverse_position(nodes, node, True) == 1
    elif op == 27:
        matched = nth_matches(element_position(nodes, node, True), a, b)
    elif op == 28:
        var child = field(nodes, node, 2)
        matched = True
        while child >= 0:
            if field(nodes, child, 0) == K_ELEMENT or (
                field(nodes, child, 0) == K_TEXT and field(nodes, child, 10) > 0
            ):
                matched = False
                break
            child = field(nodes, child, 5)
    elif op == 29:
        matched = node == 1

    return not matched if negate else matched


def compound_matches(
    source: BPtr,
    nodes: IPtr,
    attrs: IPtr,
    node: Int,
    steps: IPtr,
    step: Int,
    conds: IPtr,
    query: BPtr,
) -> Bool:
    if node < 1 or field(nodes, node, 0) != K_ELEMENT:
        return False
    var start = Int(steps[step * SF])
    var count = Int(steps[step * SF + 1])
    for i in range(count):
        if not condition_matches(source, nodes, attrs, node, conds, start + i, query):
            return False
    return True


def previous_element(nodes: IPtr, node: Int) -> Int:
    var prev = field(nodes, node, 4)
    while prev >= 0 and field(nodes, prev, 0) != K_ELEMENT:
        prev = field(nodes, prev, 4)
    return prev


def chain_matches(
    source: BPtr,
    nodes: IPtr,
    attrs: IPtr,
    node: Int,
    steps: IPtr,
    step: Int,
    end_step: Int,
    conds: IPtr,
    query: BPtr,
) -> Bool:
    if not compound_matches(source, nodes, attrs, node, steps, step, conds, query):
        return False
    if step + 1 >= end_step:
        return True
    var comb = Int(steps[step * SF + 2])
    if comb == 2:
        return chain_matches(source, nodes, attrs, field(nodes, node, 1), steps, step + 1, end_step, conds, query)
    if comb == 3:
        return chain_matches(source, nodes, attrs, previous_element(nodes, node), steps, step + 1, end_step, conds, query)
    if comb == 4:
        var prev = previous_element(nodes, node)
        while prev >= 0:
            if chain_matches(source, nodes, attrs, prev, steps, step + 1, end_step, conds, query):
                return True
            prev = previous_element(nodes, prev)
        return False
    var parent = field(nodes, node, 1)
    while parent >= 1:
        if chain_matches(source, nodes, attrs, parent, steps, step + 1, end_step, conds, query):
            return True
        parent = field(nodes, parent, 1)
    return False


def select_first(
    source: BPtr,
    nodes: IPtr,
    attrs: IPtr,
    steps: IPtr,
    groups: IPtr,
    group_count: Int,
    conds: IPtr,
    query: BPtr,
    scope: Int,
) -> Int:
    var node = scope if scope > 0 else 1
    while node >= 1:
        if field(nodes, node, 0) == K_ELEMENT:
            for group in range(group_count):
                var start = Int(groups[group * 2])
                var end = start + Int(groups[group * 2 + 1])
                if chain_matches(source, nodes, attrs, node, steps, start, end, conds, query):
                    return node

        var child = field(nodes, node, 2)
        if child >= 0:
            node = child
            continue
        while node >= 1 and field(nodes, node, 5) < 0:
            if scope > 0 and node == scope:
                return -1
            node = field(nodes, node, 1)
        if node >= 1:
            if scope > 0 and node == scope:
                return -1
            node = field(nodes, node, 5)
    return -1


@export("msx_subtree_count")
def msx_subtree_count(nodes_addr: Int, node_count: Int, scope: Int) abi("C") -> Int:
    if nodes_addr == 0 or node_count < 4 or scope < 1 or scope >= node_count:
        return -1
    var nodes = IPtr(unsafe_from_address=nodes_addr)
    var count = 0
    var node = scope
    while node >= 1:
        count += 1
        var child = field(nodes, node, 2)
        if child >= 0:
            node = child
            continue
        while node >= 1 and field(nodes, node, 5) < 0:
            if node == scope:
                return count
            node = field(nodes, node, 1)
        if node >= 1:
            if node == scope:
                return count
            node = field(nodes, node, 5)
    return count


@export("msx_select_first")
def msx_select_first(
    source_addr: Int,
    nodes_addr: Int,
    node_count: Int,
    attrs_addr: Int,
    steps_addr: Int,
    groups_addr: Int,
    group_count: Int,
    conds_addr: Int,
    query_addr: Int,
    scope: Int,
) abi("C") -> Int:
    if (
        source_addr == 0 or nodes_addr == 0 or attrs_addr == 0 or steps_addr == 0
        or groups_addr == 0 or conds_addr == 0 or query_addr == 0
        or node_count < 4 or group_count <= 0
        or scope < 0 or scope >= node_count
    ):
        return -2
    return select_first(
        BPtr(unsafe_from_address=source_addr),
        IPtr(unsafe_from_address=nodes_addr),
        IPtr(unsafe_from_address=attrs_addr),
        IPtr(unsafe_from_address=steps_addr),
        IPtr(unsafe_from_address=groups_addr),
        group_count,
        IPtr(unsafe_from_address=conds_addr),
        BPtr(unsafe_from_address=query_addr),
        scope,
    )


@export("msx_select")
def msx_select(
    source_addr: Int,
    nodes_addr: Int,
    node_count: Int,
    attrs_addr: Int,
    steps_addr: Int,
    groups_addr: Int,
    group_count: Int,
    conds_addr: Int,
    query_addr: Int,
    results_addr: Int,
    result_capacity: Int,
    scope: Int,
) abi("C") -> Int:
    if (
        source_addr == 0 or nodes_addr == 0 or attrs_addr == 0 or steps_addr == 0
        or groups_addr == 0 or conds_addr == 0 or query_addr == 0
        or results_addr == 0 or node_count < 4 or group_count <= 0
        or result_capacity < 0 or scope < 0 or scope >= node_count
    ):
        return -1
    var source = BPtr(unsafe_from_address=source_addr)
    var nodes = IPtr(unsafe_from_address=nodes_addr)
    var attrs = IPtr(unsafe_from_address=attrs_addr)
    var steps = IPtr(unsafe_from_address=steps_addr)
    var groups = IPtr(unsafe_from_address=groups_addr)
    var conds = IPtr(unsafe_from_address=conds_addr)
    var query = BPtr(unsafe_from_address=query_addr)
    var results = IPtr(unsafe_from_address=results_addr)
    var count = 0
    var node = scope if scope > 0 else 1
    while node >= 1:
        if field(nodes, node, 0) != K_ELEMENT:
            pass
        else:
            var matched = False
            for group in range(group_count):
                var start = Int(groups[group * 2])
                var end = start + Int(groups[group * 2 + 1])
                if chain_matches(source, nodes, attrs, node, steps, start, end, conds, query):
                    matched = True
                    break
            if matched:
                if count < result_capacity:
                    results[count] = Int64(node)
                count += 1
                if count >= result_capacity:
                    return count

        var child = field(nodes, node, 2)
        if child >= 0:
            node = child
            continue
        while node >= 1 and field(nodes, node, 5) < 0:
            if scope > 0 and node == scope:
                return count
            node = field(nodes, node, 1)
        if node >= 1:
            if scope > 0 and node == scope:
                return count
            node = field(nodes, node, 5)
    return count
