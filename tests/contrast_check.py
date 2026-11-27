"""Measure a RENDERED page: >=24px text, >=6:1 contrast, canonical controls, a real outer gutter,
no sideways scroll.

Thresholds are the owner's (6:1, 24px), not WCAG AA's 4.5:1 — AA has already passed a control this
reader reported as unfindable. Everything here is computed style in a real browser; nothing asserts
on CSS text. `chromium.launch(channel="chrome")` is baked in because the bundled Chromium is not
installed on this machine.

    python3 ~/.claude/skills/dashboard-ui/test_contrast_static.py page.html [more.html ...]

Exit 0 = every page passed. Exit 1 = a breach, or something it could not measure, each named.
Exit 2 = it was given no pages at all.

THREE DEFECTS THIS FILE USED TO HAVE, fixed 2026-09-04 after they let a real breach through in
CC Dev/Claude Usage. If you are reading a copy of this in a project, check it has all three:

  1. It only PRINTED breaches and exited 0 — a report, not a gate. It returned success on a page
     with 409 sub-24px text nodes. A check that cannot fail is not a check.
  2. `bgOf` walked up to the first background with alpha > 0.95 and DISCARDED every translucent
     layer above it. A `.10`-alpha red wash on a table row therefore read as the panel underneath,
     and text on it measured 6.63:1 while actually rendering at 5.83:1. Every layer is now
     composited src-over, bottom-up, and translucent LETTERS are composited over their background
     too. This is the one that matters: it is the difference between measuring the page and
     measuring what you assumed the page was.
  3. It never looked at controls. A filled face needs >=2:1 against its surround or you cannot
     FIND it, and its letters must be white or near-black — neither is implied by the text sweep,
     because an invisible control still has perfectly legible letters.

FOURTH DEFECT, fixed 2026-10-30: group opacity was counted twice. `bgOf` dimmed a painted
background by its group's opacity and `record()` then dimmed the letters again over that dimmed
background, but CSS flattens the group once (letters and background together, then the opacity).
#f8f8f8 on #080808 at opacity .56 renders 5.99:1 and used to measure 6.15:1. Nested groups are
flattened inside-out, and a control's face, letters and edge go through the same `paint`.

TWO THINGS IT STILL CANNOT DO FOR YOU, so do them in the project:

  * **Rename it out of pytest's collection path.** Copied in as `test_contrast_static.py`, pytest
    collects it on the `test_` prefix, dies on the playwright import and takes the whole suite
    down at collection. Name the project copy something like `contrast_check.py`, and resist an
    `importorskip` — that turns the strongest check in the project into a skip, and a skip is a
    check that did not run.
  * **Refuse a stale artifact.** Pointed at pre-generated (usually gitignored) HTML, it will
    happily pass a page produced before the CSS was reverted. In the project, refuse to measure a
    page older than the renderer that writes it, and refuse one whose renderer is not beside it —
    skipping the check because its reference is missing is the same false pass one level up.
"""
import pathlib
import sys

from playwright.sync_api import sync_playwright

MIN_TEXT_CONTRAST = 6.0
MIN_PX = 24.0
MIN_FACE_CONTRAST = 2.0          # a filled control against what surrounds it
# The outer gutter: how far the nearest text sits from the window edge. Owner instruction
# 2026-09-08 — a page whose sides measured 28.8px was rejected as having no border at all.
# Scaled, not fixed: 40px is a decent border at 1440px and half the line at 390px. Tokens
# ship `--gutter:clamp(1rem,4vw,4rem)`, which clears this at every width with room to spare.
GUTTER_FLOOR_PX = 40.0           # ...at a wide viewport
GUTTER_FLOOR_VW = 0.04           # ...and never more than 4% of a narrow one
LETTER_TOLERANCE = 24            # how far from pure white / near-black a control's letters may sit

