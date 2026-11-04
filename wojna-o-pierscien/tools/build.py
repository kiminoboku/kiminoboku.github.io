"""Builds index.html from the source files in src/.

Usage: python3 tools/build.py
Exits with an error (code 1) if any link does not point to an existing entry.

Source file syntax
------------------
The markup keywords below are Polish because the content in src/ is Polish.

Glossary (src/glosariusz-*.txt):
    @@ Entry title             starts an entry
    grupa: Word                (optional) group of entries sharing the same first word
    strony: 27–28              pages of the original rulebook
    klucze: a, b               (optional) extra names that links can use (not displayed)
    <blocks>                   definition (up to the first ## heading)
    ## Zasady / ## Wyjątki i szczególne przypadki / ## Przykład ...
    ~ Other name -> Entry title [| Group]   alias entry pointing to the main entry

Rules (src/instrukcja.txt):
    # Chapter, ## Subchapter, followed by blocks as described below.

Blocks: paragraphs, "- " lists (nest with 2 spaces), "1. " lists, "| a | b |" tables,
    "!img file [+ file2] | caption", boxes "::: kind Title" ... ":::"
    (kind: skrot = summary, uwaga = note, przyklad = example).
Inline: **bold**, *italic*, [[Entry]] or [[Entry|text]], {{icon}} (file from img/).
"""
from __future__ import annotations

import html
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
IMG = ROOT / "img"

ERRORS: list[str] = []

# ---------------------------------------------------------------- helpers

PL_MAP = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")
# Polish alphabetical order, used for sorting and for letter anchors
ALPHABET = "0123456789aąbcćdeęfghijklłmnńoópqrsśtuvwxyzźż"


def slug(text: str) -> str:
    t = text.translate(PL_MAP)
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")


def sort_key(text: str) -> list[int]:
    key = []
    for ch in text.lower():
        if ch in ALPHABET:
            key.append(ALPHABET.index(ch) + 2)
        elif ch == " ":
            key.append(1)
        elif ch in "ûü":
            key.append(ALPHABET.index("u") + 2)
    return key


