"""Browser audit harness that proves the route before it measures the page.

Why this exists: an earlier audit reported "zero contrast failures across nine
surfaces". Six of those nine were the login page. Repeated test logins had
tripped the account lockout, every authenticated request came back 423, and the
browser dutifully measured the lockout screen six times and attributed the
numbers to six admin routes.

So measurement is gated on identity. `open_route` returns evidence, not just a
page, and refuses to hand back a page whose identity it could not establish.
"""
import json, re, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8096"
PW = "ReviewOnly!Aa1x9"

# A marker that must be present for the route to count as "actually rendered".
ROUTE_MARKERS = {
    "/admin/heatmap":          "#jordanMap, .cs-left, .intel-panel, [id*=map]",
    "/admin/kpi":              "[id*=kpi i]",   # the page uses ids, not kpi-* classes
    "/admin/analytics/charts": "#chartsExplorerRoot, .ce-hero, .ce-kpi-strip",
    "/admin/dashboard":        ".admin-card, .admin-dashboard, [class*=dashboard]",
    "/admin/agency-reports":   ".agency-card, .agency-page-header, [class*=agency]",
    "/admin/profile":          "form, .admin-card",
    "/dashboard":              "main, .container, .card",
    "/manager/kpi":            "[class*=kpi], .card",
    "/login":                  "input[type=password]",
    "/register":               "form",
    "/forgot-password":        "form",
    "/":                       "main, body",
}