SWEEP = r"""
(MIN_TEXT_CONTRAST) => {
  const lum = (r,g,b) => {
    const f = c => { c/=255; return c<=0.03928 ? c/12.92 : Math.pow((c+0.055)/1.055,2.4); };
    return 0.2126*f(r)+0.7152*f(g)+0.0722*f(b);
  };
  const parse = s => {
    const m = String(s).match(/rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)/);
    return m ? [+m[1],+m[2],+m[3], m[4]===undefined?1:+m[4]] : null;
  };
  // `opacity` is a GROUP property: the browser flattens an element and everything inside it into
  // one image, then fades THAT once over whatever sits behind the group. So a node's background and
  // the letters inside it are composited TOGETHER and the node's opacity is applied to the result.
  // Fading the background and then fading the letters over the already-faded background counts the
  // opacity twice: #f8f8f8 on #080808 at .56 renders 5.99:1 and measured 6.15:1. Groups nest, each
  // flattened inside the next one out, so a node's opacity never touches what is outside it.
  const chain = el => { const c = []; for (let n = el; n; n = n.parentElement) c.push(n); return c; };
  const premult = c => [c[0]*c[3], c[1]*c[3], c[2]*c[3], c[3]];
  // The paint layers behind `el`, innermost first: {c: its background, o: its own opacity, img}.
  // `ps` is a pseudo-element's computed style, one more group inside its host. The list stops at the
  // first opaque background under no fade at all, because nothing further out can show. It is `null`
  // when the real colour cannot be derived from computed style: a gradient or image on the way, or
  // no opaque background ever reached. Returning a GUESS here is the whole failure mode this harness
  // exists to catch: assuming black behind a page that never paints a background passes
  // white-on-white, because the browser canvas is white, not black.
  const layersOf = (el, ps) => {
    const L = [];
    for (const cs of [ps, ...chain(el).map(n => getComputedStyle(n))]) {
      if (!cs) continue;
      L.push({c: parse(cs.backgroundColor), o: +cs.opacity,
              img: !!cs.backgroundImage && cs.backgroundImage !== 'none'});
    }
    const fade = [];                     // fade[i]: layer i's opacity times everything outside it
    for (let i = L.length - 1, up = 1; i >= 0; i--) { up *= L[i].o; fade[i] = up; }
    for (let i = 0; i < L.length; i++) {
      if (L[i].img) return null;
      if (L[i].c && L[i].c[3] * fade[i] > 0.999) return L.slice(0, i + 1);
    }
    return null;
  };
  // Flatten `L` the way the browser does and return the opaque colour it shows. `top` (the letters,
  // or a control's border) is painted over the innermost background, INSIDE the groups.
  const paint = (L, top) => {
    let acc = top ? premult(top) : [0, 0, 0, 0];
    for (const l of L) {
      const bg = l.c ? premult(l.c) : [0, 0, 0, 0];
      acc = acc.map((v, k) => (v + bg[k] * (1 - acc[3])) * l.o);
    }
    return acc[3] > 0.999 ? [acc[0] / acc[3], acc[1] / acc[3], acc[2] / acc[3], 1] : null;
  };
  const bgOf = (el, ps) => { const L = layersOf(el, ps); return L && paint(L, null); };
  const ratio = (a,b) => {
    const L1 = lum(a[0],a[1],a[2]), L2 = lum(b[0],b[1],b[2]);
    return (Math.max(L1,L2)+0.05)/(Math.min(L1,L2)+0.05);
  };
  const visible = cs => !(cs.display === 'none' || cs.visibility === 'hidden' || +cs.opacity === 0);

  const text = [], unmeasurable = [];
  // `own` is the pseudo-element's own computed style when one is passed, so its background is
  // painted OVER the host's stack rather than ignored.
  const record = (el, cs, label, sample, own) => {
    const L = layersOf(el, own);
    const bg = L && paint(L, null);
    const desc = {
      tag: el.tagName.toLowerCase(),
      cls: (typeof el.className === 'string' ? el.className : ''),
      px: parseFloat(cs.fontSize),
      text: (label ? label + ' ' : '') + String(sample).slice(0, 60)
    };
    // Distance from each window edge to this text's box — but measured on the nearest
    // ancestor that CLIPS or SCROLLS horizontally, when there is one. A wide table or a
    // long code line inside `overflow-x:auto` extends past the window by design; what the
    // reader sees framed is the scroller, and judging the cell instead reports a gutter
    // breach on every page with a scrolling table. Without an ancestor like that, the
    // element that owns the text is itself the thing in the page flow.
    {
      let box = el;
      for (let n = el.parentElement; n && n !== document.documentElement; n = n.parentElement) {
        const ox = getComputedStyle(n).overflowX;
        if (ox === 'auto' || ox === 'scroll' || ox === 'hidden') { box = n; break; }
      }
      // The CONTENT box, not the border box. A clipping ancestor is very often <body>
      // itself, whose border box is the full window however much padding it carries —
      // measuring that reports 0px of gutter on a page that has a perfectly good one.
      const cs2 = getComputedStyle(box), r = box.getBoundingClientRect();
      const px = v => parseFloat(v) || 0;
      desc.gl = r.left + px(cs2.borderLeftWidth) + px(cs2.paddingLeft);
      desc.gr = innerWidth - (r.right - px(cs2.borderRightWidth) - px(cs2.paddingRight));
    }
    let fg = parse(cs.color);
    if (!fg) { unmeasurable.push({...desc, why: 'no computed colour'}); return; }
    if (bg === null) { unmeasurable.push({...desc, why: 'background is a gradient, an inherited '
                                                      + 'opacity, or an unpainted canvas'}); return; }
    // The letters are painted inside the same groups as the background, so they are flattened with it.
    fg = paint(L, fg);
    text.push({...desc, contrast: +ratio(fg, bg).toFixed(2)});
  };
  document.querySelectorAll('*').forEach(el => {
    const cs = getComputedStyle(el);
    if (!visible(cs)) return;
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) return;
    const ownText = [...el.childNodes]
      .filter(n => n.nodeType === 3 && n.textContent.trim())
      .map(n => n.textContent.trim()).join(' ');
    if (ownText) record(el, cs, '', ownText, null);
    // A placeholder is text the reader has to read, and it is styled separately from .color.
    if (el.placeholder && el.placeholder.trim()) {
      const ph = getComputedStyle(el, '::placeholder');
      record(el, ph.color ? ph : cs, '[placeholder]', el.placeholder.trim(), null);
    }
    // ::before / ::after carry labels, icons and units in most design systems.
    for (const pseudo of ['::before', '::after']) {
      const ps = getComputedStyle(el, pseudo);
      const content = ps.content;
      if (!content || content === 'none' || content === 'normal') continue;
      const shown = content.replace(/^"|"$/g, '').trim();
      if (!shown || ps.display === 'none' || +ps.opacity === 0) continue;
      record(el, ps, '[' + pseudo + ']', shown, ps);
    }
  });

  const WHITE = [255,255,255,1], NEAR_BLACK = [7,9,12,1];
  const controls = [];
  // Enumerating input types is how `tel`, `url` and `date` went unchecked. Take them all and
  // let the native-widget test below drop the ones the browser draws itself.
  const CONTROL_SEL = 'button, .btn, a[role=button], [role=button], [role=tab], [role=menuitem],'
    + ' [role=switch], [role=combobox], input:not([type=hidden]), select, textarea';
  document.querySelectorAll(CONTROL_SEL).forEach(el => {
    const cs = getComputedStyle(el);
    if (!visible(cs)) return;
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) return;
    const nativeWidget = /^(checkbox|radio|file)$/.test(el.type || '')
      && /auto/.test(cs.appearance || cs.webkitAppearance || 'auto');
    if (nativeWidget) return;          // browser-drawn: there is no author face to measure
    const L = layersOf(el);
    const face = L && paint(L, null);
    const around = el.parentElement ? bgOf(el.parentElement) : null;
    const base = {
      tag: el.tagName.toLowerCase(),
      cls: (typeof el.className === 'string' ? el.className : ''),
      px: parseFloat(cs.fontSize),
      text: (el.value || el.textContent || el.placeholder || '').trim().slice(0, 40)
    };
    if (face === null || around === null) {
      controls.push({...base, unmeasurable: 'face or surround cannot be derived'});
      return;
    }
    const fg = paint(L, parse(cs.color) || NEAR_BLACK);
    // The widest border edge actually painted. The spec is a bright 2px edge in the face's hue:
    // without one a dark face on a near-black page measured 1.08:1 against its own panel.
    const widths = ['Top','Right','Bottom','Left'].map(s => ({
      w: parseFloat(cs['border' + s + 'Width']) || 0,
      style: cs['border' + s + 'Style'],
      col: parse(cs['border' + s + 'Color'])
    })).filter(b => b.w > 0 && b.style !== 'none' && b.col && b.col[3] > 0.05);
    const edge = widths.length ? Math.min(...widths.map(b => b.w)) : 0;
    const edgeCol = widths.length ? paint(L, widths[0].col) : null;
    // A mid-tone face is refused whatever it measures: it is one where NEITHER white nor
    // near-black letters clear the floor, so no permitted letter colour can rescue it.
    const midtone = ratio(WHITE, face) < MIN_TEXT_CONTRAST
                 && ratio(NEAR_BLACK, face) < MIN_TEXT_CONTRAST;
    const ownBg = parse(cs.backgroundColor);
    controls.push({...base,
      filled: !!(ownBg && ownBg[3] > 0.05),
      letters: +ratio(fg, face).toFixed(2),
      face: +ratio(face, around).toFixed(2),
      rgb: [Math.round(fg[0]), Math.round(fg[1]), Math.round(fg[2])],
      edge: edge,
      edgeContrast: edgeCol ? +ratio(edgeCol, face).toFixed(2) : 0,
      midtone: midtone
    });
  });
  return {text, controls, unmeasurable};
}
"""