def norm_key(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def first_letter(text: str) -> str:
    for ch in text:
        if ch.isalpha():
            return ch.upper()
    return "#"


# ---------------------------------------------------------------- model


@dataclass
class Entry:
    title: str
    file: str
    group: str | None = None
    pages: str = ""
    keys: list[str] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    id: str = ""
    related: list[str] = field(default_factory=list)


@dataclass
class Alias:
    name: str
    target: str
    group: str | None
    file: str
    id: str = ""


ENTRIES: dict[str, Entry] = {}
ALIASES: list[Alias] = []
LINK_INDEX: dict[str, str] = {}  # normalized name -> id of the main entry


def parse_glossary(path: Path) -> None:
    cur: Entry | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if line.startswith("@@ "):
            cur = Entry(title=line[3:].strip(), file=path.name)
            if cur.title in ENTRIES:
                ERRORS.append(f"{path.name}: duplicate entry '{cur.title}'")
            ENTRIES[cur.title] = cur
            continue
        if line.startswith("~ "):
            m = re.match(r"~ (.+?) -> (.+?)(?: \| (.+))?$", line)
            if not m:
                ERRORS.append(f"{path.name}: malformed alias: {line}")
                continue
            ALIASES.append(Alias(m.group(1).strip(), m.group(2).strip(),
                                 m.group(3).strip() if m.group(3) else None, path.name))
            continue
        if cur is None:
            continue
        # entry fields: grupa = group, strony = pages, klucze = extra link keys
        m = re.match(r"(grupa|strony|klucze): (.*)$", line)
        if m and not cur.lines:
            k, v = m.groups()
            if k == "grupa":
                cur.group = v.strip()
            elif k == "strony":
                cur.pages = v.strip()
            else:
                cur.keys = [x.strip() for x in v.split(",") if x.strip()]
            continue
        cur.lines.append(line)


def build_index() -> None:
    used_ids: set[str] = set()
    for e in ENTRIES.values():
        e.id = "g-" + slug(e.title)
        if e.id in used_ids:
            ERRORS.append(f"duplicate id {e.id}")
        used_ids.add(e.id)
        for k in [e.title, *e.keys]:
            LINK_INDEX[norm_key(k)] = e.id
    for a in ALIASES:
        a.id = "g-" + slug(a.name)
        if a.id in used_ids:
            ERRORS.append(f"duplicate alias id {a.id}")
        used_ids.add(a.id)
        target = ENTRIES.get(a.target)
        if not target:
            ERRORS.append(f"{a.file}: alias '{a.name}' points to a missing entry '{a.target}'")
            continue
        LINK_INDEX.setdefault(norm_key(a.name), target.id)


ID_TO_ENTRY: dict[str, Entry] = {}

# ---------------------------------------------------------------- inline markup


class Ctx:
    """Rendering context: collects links to related entries."""

    def __init__(self, where: str, self_id: str | None = None):
        self.where = where
        self.self_id = self_id
        self.links: list[str] = []


def find_image(name: str) -> str | None:
    for ext in (".png", ".jpg"):
        f = IMG / f"{name}{ext}"
        if f.exists():
            return f"img/{name}{ext}?v={int(f.stat().st_mtime)}"
    return None


def inline(text: str, ctx: Ctx) -> str:
    out = html.escape(text, quote=False)

    def link(m: re.Match) -> str:
        target, _, label = m.group(1).partition("|")
        label = label or target
        tid = LINK_INDEX.get(norm_key(html.unescape(target)))
        if not tid:
            ERRORS.append(f"{ctx.where}: unknown entry in link [[{html.unescape(target)}]]")
            return label
        if tid != ctx.self_id and tid not in ctx.links:
            ctx.links.append(tid)
        return f'<a class="term" href="#{tid}">{label}</a>'

    def icon(m: re.Match) -> str:
        src = find_image(m.group(1))
        if not src:
            ERRORS.append(f"{ctx.where}: missing image {{{{{m.group(1)}}}}}")
            return ""
        return f'<img class="icon" src="{src}" alt="">'

    out = re.sub(r"\[\[(.+?)\]\]", link, out)
    out = re.sub(r"\{\{([\w-]+)\}\}", icon, out)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", out)
    return out


# ---------------------------------------------------------------- blocks

# box kind used in src -> (CSS class, default heading shown on the page)
BOX_KINDS = {
    "skrot": ("summary", "W skrócie"),
    "uwaga": ("note", "Uwaga"),
    "przyklad": ("example", "Przykład"),
}


def render_blocks(lines: list[str], ctx: Ctx) -> str:
    out: list[str] = []
    i = 0
    n = len(lines)
    para: list[str] = []

    def flush_para() -> None:
        if para:
            out.append(f"<p>{inline(' '.join(para), ctx)}</p>")
            para.clear()

    while i < n:
        line = lines[i]
        s = line.strip()
        if not s:
            flush_para()
            i += 1
            continue
        if s.startswith(":::") and s != ":::":
            flush_para()
            kind, _, title = s[3:].strip().partition(" ")
            depth, j = 1, i + 1
            while j < n:
                t = lines[j].strip()
                if t.startswith(":::"):
                    depth += -1 if t == ":::" else 1
                    if depth == 0:
                        break
                j += 1
            if kind not in BOX_KINDS:
                ERRORS.append(f"{ctx.where}: unknown box kind '{kind}'")
            css, default_title = BOX_KINDS.get(kind, ("note", ""))
            inner = render_blocks(lines[i + 1:j], ctx)
            head = inline(title, ctx) if title else default_title
            out.append(f'<aside class="box box-{css}"><h5>{head}</h5>{inner}</aside>')
            i = j + 1
            continue
        if s.startswith("!img "):
            flush_para()
            spec, _, caption = s[5:].partition("|")
            imgs = []
            for name in [x.strip() for x in spec.split("+")]:
                src = find_image(name)
                if not src:
                    ERRORS.append(f"{ctx.where}: missing image {name}")
                    continue
                alt = html.escape(caption.strip() or name)
                imgs.append(f'<a href="{src}" target="_blank" rel="noopener">'
                            f'<img src="{src}" alt="{alt}" loading="lazy"></a>')
            cls = "fig fig-pair" if len(imgs) > 1 else "fig"
            cap = f"<figcaption>{inline(caption.strip(), ctx)}</figcaption>" if caption.strip() else ""
            out.append(f'<figure class="{cls}"><div class="fig-imgs">{"".join(imgs)}</div>{cap}</figure>')
            i += 1
            continue
        if s.startswith("|"):
            flush_para()
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                # a "|" inside [[link|text]] does not split cells
                row = re.sub(r"\[\[[^\]]*\]\]", lambda m: m.group(0).replace("|", "\x00"), lines[i].strip())
                cells = [c.strip().replace("\x00", "|") for c in row.strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            head, *body = rows
            th = "".join(f"<th>{inline(c, ctx)}</th>" for c in head)
            trs = "".join("<tr>" + "".join(f"<td>{inline(c, ctx)}</td>" for c in r) + "</tr>" for r in body)
            out.append(f'<div class="table-wrap"><table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>')
            continue
        m = re.match(r"(\s*)(- |\d+\. )", line)
        if m:
            flush_para()
            html_list, i = render_list(lines, i, ctx)
            out.append(html_list)
            continue
        para.append(s)
        i += 1
    flush_para()
    return "".join(out)


def render_list(lines: list[str], i: int, ctx: Ctx) -> tuple[str, int]:
    first = re.match(r"(\s*)(- |\d+\. )", lines[i])
    indent = len(first.group(1))
    tag = "ul" if first.group(2) == "- " else "ol"
    items: list[list[str]] = []
    nested: list[str] = []
    n = len(lines)
    while i < n:
        line = lines[i]
        if not line.strip():
            # a blank line ends the list unless the next line is another item of this list
            j = i + 1
            if j < n and re.match(r"\s{%d}(- |\d+\. )" % indent, lines[j]) and \
                    len(re.match(r"(\s*)", lines[j]).group(1)) == indent:
                i = j
                continue
            break
        m = re.match(r"(\s*)(- |\d+\. )(.*)", line)
        lead = len(re.match(r"(\s*)", line).group(1))
        if m and lead == indent:
            items.append([m.group(3)])
            nested.append("")
            i += 1
        elif m and lead > indent:
            sub, i = render_list(lines, i, ctx)
            nested[-1] += sub
        elif lead > indent and items:
            items[-1].append(line.strip())
            i += 1
        else:
            break
    lis = "".join(f"<li>{inline(' '.join(it), ctx)}{sub}</li>" for it, sub in zip(items, nested))
    return f"<{tag}>{lis}</{tag}>", i


# ---------------------------------------------------------------- glossary


def split_sections(lines: list[str]) -> tuple[list[str], list[tuple[str, list[str]]]]:
    definition: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    for line in lines:
        if line.startswith("## "):
            sections.append((line[3:].strip(), []))
        elif sections:
            sections[-1][1].append(line)
        else:
            definition.append(line)
    return definition, sections


# chain icon for the "copy link" button; SVG attributes are not inline styles, so this is CSP-safe
LINK_ICON = ('<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" '
             'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
             '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>'
             '<path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>')


def render_entry(e: Entry) -> str:
    ctx = Ctx(f"{e.file} / {e.title}", e.id)
    definition, sections = split_sections(e.lines)
    if not any(x.strip() for x in definition):
        ERRORS.append(f"{ctx.where}: missing definition")
    parts = [f'<div class="def">{render_blocks(definition, ctx)}</div>']
    for title, body in sections:
        parts.append(f'<section><h4>{html.escape(title)}</h4>{render_blocks(body, ctx)}</section>')
    e.related = ctx.links
    if not e.related:
        ERRORS.append(f"{ctx.where}: no related entries")
    chips = "".join(f'<li><a class="chip term" href="#{rid}">{html.escape(ID_TO_ENTRY[rid].title)}</a></li>'
                    for rid in e.related)
    pages = f'<span class="pages">instrukcja s. {html.escape(e.pages)}</span>' if e.pages else ""
    search = html.escape(" ".join([e.title, *e.keys, *[a.name for a in ALIASES if a.target == e.title]]))
    copy = (f'<button type="button" class="copy-link" data-anchor="{e.id}" '
            f'title="Kopiuj link do hasła" aria-label="Kopiuj link do hasła {html.escape(e.title)}">'
            f'{LINK_ICON}</button>')
    return (f'<article class="entry" id="{e.id}" data-search="{search}">'
            f'<h3><span class="t">{html.escape(e.title)}</span>{copy}{pages}</h3>{"".join(parts)}'
            f'<footer class="related"><h4>Powiązane hasła</h4><ul>{chips}</ul></footer></article>')


def render_alias(a: Alias) -> str:
    t = ENTRIES.get(a.target)
    if not t:
        return ""
    return (f'<div class="alias" id="{a.id}" data-search="{html.escape(a.name)}">'
            f'<span class="alias-name">{html.escape(a.name)}</span> '
            f'<span class="arrow" aria-hidden="true">→</span> <span class="sr">patrz</span> '
            f'<a class="term" href="#{t.id}">{html.escape(t.title)}</a></div>')


def render_glossary() -> tuple[str, str]:
    # top-level items: ungrouped entries, ungrouped aliases, and groups
    items: list[tuple[str, str, str]] = []  # (sort key, letter, html)
    groups: dict[str, list[tuple[str, str, bool]]] = {}
    for e in ENTRIES.values():
        body = render_entry(e)
        if e.group:
            groups.setdefault(e.group, []).append((e.title, body, e.title == e.group))
        else:
            items.append((e.title, first_letter(e.title), body))
    for a in ALIASES:
        body = render_alias(a)
        if a.group:
            groups.setdefault(a.group, []).append((a.name, body, False))
        else:
            items.append((a.name, first_letter(a.name), body))
    for g, members in groups.items():
        members.sort(key=lambda m: (not m[2], sort_key(m[0])))
        if len(members) < 2:
            ERRORS.append(f"group '{g}' has fewer than 2 members")
        head_entry = ENTRIES.get(g)
        head = (f'<a class="term" href="#{head_entry.id}">{html.escape(g)}</a>'
                if head_entry and head_entry.group == g else html.escape(g))
        names = html.escape(" ".join(m[0] for m in members))
        items.append((g, first_letter(g),
                      f'<section class="group" data-search="{names}"><h3 class="group-title">'
                      f'<span class="group-mark" aria-hidden="true">▸</span> {head}</h3>'
                      f'<div class="group-body">{"".join(m[1] for m in members)}</div></section>'))
    items.sort(key=lambda x: sort_key(x[0]))
    letters: dict[str, list[str]] = {}
    for _, letter, body in items:
        letters.setdefault(letter, []).append(body)
    order = sorted(letters, key=sort_key)

    def lid(L: str) -> str:  # Z and Ż need different anchors
        return f"letter-{ALPHABET.index(L.lower()) if L.lower() in ALPHABET else slug(L)}"
    sections = "".join(f'<section class="letter" id="{lid(L)}"><h2>{L}</h2>{"".join(letters[L])}</section>'
                       for L in order)
    nav = "".join(f'<a href="#{lid(L)}">{L}</a>' for L in order)
    return sections, nav


# ---------------------------------------------------------------- rules


def render_rules() -> tuple[str, str]:
    path = SRC / "instrukcja.txt"
    chapters: list[tuple[int, str, list[str]]] = []
    intro: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"(#{1,2}) (.+)$", line)
        if m:
            chapters.append((len(m.group(1)), m.group(2).strip(), []))
        elif chapters:
            chapters[-1][2].append(line)
        else:
            intro.append(line)
    ctx = Ctx(path.name)
    body = [render_blocks(intro, ctx)]
    toc: list[str] = []
    num = 0
    for level, title, lines in chapters:
        hid = "i-" + slug(title)
        ctx.where = f"{path.name} / {title}"
        if level == 1:
            num += 1
            if body and toc:
                body.append("</section>")
            body.append(f'<section class="chapter"><h2 id="{hid}"><span class="num">{num}.</span> '
                        f'{inline(title, ctx)}</h2>')
            toc.append(f'<li class="toc-1"><a href="#{hid}">{num}. {html.escape(title)}</a></li>')
        else:
            body.append(f'<h3 id="{hid}">{inline(title, ctx)}</h3>')
            toc.append(f'<li class="toc-2"><a href="#{hid}">{html.escape(title)}</a></li>')
        body.append(render_blocks(lines, ctx))
    body.append("</section>")
    return "".join(body), "".join(toc)


# ---------------------------------------------------------------- page

# The page text is Polish; ids, classes and comments are English.
PAGE = """<!DOCTYPE html>
<html lang="pl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<!-- Static page opened locally (file://), so there is no server that could send a CSP header.
     The code uses no inline scripts or styles and no eval, so when hosting it on a server, send:
     Content-Security-Policy: default-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self' -->
<title>Wojna o Pierścień — zasady gry</title>
<link rel="stylesheet" href="style.css?v=__V_CSS__">
<script src="app.js?v=__V_JS__" defer></script>
</head>
<body>
<header class="top">
  <div class="brand">Wojna o Pierścień <span>zasady gry · 2. edycja</span></div>
  <nav class="tabs" role="tablist">
    <a href="#rules" class="tab" data-tab="rules" role="tab">Instrukcja</a>
    <a href="#glossary" class="tab" data-tab="glossary" role="tab">Glosariusz</a>
  </nav>
</header>
<div class="panel" id="rules">
  <nav class="side" aria-label="Spis treści"><h2>Spis treści</h2><ol class="toc">__TOC__</ol></nav>
  <main class="content rules">__RULES__</main>
</div>
<div class="panel" id="glossary">
  <nav class="side" aria-label="Indeks glosariusza">
    <h2>Glosariusz</h2>
    <label class="search"><span class="sr">Szukaj hasła</span>
      <input id="search" type="search" placeholder="Szukaj hasła…" autocomplete="off"></label>
    <label class="search-full"><input id="search-full-text" type="checkbox"> szukaj także w treści</label>
    <p class="count" id="result-count"></p>
    <div class="letters">__LETTERS__</div>
  </nav>
  <main class="content gloss">
    <p class="gloss-intro">__COUNT__ Hasła o wspólnym pierwszym słowie są zebrane w grupy (▸).
    Hasła zapisane kursywą są odsyłaczami do hasła głównego.</p>
    <p class="empty" id="no-results" hidden>Brak haseł pasujących do wyszukiwania.</p>
    __GLOSS__
  </main>
</div>
<footer class="bottom">Opracowanie na podstawie instrukcji „Wojna o Pierścień — Druga edycja” (Ares Games, wyd. polskie Galakta).
Numery stron odnoszą się do oryginalnej instrukcji. Grafiki pochodzą z instrukcji.</footer>
</body>
</html>
"""


def mtime(name: str) -> str:
    return str(int((ROOT / name).stat().st_mtime))


def main() -> int:
    for p in sorted(SRC.glob("glosariusz-*.txt")):
        parse_glossary(p)
    build_index()
    ID_TO_ENTRY.update({e.id: e for e in ENTRIES.values()})
    gloss, letters = render_glossary()
    rules, toc = render_rules()
    count = f"Glosariusz zawiera {len(ENTRIES)} haseł i {len(ALIASES)} odsyłaczy."
    page = (PAGE.replace("__TOC__", toc).replace("__RULES__", rules)
            .replace("__LETTERS__", letters)
            .replace("__V_CSS__", mtime("style.css")).replace("__V_JS__", mtime("app.js"))
            .replace("__GLOSS__", gloss).replace("__COUNT__", count))
    if "style=" in page or re.search(r"<script(?![^>]*\bsrc=)", page):
        ERRORS.append("page contains inline styles or scripts (not CSP-compliant)")
    linked = {rid for e in ENTRIES.values() for rid in e.related}
    orphans = [e.title for e in ENTRIES.values() if e.id not in linked]
    (ROOT / "index.html").write_text(page, encoding="utf-8")
    groups = {e.group for e in ENTRIES.values() if e.group} | {a.group for a in ALIASES if a.group}
    print(f"entries: {len(ENTRIES)}, aliases: {len(ALIASES)}, groups: {len(groups)}")
    if orphans:
        print("entries no other entry links to:", ", ".join(orphans))
    if ERRORS:
        print(f"\nERRORS ({len(ERRORS)}):")
        for err in ERRORS:
            print(" -", err)
        return 1
    print("OK: all links are valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