CONTRAST_JS = r"""
() => {
  const lum = c => { const [r,g,b] = c.map(v => { v/=255;
      return v <= 0.03928 ? v/12.92 : Math.pow((v+0.055)/1.055, 2.4); });
    return 0.2126*r + 0.7152*g + 0.0722*b; };
  const parse = s => { const m = String(s).match(/rgba?\(([^)]+)\)/); if (!m) return null;
    const p = m[1].split(',').map(x => parseFloat(x));
    return { rgb: p.slice(0,3), a: p.length > 3 ? p[3] : 1 }; };

  // Effective backing: walk ancestors and COMPOSITE translucent layers over
  // whatever is behind them, which is what the pixel actually shows. Bailing on
  // any alpha (the previous behaviour) reported white-on-blue header buttons as
  // white-on-light-grey, because a 12%-white button surface was resolved to a
  // guess instead of being composited over the header. Only a background IMAGE
  // is still indeterminate: a gradient or photo has no single colour.
  const over = (fg, bg) => fg.rgb.map((c, i) => c * fg.a + bg[i] * (1 - fg.a));

  // A background IMAGE used to abort the whole measurement. That was too
  // blunt: nearly every dark panel in this app is painted with a linear
  // gradient, so those nodes were reported "indeterminate" and silently never
  // checked -- 29 on /admin/heatmap alone. A real 3.06:1 failure on
  // .kpi-label hid there until Firefox happened to report the same card as a
  // translucent colour instead of a gradient and composited it.
  //
  // A gradient has no single colour, so instead of guessing an average this
  // returns EVERY colour stop as a candidate ground and the caller takes the
  // worst ratio. That is the honest reading: text over a gradient has to be
  // legible against the whole gradient, not against its mean.
  //
  // Anything with no parseable colour stops -- url(), image-set(), a
  // cross-origin texture -- is still genuinely indeterminate and still bails.
  // background-image can hold SEVERAL layers, comma-separated, painted first
  // = topmost. Splitting has to respect parens: gradients are full of commas.
  const splitLayers = s => {
    const out = []; let depth = 0, cur = '';
    for (const ch of s) {
      if (ch === '(') depth++;
      if (ch === ')') depth--;
      if (ch === ',' && depth === 0) { out.push(cur); cur = ''; continue; }
      cur += ch;
    }
    if (cur.trim()) out.push(cur);
    return out.map(x => x.trim()).filter(Boolean);
  };

  const layerStops = layer => {
    if (!/gradient\(/.test(layer)) return null;            // url(), image-set()
    const found = layer.match(/rgba?\([^)]+\)/g);
    if (!found || !found.length) return null;
    const stops = found.map(parse).filter(Boolean);
    return stops.length ? stops : null;
  };

  // Composite the layers BOTTOM-UP over whatever is behind them. This is the
  // part that has to be right: a top layer's `transparent` stop reveals the
  // layer BELOW it, not the page canvas. Treating every stop as if it sat
  // directly on the parent reported the dark-green /my-reports hero as
  // near-white and its white heading as 1.05:1, which was a harness bug, not
  // a page defect -- .reports-hero is
  //   radial-gradient(..., rgba(201,135,67,.2), transparent 28%),
  //   linear-gradient(135deg, #163d2e, #1f5e47, #2f7d62)
  // and the dark green underneath is what the text actually sits on.
  const compositeLayers = (cssImage, behindGrounds) => {
    // `none` is a layer that paints NOTHING -- it is not an unknowable image.
    // .admin-page-header computes to `linear-gradient(...), none`, and treating
    // that trailing `none` as unparseable made layerStops bail, so the whole
    // header came back indeterminate: 2 nodes per engine on /admin/dashboard
    // (h1.admin-page-title, p.admin-page-subtitle) were never measured at all.
    // Dropping it is the correct semantics and keeps a real url() bailing.
    const layers = splitLayers(cssImage).filter(l => l !== 'none');
    const parsed = layers.map(layerStops);
    if (parsed.some(x => x === null)) return null;          // an opaque image: unknowable
    let grounds = behindGrounds.slice();
    for (let i = parsed.length - 1; i >= 0; i--) {          // bottom layer first
      const next = [];
      for (const g of grounds) {
        for (const s of parsed[i]) {
          next.push(s.a > 0.999 ? s.rgb : over(s, g));
        }
      }
      // Keep the extremes rather than every combination: the darkest and the
      // lightest candidate bound the contrast range, and the count would
      // otherwise multiply out layer by layer.
      next.sort((a, b) => lum(a) - lum(b));
      grounds = next.length > 6 ? [next[0], next[Math.floor(next.length/2)], next[next.length-1]] : next;
    }
    return grounds;
  };

  const backing = el => {
    const stack = [];
    let n = el;
    while (n && n !== document.documentElement) {
      const cs = getComputedStyle(n);
      if (cs.backgroundImage && cs.backgroundImage !== 'none') {
        // Resolve what sits BEHIND this element first; it may itself be a
        // gradient (nested panels are common here), so normalise to a list.
        const behind = n.parentElement ? backing(n.parentElement) : { rgb: [255, 255, 255] };
        if (behind.i) return { i: true };
        const behindGrounds = behind.grounds ? behind.grounds : [behind.rgb];
        const composed = compositeLayers(cs.backgroundImage, behindGrounds);
        if (!composed) return { i: true };                  // genuinely unknowable
        const grounds = composed.map(base => {
          for (let k = stack.length - 1; k >= 0; k--) base = over(stack[k], base);
          return base;
        });
        return { grounds };
      }
      const b = parse(cs.backgroundColor);
      if (b && b.a > 0.999) {                     // opaque: stop here
        let base = b.rgb;
        for (let k = stack.length - 1; k >= 0; k--) base = over(stack[k], base);
        return { rgb: base };
      }
      if (b && b.a > 0.004) stack.push(b);        // translucent: remember it
      n = n.parentElement;
    }
    const b = parse(getComputedStyle(document.body).backgroundColor);
    let base = b && b.a > 0.999 ? b.rgb : [255, 255, 255];
    for (let k = stack.length - 1; k >= 0; k--) base = over(stack[k], base);
    return { rgb: base };
  };

  const fails = [], indet = [];
  document.querySelectorAll('*').forEach(el => {
    const t = [...el.childNodes].filter(n => n.nodeType === 3)
                .map(n => n.nodeValue.trim()).join('');
    if (!t) return;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return;
    if (parseFloat(cs.opacity) === 0) return;
    const r = el.getBoundingClientRect(); if (r.width < 1 || r.height < 1) return;
    // Screen-reader-only text paints no pixels, so its contrast is meaningless.
    // Bootstrap's .visually-hidden is 1x1 with clip:rect(0,0,0,0), which slips
    // past the size check above and reported four "failures" on /kpi/dashboard
    // for text no sighted user can see. Excluding it removes noise, not debt --
    // any element that is genuinely visible still has clip/clip-path 'auto'/'none'.
    const clip = cs.clip, cp = cs.clipPath;
    if ((clip && clip !== 'auto' && /rect\(\s*0/.test(clip)) ||
        (cp && cp !== 'none' && /inset\(\s*(50%|100%)/.test(cp))) return;
    const fg = parse(cs.color); if (!fg || fg.a < 0.95) return;
    const bg = backing(el);
    const sel = el.tagName.toLowerCase() +
                (el.className ? '.' + String(el.className).split(' ').filter(Boolean)[0] : '');
    if (bg.i) { indet.push(sel); return; }
    const L1 = lum(fg.rgb);
    // Over a gradient, take the WORST stop: the text has to work everywhere.
    const grounds = bg.grounds ? bg.grounds : [bg.rgb];
    let ratio = Infinity, worst = grounds[0];
    for (const g of grounds) {
      const L2 = lum(g);
      const r = (Math.max(L1,L2) + 0.05) / (Math.min(L1,L2) + 0.05);
      if (r < ratio) { ratio = r; worst = g; }
    }
    const px = parseFloat(cs.fontSize), bold = parseInt(cs.fontWeight) >= 700;
    const need = (px >= 24 || (px >= 18.66 && bold)) ? 3 : 4.5;
    if (ratio < need) fails.push({ ratio: +ratio.toFixed(2), need,
        fg: cs.color, bg: 'rgb(' + worst.join(', ') + ')', px, sel,
        text: t.slice(0, 24) });
  });

  const small = [...document.querySelectorAll('*')].filter(e => {
    const t = [...e.childNodes].filter(n => n.nodeType === 3)
                .map(n => n.nodeValue.trim()).join('');
    if (!t) return false; const cs = getComputedStyle(e);
    return cs.display !== 'none' && parseFloat(cs.fontSize) < 12 &&
           !/Roboto/.test(cs.fontFamily); }).length;

  const glass = [...document.querySelectorAll('*')].filter(e => {
    const f = getComputedStyle(e).backdropFilter; return f && f !== 'none'; }).length;

  return { fails, indeterminate: indet.length, sub12: small, glass,
           overflow: document.documentElement.scrollWidth > window.innerWidth + 1,
           dir: document.documentElement.dir, lang: document.documentElement.lang,
           visibility: getComputedStyle(document.documentElement).visibility,
           title: document.title.slice(0, 60) };
}
"""