MIN_EDGE_PX = 2.0                # the agreed control spec: a bright 2px edge in the face's hue
MIN_EDGE_CONTRAST = 1.5          # ...and it has to be visible against the face it edges


def _letters_ok(rgb):
    """White or near-black only. A tinted glyph on a control is refused whatever it measures."""
    return all(c >= 255 - LETTER_TOLERANCE for c in rgb) or all(c <= LETTER_TOLERANCE for c in rgb)


def _control_faults(c):
    """Every way a control departs from the agreed spec, named. Letter and size checks apply only
    where the control actually carries letters — an icon-only control has no text to measure."""
    if c.get("unmeasurable"):
        return [c["unmeasurable"]]
    faults = []
    if c["midtone"]:
        faults.append("mid-tone face (neither white nor near-black letters can clear the floor "
                      "on it) — refused whatever it measures")
    face_ok = c["face"] >= MIN_FACE_CONTRAST
    edge_ok = c["edge"] >= MIN_EDGE_PX and c["edgeContrast"] >= MIN_EDGE_CONTRAST
    if not face_ok and not edge_ok:
        faults.append(f"face only {c['face']}:1 against its surround and edge {c['edge']}px at "
                      f"{c['edgeContrast']}:1 — you cannot find it at all")
    elif c["filled"] and not edge_ok:
        # "Every filled face carries a bright 2px edge in its own hue" is flat, not conditional:
        # a face that reads clearly on one panel vanishes on the next one someone drops it into.
        faults.append(f"filled face with no bright edge — {c['edge']}px at {c['edgeContrast']}:1, "
                      f"the spec is {MIN_EDGE_PX:.0f}px in the face's own hue")
    if c["text"]:
        if c["letters"] < MIN_TEXT_CONTRAST:
            faults.append(f"letters {c['letters']}:1 on the face")
        if not _letters_ok(c["rgb"]):
            faults.append(f"letters rgb{tuple(c['rgb'])} are neither white nor near-black")
        if c["px"] < MIN_PX:
            faults.append(f"{c['px']:.0f}px letters")
    return faults


