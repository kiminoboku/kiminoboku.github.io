# War of the Ring: rules reference (website)

A rewritten, easier-to-read version of the Polish rulebook for *War of the Ring*
(2nd edition, Polish edition by Galakta). The page content is in Polish; the code is in English.
Rulebook and card errata follow the unofficial *Errata i FAQ* v. 2.92 by Kamil Łukasik.

Open `index.html` in a browser. The page works offline, but it needs the whole folder:
`style.css`, `app.js` and `img/` must sit next to `index.html`.

## Structure

- `index.html`: the generated page (do not edit by hand)
- `style.css`, `app.js`: styling, glossary search, definition tooltips
- `img/`: images cropped from the original rulebook
- `src/instrukcja.txt`: content of the *Instrukcja* (rules) tab
- `src/glosariusz-a-o.txt`, `src/glosariusz-p-z.txt`: glossary entries
- `src/karty.txt`: content of the *Karty* (cards) tab: card errata
- `tools/build.py`: builds `index.html` and validates links
- `tools/crop_images.py`: crops images from the PDF (requires `poppler`)

## Editing content

1. Edit the files in `src/`. The markup syntax is described at the top of `tools/build.py`.
2. Run:

   ```bash
   python3 tools/build.py
   ```

   The build fails if a `[[...]]` link points to a missing entry or an entry has no related
   entries. The *Powiązane hasła* (related entries) list at the end of each glossary entry is
   generated from the links used in that entry's text.

## Re-cropping images

```bash
python3 tools/crop_images.py /path/to/WoP_instrukcja.pdf
```

Image file names stay Polish because the files in `src/` refer to them by name.

## Hosting

The page is published with GitHub Pages at https://kiminoboku.github.io/wojna-o-pierscien/.

GitHub Pages cannot send custom HTTP headers, so the Content Security Policy is set with a
`<meta>` tag in `index.html` (written by `tools/build.py`). Browsers ignore `frame-ancestors`
in a `<meta>` tag, so on GitHub Pages the page can still be embedded in other sites.
The page uses no inline scripts or styles and no `eval`.

On a host that can send headers, send this header instead:

```
Content-Security-Policy: default-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'
```