class RouteIdentityError(AssertionError):
    """The page measured was not the page requested."""


def login(ctx, email, base=BASE):
    pg = ctx.new_page()
    pg.goto(base + "/login", wait_until="domcontentloaded")
    pg.fill('input[name="username"], input[name="email"], #email, #username', email)
    pg.fill('input[type="password"]', PW)
    pg.click('button[type="submit"]')
    pg.wait_for_load_state("networkidle")
    return pg


def open_route(pg, path, base=BASE, settle=800):
    """Navigate and PROVE identity. Raises RouteIdentityError otherwise."""
    resp = pg.goto(base + path, wait_until="networkidle")
    pg.evaluate("document.fonts.ready")
    if settle:
        pg.wait_for_timeout(settle)
    status = resp.status if resp else None
    final = pg.evaluate("location.pathname")
    ev = {"requested": path, "final": final, "status": status,
          "title": pg.title()[:60]}

    if status in (401, 403, 423):
        raise RouteIdentityError(f"{path}: status {status} — not an authenticated render")
    if final != path:
        raise RouteIdentityError(f"{path}: landed on {final} — wrong surface")
    if "/login" in final and path != "/login":
        raise RouteIdentityError(f"{path}: login substitution detected")

    marker = ROUTE_MARKERS.get(path)
    if marker:
        found = pg.evaluate("(m) => !!document.querySelector(m)", marker)
        ev["marker"] = marker
        ev["marker_found"] = found
        if not found:
            raise RouteIdentityError(f"{path}: route marker {marker!r} absent — page did not render")
    return ev


def audit(pg, path, base=BASE):
    ev = open_route(pg, path, base)
    data = pg.evaluate(CONTRAST_JS)
    data["identity"] = ev
    return data