def check(page_path):
    page = pathlib.Path(page_path).resolve()
    if not page.is_file():
        return [f"{page.name}: no such page — nothing was measured"]
    breaches = []
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome")
        # 1100px is not decoration. At 1440 a centred `max-width` supplies the gutter by
        # itself, so the page that PROMPTED this check measured 48px and passed; the defect only
        # appears once the container is width-constrained, which is every pane and half-screen
        # window the reader actually uses. A width where max-width does not bind is the only one
        # that measures the page's own padding.
        for label, width in (("desktop", 1440), ("narrow", 1100), ("mobile", 390)):
            pg = b.new_page(viewport={"width": width, "height": 900})
            pg.goto(page.as_uri())
            # A web font that has not loaded is a different metric and sometimes a different
            # colour; 300ms is a hope, fonts.ready is the event.
            pg.evaluate("() => document.fonts ? document.fonts.ready : null")
            pg.wait_for_timeout(150)
            data = pg.evaluate(SWEEP, MIN_TEXT_CONTRAST)
            nodes, controls = data["text"], data["controls"]
            blind = data["unmeasurable"]
            overflow = pg.evaluate(
                "() => document.documentElement.scrollWidth >"
                " document.documentElement.clientWidth + 1"
            )
            gutter_floor = min(GUTTER_FLOOR_PX, GUTTER_FLOOR_VW * width)
            # Once the page is wider than the window there is no gutter to measure: the
            # content the reader can see ends at the frame by definition, so every page that
            # scrolls sideways would also report a 0px gutter and the two lines would name
            # one defect twice. Fix the overflow, re-run, and the gutter is judged again.
            tight = [] if overflow else [n for n in nodes
                                         if min(n["gl"], n["gr"]) < gutter_floor]
            small = [n for n in nodes if n["px"] < MIN_PX]
            faint = [n for n in nodes if n["contrast"] < MIN_TEXT_CONTRAST]
            bad_ctl = [(c, _control_faults(c)) for c in controls]
            bad_ctl = [(c, f) for c, f in bad_ctl if f]

            print(f"\n=== {page.name} · {label} ({width}px) — {len(nodes)} text elements, "
                  f"{len(controls)} controls ===")
            print(f"  horizontal page scroll : {'FAIL' if overflow else 'none'}")
            # Report the min over the SAME set the gate judges, or the number under the
            # verdict disagrees with the verdict — an internal scroller's -380px is not a gutter.
            if overflow:
                print("  outer gutter          : not judged — the page scrolls sideways, so "
                      "there is no gutter to measure until that is fixed")
            elif nodes:
                print(f"  outer gutter (floor {gutter_floor:.0f}px): "
                      f"{min(min(n['gl'], n['gr']) for n in nodes):.1f}px"
                      f"{'  FAIL' if tight else ''}")
            for n in tight[:6]:
                print(f"      left {n['gl']:.1f}px / right {n['gr']:.1f}px  <{n['tag']} "
                      f"class=\"{n['cls']}\">  {n['text']!r}")
            print(f"  below {MIN_PX:.0f}px           : {len(small)}")
            for n in small[:12]:
                print(f"      {n['px']:.1f}px  <{n['tag']} class=\"{n['cls']}\">  {n['text']!r}")
            print(f"  below {MIN_TEXT_CONTRAST}:1 contrast  : {len(faint)}")
            for n in faint[:12]:
                print(f"      {n['contrast']}:1  {n['px']:.1f}px  <{n['tag']} "
                      f"class=\"{n['cls']}\">  {n['text']!r}")
            print(f"  non-canonical controls : {len(bad_ctl)} of {len(controls)}")
            for c, faults in bad_ctl[:12]:
                print(f"      <{c['tag']} class=\"{c['cls']}\">  {c['text']!r}")
                for f in faults:
                    print(f"          - {f}")
            print(f"  UNMEASURABLE text      : {len(blind)}")
            for n in blind[:12]:
                print(f"      <{n['tag']} class=\"{n['cls']}\">  {n['text']!r}  — {n['why']}")
            if nodes:
                print(f"  min contrast measured  : {min(n['contrast'] for n in nodes)}:1")
                print(f"  min font size measured : {min(n['px'] for n in nodes)}px")

            if not nodes and not blind:
                breaches.append(f"{page.name} {label}: 0 text elements found — it did not render")
            elif not nodes:
                breaches.append(f"{page.name} {label}: every text node was unmeasurable — nothing "
                                f"about this page's contrast has been established")
            if small:
                breaches.append(f"{page.name} {label}: {len(small)} text nodes below {MIN_PX:.0f}px "
                                f"(min {min(n['px'] for n in small)}px)")
            if faint:
                breaches.append(f"{page.name} {label}: {len(faint)} text nodes below "
                                f"{MIN_TEXT_CONTRAST}:1 (min {min(n['contrast'] for n in faint)}:1)")
            if bad_ctl:
                breaches.append(f"{page.name} {label}: {len(bad_ctl)} of {len(controls)} controls "
                                f"off the canonical spec — " +
                                "; ".join(f"<{c['tag']}.{c['cls'][:18]}> {f[0]}"
                                          for c, f in bad_ctl[:4]))
            if blind:
                # Refusing beats guessing, but a refusal that prints and passes is the same
                # false pass in a politer voice.
                breaches.append(f"{page.name} {label}: {len(blind)} text nodes could NOT be "
                                f"measured (gradient, inherited opacity, or a page that paints no "
                                f"background) — {blind[0]['why']}")
            if tight:
                worst = min(min(n["gl"], n["gr"]) for n in tight)
                breaches.append(f"{page.name} {label}: text sits {worst:.1f}px from the window "
                                f"edge, floor is {gutter_floor:.0f}px at {width}px — the page "
                                f"needs an outer gutter (tokens.css ships --gutter)")
            if overflow:
                breaches.append(f"{page.name} {label}: the page scrolls horizontally")
            pg.close()
        b.close()
    return breaches


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    breaches = []
    for page in argv:
        breaches += check(page)
    if breaches:
        print("\nFAIL")
        for line in breaches:
            print(f"  {line}")
        return 1
    print(f"\nPASS — {len(argv)} page(s): every text node >= {MIN_PX:.0f}px and >= "
          f"{MIN_TEXT_CONTRAST}:1 over its COMPOSITED background, controls canonical, "
          f"an outer gutter of at least min({GUTTER_FLOOR_PX:.0f}px, "
          f"{GUTTER_FLOOR_VW * 100:.0f}vw), no horizontal scroll")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
