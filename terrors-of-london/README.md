# Terrors of London: rules reference (website)

A rewritten, easier-to-read version of the Polish rulebook for *Terrors of London*
(Polish edition by Portal Games). The page content is in Polish; the code is in English.

Open `index.html` in a browser. The page works offline, but it needs the whole folder:
`style.css`, `app.js` and `img/` must sit next to `index.html`.

## Structure

- `index.html`: the generated page (do not edit by hand)
- `style.css`, `app.js`: styling, glossary search, definition tooltips, expansion selection
- `img/`: images cropped from the original rulebooks
- `src/instrukcja.txt`: content of the *Instrukcja* (rules) tab
- `src/glosariusz-podstawka.txt`: glossary entries of the base game
- `src/glosariusz-gadzi.txt`: glossary entries of *Gadzi Grobowiec* and its 2-vs-2 team variant
- `src/glosariusz-brama.txt`: glossary entries of *Słudzy Czarnej Bramy*
- `src/wladcy.txt`: content of the *Władcy* (Lords) tab
- `tools/build.py`: builds `index.html` and validates links
- `tools/crop_images.py`: crops images from the PDFs (requires `poppler`)

## Editing content

1. Edit the files in `src/`. The markup syntax is described at the top of `tools/build.py`.
2. Run:

   ```bash
   python3 tools/build.py
   ```

   The build fails if a `[[...]]` link points to a missing entry or Lord, if an entry has no
   related entries, if a link points to content that can be hidden while the linking text is
   visible, or if the page contains inline styles or scripts. The *Powiązane hasła* (related
   entries) list at the end of each glossary entry is generated from the links used in that
   entry's text.

## Sources

Rules come from the Polish rulebooks of the base game and the expansions, and from the separate
leaflet of the 2-vs-2 team variant (*Wariant drużynowy*). Expansion page numbers are PDF pages. Some Lord data is not
printed in the rulebooks (it is on the Lord sheets or cards) and was provided by the page owner:
abilities, life and sheet titles of the expansion Lords, the number of Influence cards and
Minions (*Sługusy*) per Lord, the purpose of the Acolyte cost token, and rulings on situations
the rulebooks do not cover.

## Re-cropping images

```bash
python3 tools/crop_images.py /path/to/folder-with-the-pdfs
```

The folder must hold the Polish PDFs under the file names listed in `PDFS` in
`tools/crop_images.py`. Add image names after the folder to crop only those.

Image file names stay Polish because the files in `src/` refer to them by name.

## Hosting

The page is published with GitHub Pages at https://kiminoboku.github.io/terrors-of-london/.

GitHub Pages cannot send custom HTTP headers, so the Content Security Policy is set with a
`<meta>` tag in `index.html` (written by `tools/build.py`). Browsers ignore `frame-ancestors`
in a `<meta>` tag, so on GitHub Pages the page can still be embedded in other sites.
The page uses no inline scripts or styles and no `eval`.

On a host that can send headers, send this header instead:

```
Content-Security-Policy: default-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'
```
