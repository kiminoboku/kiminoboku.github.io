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
    zrodlo: text               (optional) source shown instead of "instrukcja", e.g. a variant leaflet
    klucze: a, b               (optional) extra names that links can use (not displayed)
    powiazane: Entry, Entry    (optional) extra related entries that the text does not link to
    <blocks>                   definition (up to the first ## heading)
    ## Zasady / ## Wyjątki i szczególne przypadki / ## Przykład ...
    ~ Other name -> Entry title [| Group]   alias entry pointing to the main entry

Rules (src/instrukcja.txt):
    # Chapter, ## Subchapter, followed by blocks as described below.

Lords (src/wladcy.txt):
    # Section                  e.g. the base game; blocks before the first @@ are the section intro
    @@ Lord name               starts a Lord
    frakcja: Bestie            faction (Bestie, Duchy, Nieumarli, Śmiertelnicy)
    zycie: 45                  starting life
    tytul: Wilk Alfa           title printed on the Lord sheet
    strony: 3, 9               (optional) pages of the rulebook that show the Lord
    ## Zdolność (tekst z arkusza)   the first section: the text printed on the Lord sheet;
                               its first paragraph is the link preview
    ## Zasoby / ## Przygotowanie / ## Zasady specjalne ...

Expansions (keys: tomb = Gadzi Grobowiec, gate = Słudzy Czarnej Bramy):
    dodatek: tomb              field on a glossary entry or Lord: shown only with that expansion
    # Title {tomb}             suffix on a chapter, subchapter, ## section or Lord section
    ::: dodatek tomb Title     box shown only with that expansion
    A condition joins keys with "+" (all required); one "+" part may list alternatives with "|"
    (any of them); "!key" means "only without that expansion", e.g. {tomb+gate},
    dodatek: tomb|gate or dodatek: !gate.
    Aliases inherit their target's condition.
    Links must not point to content that can be hidden while the linking text is visible.

Blocks: paragraphs, "- " lists (nest with 2 spaces), "1. " lists, "| a | b |" tables,
    "!img file [+ file2] | caption", boxes "::: kind Title" ... ":::"
    (kind: skrot = summary, uwaga = note, przyklad = example).
Inline: **bold**, *italic*, [[Entry]] or [[Entry|text]], [[władca: Lord]] or [[władca: Lord|text]]
    (link to a Lord), {{icon}} (file from img/; ICON_NAMES gives its spoken name).
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
        else:  # letters from outside the Polish alphabet (é, ú) sort as their base letter
            base = unicodedata.normalize("NFKD", ch)[0]
            if base in ALPHABET:
                key.append(ALPHABET.index(base) + 2)
    return key


def norm_key(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def first_letter(text: str) -> str:
    for ch in text:
        if ch.isalpha():
            return ch.upper()
    return "#"


# ---------------------------------------------------------------- expansions

# expansion key used in src -> name shown on the page
EXPANSIONS = {
    "tomb": "Gadzi Grobowiec",
    "gate": "Słudzy Czarnej Bramy",
}
USED_EXPANSIONS: set[str] = set()


@dataclass(frozen=True)
class Cond:
    """When content is visible: all `req` expansions selected, none of `nots`,
    and (if `any` is not empty) at least one of `any`."""
    req: frozenset = frozenset()
    nots: frozenset = frozenset()
    any: frozenset = frozenset()

    def __bool__(self) -> bool:
        return bool(self.req or self.nots or self.any)

    def __or__(self, other: "Cond") -> "Cond":
        if self.any and other.any and self.any != other.any:
            ERRORS.append(f"cannot nest two different 'any' conditions: {sorted(self.any)} and {sorted(other.any)}")
        return Cond(self.req | other.req, self.nots | other.nots, self.any or other.any)

    def implies(self, other: "Cond") -> bool:
        """True if content visible under `self` is always visible under `other`'s condition."""
        if not (other.req <= self.req and other.nots <= self.nots):
            return False
        return not other.any or bool(self.req & other.any) or bool(self.any and self.any <= other.any)

    def attrs(self) -> str:
        out = f' data-req="{" ".join(sorted(self.req))}"' if self.req else ""
        out += f' data-any="{" ".join(sorted(self.any))}"' if self.any else ""
        return out + (f' data-not="{" ".join(sorted(self.nots))}"' if self.nots else "")


NO_COND = Cond()
COND_SUFFIX = re.compile(r"\s*(?<!\{)\{([a-z!+| ]+)\}$")


def parse_cond(text: str, where: str) -> Cond:
    req, nots, any_of = set(), set(), set()
    for tok in text.split("+"):
        tok = tok.strip()
        if "|" in tok:  # alternatives: at least one of them
            names = [t.strip() for t in tok.split("|")]
            if any_of or any(n not in EXPANSIONS for n in names):
                ERRORS.append(f"{where}: bad 'a|b' part in condition '{text}' (plain keys, at most one such part)")
                continue
            any_of.update(names)
            USED_EXPANSIONS.update(names)
            continue
        name = tok.lstrip("!")
        if name not in EXPANSIONS:
            ERRORS.append(f"{where}: unknown expansion '{name}'")
            continue
        (nots if tok.startswith("!") else req).add(name)
        USED_EXPANSIONS.add(name)
    return Cond(frozenset(req), frozenset(nots), frozenset(any_of))


def split_cond(title: str, where: str) -> tuple[str, Cond]:
    """Split a trailing {condition} off a heading."""
    m = COND_SUFFIX.search(title)
    if not m:
        return title, NO_COND
    return title[:m.start()].rstrip(), parse_cond(m.group(1), where)


def badges(cond: Cond, heading: str = "") -> str:
    """Expansion badges; a heading that already is the expansion's name gets none."""
    return "".join(f'<span class="exp-badge exp-{k}" title="Dodatek: {EXPANSIONS[k]}">{EXPANSIONS[k]}</span>'
                   for k in sorted(cond.req | cond.any) if EXPANSIONS[k] != heading)


# ---------------------------------------------------------------- model


@dataclass
class Entry:
    title: str
    file: str
    group: str | None = None
    pages: str = ""
    source: str = ""
    keys: list[str] = field(default_factory=list)
    extra_related: list[str] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    id: str = ""
    related: list[tuple[str, Cond]] = field(default_factory=list)
    cond: Cond = NO_COND


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
        # entry fields: grupa = group, strony = pages, zrodlo = source, klucze = extra link keys,
        # powiazane = extra related entries, dodatek = expansion
        m = re.match(r"(grupa|strony|zrodlo|klucze|powiazane|dodatek): (.*)$", line)
        if m and not cur.lines:
            k, v = m.groups()
            if k == "dodatek":
                cur.cond = parse_cond(v, f"{path.name} / {cur.title}")
            elif k == "grupa":
                cur.group = v.strip()
            elif k == "strony":
                cur.pages = v.strip()
            elif k == "zrodlo":
                cur.source = v.strip()
            elif k == "powiazane":
                cur.extra_related = [x.strip() for x in v.split(",") if x.strip()]
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
    """Rendering context: the current expansion condition and the links to related entries."""

    def __init__(self, where: str, self_id: str | None = None, cond: Cond = NO_COND):
        self.where = where
        self.self_id = self_id
        self.cond = cond
        self.links: dict[str, set[Cond]] = {}  # entry id -> conditions under which it is linked

    def check_target(self, target_cond: Cond, what: str) -> None:
        if not self.cond.implies(target_cond):
            ERRORS.append(f"{self.where}: link to {what} that can be hidden while this text is visible")


# inline icon file -> spoken name (alt text, also read by screen readers and the link preview)
ICON_NAMES = {
    "moc": "Moc",
    "moneta": "Moneta",
    "regeneracja": "Regeneracja",
    "pancerz": "Pancerz",
    "frakcja-bestie": "Bestie",
    "frakcja-duchy": "Duchy",
    "frakcja-nieumarli": "Nieumarli",
    "frakcja-smiertelnicy": "Śmiertelnicy",
    "symbol-polecane": "symbol kart polecanych na pierwsze rozgrywki",
}


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
        if target.startswith("władca:"):  # link to a Lord on the Władcy tab
            name = html.unescape(target[len("władca:"):].strip())
            lord = LORD_INDEX.get(norm_key(name))
            if not lord:
                ERRORS.append(f"{ctx.where}: unknown Lord in link [[{html.unescape(target)}]]")
                return label or html.escape(name)
            ctx.check_target(lord.cond, f"Lord '{name}'")
            return f'<a class="term lord-link" href="#{lord.id}">{label or html.escape(name)}</a>'
        label = label or target
        tid = LINK_INDEX.get(norm_key(html.unescape(target)))
        if not tid:
            ERRORS.append(f"{ctx.where}: unknown entry in link [[{html.unescape(target)}]]")
            return label
        ctx.check_target(ID_TO_ENTRY[tid].cond, f"entry '{html.unescape(target)}'")
        if tid != ctx.self_id:
            ctx.links.setdefault(tid, set()).add(ctx.cond)
        return f'<a class="term" href="#{tid}">{label}</a>'

    def icon(m: re.Match) -> str:
        name = m.group(1)
        src = find_image(name)
        if not src:
            ERRORS.append(f"{ctx.where}: missing image {{{{{name}}}}}")
            return ""
        if name not in ICON_NAMES:
            ERRORS.append(f"{ctx.where}: icon {{{{{name}}}}} has no entry in ICON_NAMES")
        alt = html.escape(ICON_NAMES.get(name, ""))
        return f'<img class="icon" src="{src}" alt="{alt}" title="{alt}">'

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
            if kind == "dodatek":  # expansion box: "::: dodatek <condition> [Title]"
                spec, _, title = title.partition(" ")
                cond = parse_cond(spec, ctx.where)
                outer = ctx.cond
                ctx.cond = outer | cond
                inner = render_blocks(lines[i + 1:j], ctx)
                head = inline(title, ctx) if title else "Z dodatkiem"
                ctx.cond = outer
                out.append(f'<aside class="box box-expansion"{cond.attrs()}><h5>{head} {badges(cond)}</h5>'
                           f'{inner}</aside>')
                i = j + 1
                continue
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
                alt = html.escape(re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", caption.strip()) or name)
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


def copy_button(anchor: str, what: str) -> str:
    """Button that copies a link to `anchor`; `what` completes the Polish label, e.g. "hasła Horda"."""
    return (f'<button type="button" class="copy-link" data-anchor="{anchor}" '
            f'title="Kopiuj link" aria-label="Kopiuj link do {html.escape(what)}">{LINK_ICON}</button>')


def related_cond(conds: set[Cond]) -> Cond:
    """Condition for a related-entry chip linked from text under the given conditions."""
    return next(iter(conds)) if len(conds) == 1 else NO_COND


def source_label(cond: Cond, source: str, pages: str) -> str:
    """Where an entry comes from, e.g. "instrukcja s. 9" or "instrukcja dodatku s. 2"."""
    if source:
        text = f"{source} s. {pages}" if pages else source
    elif pages:
        text = f"{'instrukcja dodatku' if cond.req or cond.any else 'instrukcja'} s. {pages}"
    else:
        return ""
    return f'<span class="pages">{html.escape(text)}</span>'


def render_entry(e: Entry) -> str:
    ctx = Ctx(f"{e.file} / {e.title}", e.id, e.cond)
    definition, sections = split_sections(e.lines)
    if not any(x.strip() for x in definition):
        ERRORS.append(f"{ctx.where}: missing definition")
    parts = [f'<div class="def">{render_blocks(definition, ctx)}</div>']
    for title, body in sections:
        title, cond = split_cond(title, ctx.where)
        ctx.cond = e.cond | cond
        parts.append(f'<section{cond.attrs()}><h4>{html.escape(title)} {badges(cond)}</h4>'
                     f'{render_blocks(body, ctx)}</section>')
        ctx.cond = e.cond
    ctx.cond = e.cond
    for name in e.extra_related:  # related entries the text does not link to
        tid = LINK_INDEX.get(norm_key(name))
        if not tid:
            ERRORS.append(f"{ctx.where}: unknown related entry '{name}'")
            continue
        ctx.check_target(ID_TO_ENTRY[tid].cond, f"related entry '{name}'")
        if tid in ctx.links:
            ERRORS.append(f"{ctx.where}: related entry '{name}' is already linked in the text")
        elif tid != e.id:
            ctx.links[tid] = {e.cond}
    e.related = [(rid, related_cond(conds)) for rid, conds in ctx.links.items()]
    if not e.related:
        ERRORS.append(f"{ctx.where}: no related entries")
    chips = "".join(f'<li{(c | ID_TO_ENTRY[rid].cond).attrs()}><a class="chip term" href="#{rid}">'
                    f'{html.escape(ID_TO_ENTRY[rid].title)}</a></li>' for rid, c in e.related)
    search = html.escape(" ".join([e.title, *e.keys, *[a.name for a in ALIASES if a.target == e.title]]))
    copy = copy_button(e.id, f"hasła {e.title}")
    return (f'<article class="entry" id="{e.id}" data-search="{search}"{e.cond.attrs()}>'
            f'<h3><span class="t">{html.escape(e.title)}</span>{copy}{badges(e.cond)}'
            f'{source_label(e.cond, e.source, e.pages)}</h3>{"".join(parts)}'
            f'<footer class="related"><h4>Powiązane hasła</h4><ul>{chips}</ul></footer></article>')


def render_alias(a: Alias) -> str:
    t = ENTRIES.get(a.target)
    if not t:
        return ""
    return (f'<div class="alias" id="{a.id}" data-search="{html.escape(a.name)}"{t.cond.attrs()}>'
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
    chapter_cond = NO_COND
    in_chapter = in_sub = False
    for level, title, lines in chapters:
        ctx.where = f"{path.name} / {title}"
        title, cond = split_cond(title, ctx.where)
        hid = "i-" + slug(title)
        if in_sub:
            body.append("</div>")
            in_sub = False
        if level == 1:
            if in_chapter:
                body.append("</section>")
            in_chapter = True
            chapter_cond = cond
            ctx.cond = cond
            # base-game chapters are numbered; expansion chapters carry a badge instead
            label = "" if cond else f"{(num := num + 1)}. "
            num_html = "" if cond else f'<span class="num">{num}.</span> '
            body.append(f'<section class="chapter"{cond.attrs()}><h2 id="{hid}">{num_html}'
                        f'{inline(title, ctx)} {badges(cond, title)}</h2>')
            toc.append(f'<li class="toc-1"{cond.attrs()}><a href="#{hid}">{label}{html.escape(title)}</a></li>')
        else:
            full = chapter_cond | cond
            ctx.cond = full
            body.append(f'<div class="sub"{cond.attrs()}><h3 id="{hid}">{inline(title, ctx)} {badges(cond)}</h3>')
            in_sub = True
            toc.append(f'<li class="toc-2"{full.attrs()}><a href="#{hid}">{html.escape(title)}</a></li>')
        body.append(render_blocks(lines, ctx))
    if in_sub:
        body.append("</div>")
    body.append("</section>")
    return "".join(body), "".join(toc)


# ---------------------------------------------------------------- Lords

# faction name used in src -> inline icon file
FACTIONS = {
    "Bestie": "frakcja-bestie",
    "Duchy": "frakcja-duchy",
    "Nieumarli": "frakcja-nieumarli",
    "Śmiertelnicy": "frakcja-smiertelnicy",
}


@dataclass
class Lord:
    name: str
    faction: str = ""
    life: str = ""
    title: str = ""
    pages: str = ""
    lines: list[str] = field(default_factory=list)
    id: str = ""
    own: Cond = NO_COND  # condition from the Lord's own "dodatek:" field
    cond: Cond = NO_COND  # own condition joined with the section's


@dataclass
class LordSection:
    title: str
    cond: Cond = NO_COND
    intro: list[str] = field(default_factory=list)
    lords: list[Lord] = field(default_factory=list)


LORD_SECTIONS: list[LordSection] = []
LORD_INDEX: dict[str, Lord] = {}  # normalized Lord name -> Lord


def parse_lords(path: Path) -> None:
    cur: Lord | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if line.startswith("# "):
            title, cond = split_cond(line[2:].strip(), path.name)
            LORD_SECTIONS.append(LordSection(title, cond))
            cur = None
            continue
        if line.startswith("@@ "):
            if not LORD_SECTIONS:
                ERRORS.append(f"{path.name}: Lord before the first # section: {line}")
                continue
            cur = Lord(line[3:].strip(), cond=LORD_SECTIONS[-1].cond)
            LORD_SECTIONS[-1].lords.append(cur)
            continue
        if cur is None:
            if LORD_SECTIONS:
                LORD_SECTIONS[-1].intro.append(line)
            continue
        # frakcja = faction, zycie = life, tytul = sheet title, strony = pages, dodatek = expansion
        m = re.match(r"(frakcja|zycie|tytul|strony|dodatek): (.*)$", line)
        if m and not cur.lines:
            k, v = m.group(1), m.group(2).strip()
            if k == "frakcja":
                cur.faction = v
            elif k == "zycie":
                cur.life = v
            elif k == "tytul":
                cur.title = v
            elif k == "strony":
                cur.pages = v
            else:
                cur.own = parse_cond(v, f"{path.name} / {cur.name}")
                cur.cond = cur.cond | cur.own
            continue
        cur.lines.append(line)
    for sec in LORD_SECTIONS:
        for lord in sec.lords:
            lord.id = "w-" + slug(lord.name)
            if norm_key(lord.name) in LORD_INDEX:
                ERRORS.append(f"{path.name}: duplicate Lord '{lord.name}'")
            LORD_INDEX[norm_key(lord.name)] = lord
            if lord.faction not in FACTIONS:
                ERRORS.append(f"{path.name} / {lord.name}: unknown faction '{lord.faction}'")
            if not (lord.life and lord.title):
                ERRORS.append(f"{path.name} / {lord.name}: missing 'zycie' or 'tytul'")


def render_lord(lord: Lord) -> str:
    ctx = Ctx(f"wladcy.txt / {lord.name}", cond=lord.cond)
    intro, sections = split_sections(lord.lines)
    if not sections or not split_cond(sections[0][0], ctx.where)[0].startswith("Zdolność"):
        ERRORS.append(f"{ctx.where}: the first section must be '## Zdolność …' (the text printed on the Lord sheet)")
    parts = [render_blocks(intro, ctx)]
    for n, (title, body) in enumerate(sections):
        title, cond = split_cond(title, ctx.where)
        ctx.cond = lord.cond | cond
        cls = ' class="lord-ability"' if n == 0 else ""
        parts.append(f'<section{cls}{cond.attrs()}><h4>{html.escape(title)} {badges(cond)}</h4>'
                     f'{render_blocks(body, ctx)}</section>')
        ctx.cond = lord.cond
    icon = FACTIONS.get(lord.faction, "")
    src = find_image(icon) if icon else None
    faction_img = (f'<img class="faction-icon" src="{src}" alt="" title="{html.escape(lord.faction)}">'
                   if src else "")
    pages = f" · instrukcja{' dodatku' if lord.cond else ''} s. {html.escape(lord.pages)}" if lord.pages else ""
    meta = (f'<p class="lord-meta"><span class="lord-title">„{html.escape(lord.title)}”</span> · '
            f'frakcja: {html.escape(lord.faction)} · {html.escape(lord.life)} punktów Życia{pages}</p>')
    return (f'<article class="lord" id="{lord.id}"{lord.own.attrs()}>'
            f'<h3>{faction_img}<span class="t">{html.escape(lord.name)}</span>'
            f'{copy_button(lord.id, f"Władcy {lord.name}")}{badges(lord.own)}</h3>'
            f'{meta}{"".join(parts)}</article>')


def render_lords() -> tuple[str, str]:
    body: list[str] = []
    toc: list[str] = []
    for sec in LORD_SECTIONS:
        sid = "s-" + slug(sec.title)
        ctx = Ctx(f"wladcy.txt / {sec.title}", cond=sec.cond)
        body.append(f'<section class="lord-section"{sec.cond.attrs()}><h2 id="{sid}">{html.escape(sec.title)} '
                    f'{badges(sec.cond, sec.title)}</h2>'
                    f'{render_blocks(sec.intro, ctx)}{"".join(render_lord(lord) for lord in sec.lords)}</section>')
        toc.append(f'<li class="toc-1"{sec.cond.attrs()}><a href="#{sid}">{html.escape(sec.title)}</a></li>')
        toc.extend(f'<li class="toc-2"{lord.cond.attrs()}><a href="#{lord.id}">{html.escape(lord.name)}</a></li>'
                   for lord in sec.lords)
    return "".join(body), "".join(toc)


# ---------------------------------------------------------------- page

# The page text is Polish; ids, classes and comments are English.
PAGE = """<!DOCTYPE html>
<html lang="pl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<!-- Content Security Policy as a <meta> tag: an exception to the "send CSP as an HTTP header" rule.
     Reason: the page is hosted on GitHub Pages, which cannot send custom response headers,
     and it is also opened locally from file://, where there is no server at all.
     frame-ancestors is left out because browsers ignore it in a <meta> tag.
     The code uses no inline scripts or styles and no eval. On a host that can send headers, send instead:
     Content-Security-Policy: default-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self' -->
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'">
<title>Terrors of London — zasady gry</title>
<link rel="stylesheet" href="style.css?v=__V_CSS__">
<script src="app.js?v=__V_JS__" defer></script>
</head>
<body>
<header class="top">
  <div class="brand">Terrors of London <span>zasady gry</span></div>
  <nav class="tabs" role="tablist">
    <a href="#rules" class="tab" data-tab="rules" role="tab">Instrukcja</a>
    <a href="#glossary" class="tab" data-tab="glossary" role="tab">Glosariusz</a>
    <a href="#lords" class="tab" data-tab="lords" role="tab">Władcy</a>
  </nav>
  __EXP_MENU__
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
    <p class="gloss-intro">Hasła o wspólnym pierwszym słowie są zebrane w grupy (▸).
    Hasła zapisane kursywą są odsyłaczami do hasła głównego.</p>
    <p class="empty" id="no-results" hidden>Brak haseł pasujących do wyszukiwania.</p>
    __GLOSS__
  </main>
</div>
<div class="panel" id="lords">
  <nav class="side" aria-label="Spis Władców"><h2>Władcy</h2><ol class="toc">__LORDS_TOC__</ol></nav>
  <main class="content lords">
    <p class="lords-intro">Władcy z gry podstawowej i dodatków: frakcja, zdolność z arkusza Władcy,
    zasoby, z których korzysta, i zasady przygotowania. Władcy z dodatków są widoczni po wybraniu dodatku w menu „Dodatki”.</p>
    __LORDS__
  </main>
</div>
<footer class="bottom">Opracowanie na podstawie instrukcji „Terrors of London” (Brad Pye, wyd. polskie Portal Games).
Numery stron odnoszą się do oryginalnych instrukcji (w dodatkach: stron pliku PDF). Grafiki pochodzą z instrukcji.
Wariant drużynowy według osobnej instrukcji wariantu (Portal Games).</footer>
</body>
</html>
"""


def render_expansion_menu() -> str:
    """Expansion checkboxes; only expansions that have content are offered."""
    if not USED_EXPANSIONS:
        return ""
    boxes = "".join(f'<label><input type="checkbox" data-exp="{k}"> {html.escape(name)}</label>'
                    for k, name in EXPANSIONS.items() if k in USED_EXPANSIONS)
    return ('<details class="exp-menu"><summary>Dodatki <span class="exp-count" id="exp-count"></span></summary>'
            f'<div class="exp-panel"><p>Pokaż zasady z dodatków:</p>{boxes}'
            '<p class="exp-hint">Wybór zostanie zapamiętany w tej przeglądarce.</p></div></details>')


def mtime(name: str) -> str:
    return str(int((ROOT / name).stat().st_mtime))


def main() -> int:
    for p in sorted(SRC.glob("glosariusz-*.txt")):
        parse_glossary(p)
    build_index()
    ID_TO_ENTRY.update({e.id: e for e in ENTRIES.values()})
    parse_lords(SRC / "wladcy.txt")  # before rendering, so [[władca: ...]] links resolve
    gloss, letters = render_glossary()
    rules, toc = render_rules()
    lords, lords_toc = render_lords()
    menu = render_expansion_menu()
    page = (PAGE.replace("__TOC__", toc).replace("__RULES__", rules)
            .replace("__LETTERS__", letters)
            .replace("__V_CSS__", mtime("style.css")).replace("__V_JS__", mtime("app.js"))
            .replace("__GLOSS__", gloss).replace("__EXP_MENU__", menu)
            .replace("__LORDS_TOC__", lords_toc).replace("__LORDS__", lords))
    if "style=" in page or re.search(r"<script(?![^>]*\bsrc=)", page):
        ERRORS.append("page contains inline styles or scripts (not CSP-compliant)")
    linked = {rid for e in ENTRIES.values() for rid, _ in e.related}
    orphans = [e.title for e in ENTRIES.values() if e.id not in linked]
    (ROOT / "index.html").write_text(page, encoding="utf-8")
    groups = {e.group for e in ENTRIES.values() if e.group} | {a.group for a in ALIASES if a.group}
    n_lords = sum(len(sec.lords) for sec in LORD_SECTIONS)
    print(f"entries: {len(ENTRIES)}, aliases: {len(ALIASES)}, groups: {len(groups)}, Lords: {n_lords}")
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
