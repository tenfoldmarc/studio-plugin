// Runs inside every slide before the screenshot. Three jobs:
//  1. "fit lines": when the look sets --fit: lines on a headline, every loud line is sized to fill the width
//     (the poster look: short lines get huge, long lines get smaller). Quiet lines ((...)) keep their size.
//  2. Nothing may spill: when the content is taller than the body, shrink the headline first, then the middle,
//     then everything, a little at a time. Long words that are wider than their box are shrunk on their own.
//  3. The check: write what is still wrong into #qa (read back by render.py) and the zone positions into CSS vars
//     (--zb-top, --zt-bottom, ...) so a look can hang decoration off them (a sun behind the bottom zone).
(function () {
  const S = document.querySelector('.slide');
  const body = S.querySelector('.body');
  const css = (el, p) => getComputedStyle(el).getPropertyValue(p).trim();
  const px = (v, d) => { const n = parseFloat(v); return isFinite(n) ? n : d; };
  const fsz = el => parseFloat(getComputedStyle(el).fontSize);
  const notes = [];

  function fitLines() {
    S.querySelectorAll('.hl').forEach(hl => {
      if (css(hl, '--fit') !== 'lines') return;
      const width = (hl.closest('.zt') || hl.parentElement).clientWidth;   // the column, not the headline (it may hug its lines)
      const lo = px(css(hl, '--fit-min'), 60), hi = px(css(hl, '--fit-max'), 260);
      const wide = css(hl, '--fit-wide'), narrow = css(hl, '--fit-narrow'), cut = px(css(hl, '--fit-cut'), 8);
      hl.querySelectorAll('.ln:not(.q)').forEach(ln => {
        // a variable-width face: short punch lines go wide, long lines go narrow (only when the look sets both)
        if (wide && narrow) ln.style.fontStretch = ln.textContent.trim().length <= cut ? wide : narrow;
        ln.style.width = 'max-content';   // a flex item stretches to the box; measure the words themselves
        const w = ln.getBoundingClientRect().width;
        ln.style.width = '';
        if (!w) return;
        const size = Math.max(lo, Math.min(hi, fsz(ln) * width / w * 0.995));
        ln.style.fontSize = size.toFixed(1) + 'px';
      });
    });
  }

  function widthFix() {   // a single word wider than its box: shrink that element until it fits
    S.querySelectorAll('.body *').forEach(el => {
      if (!el.firstChild || el.children.length > 3) return;
      // never below 60% of its size: past that the overflow is a decoration (a bubble tail), or the words must be cut
      let guard = 0;
      const floor = fsz(el) * 0.6;
      while (el.scrollWidth > el.clientWidth + 1 && el.clientWidth > 0 && fsz(el) * 0.95 >= floor && guard++ < 40) {
        el.style.fontSize = (fsz(el) * 0.95).toFixed(1) + 'px';
      }
    });
    S.querySelectorAll('.hl .ln').forEach(ln => {
      let guard = 0;
      const box = (ln.closest('.zt') || ln.parentElement).clientWidth;
      while (ln.scrollWidth > box + 1 && guard++ < 40) ln.style.fontSize = (fsz(ln) * 0.96).toFixed(1) + 'px';
    });
  }

  function overflow() {
    S.classList.add('measuring');
    const kids = [...body.children];
    let need = 0;
    if (kids.length) {
      const top = kids[0].getBoundingClientRect().top;
      const bottom = Math.max(...kids.map(k => k.getBoundingClientRect().bottom));
      need = bottom - top;
    }
    S.classList.remove('measuring');
    return need - body.clientHeight;
  }

  function scaleAll(sel, k) { S.querySelectorAll(sel).forEach(el => { el.style.fontSize = (fsz(el) * k).toFixed(2) + 'px'; }); }
  function shrink() {
    let guard = 0, hlK = 1, midK = 1, allK = 1;
    while (overflow() > 1 && guard++ < 60) {
      if (hlK > 0.72) { scaleAll('.hl .ln', 0.96); hlK *= 0.96; continue; }
      const zm = S.querySelector('.zm');
      if (zm && midK > 0.7) { zm.style.zoom = (midK *= 0.95).toFixed(3); continue; }
      if (allK > 0.6) { body.style.zoom = (allK *= 0.96).toFixed(3); continue; }
      break;
    }
    if (hlK < 0.99 || midK < 0.99 || allK < 0.99)
      notes.push(`shrunk to fit (headline ${Math.round(hlK * 100)}%, middle ${Math.round(midK * 100)}%, all ${Math.round(allK * 100)}%)`);
    const left = overflow();
    if (left > 1) notes.push(`TOO MUCH: content is ${Math.round(left)}px taller than the slide allows. Cut words.`);
  }

  function tooWide(box) {   // anything inside poking out of the box sideways
    const r = box.getBoundingClientRect();
    return [...box.querySelectorAll('*')].some(el => { const e = el.getBoundingClientRect(); return e.width > 24 && (e.right > r.right + 6 || e.left < r.left - 6); });   // small marks (a rotated dot) may poke out a hair
  }

  function grow() {   // a lot of empty room: let the middle grow (up to --zm-grow) so the slide has no dead space
    const zm = S.querySelector('.zm');
    const max = px(css(S, '--zm-grow'), 1);
    if (!zm || max <= 1 || overflow() > -160) return;
    if (zm.querySelector(':scope > [style*="height"]')) return;   // a block given its own height keeps it
    let z = 1, guard = 0;
    while (z < max && guard++ < 40) {
      zm.style.zoom = (z * 1.03).toFixed(3);
      if (overflow() > -60 || tooWide(zm)) { zm.style.zoom = z.toFixed(3); break; }
      z *= 1.03;
    }
  }

  // a person standing on the bottom edge: the text must never cover the head. Their head is the top part of the
  // picture (--head, default 34%); shrink the picture until no text overlaps it, or say so.
  function clearHead() {
    const fig = S.querySelector('.stage-img');
    if (!fig) return;
    const img = fig.querySelector('img');
    const share = px(css(S, '--head'), 0.34);
    const texts = [...S.querySelectorAll('.body .hl .ln, .body p, .body li, .body .payload, .body .callout, .body .kw, .body .cta-word, .body .big')];
    const hits = () => {
      const r = img.getBoundingClientRect();
      const head = { top: r.top, bottom: r.top + r.height * share, left: r.left + r.width * 0.2, right: r.right - r.width * 0.2 };
      return texts.some(t => { const e = t.getBoundingClientRect(); return e.width && e.left < head.right && e.right > head.left && e.top < head.bottom && e.bottom > head.top; });
    };
    let h = fig.getBoundingClientRect().height, guard = 0;
    const start = h;
    while (hits() && h > S.clientHeight * 0.3 && guard++ < 60) { h *= 0.97; fig.style.height = h.toFixed(0) + 'px'; }
    if (hits()) notes.push('TEXT OVER THE FACE: the headline covers the head of the person in the picture. Shorten it or use a smaller picture.');
    else if (h < start - 1) notes.push(`picture made smaller to keep the face clear (${Math.round(h / start * 100)}%)`);
  }

  // the face of a marked photo, in page coordinates
  function faceRect(img) {
    const f = img.dataset.face.split(',').map(Number);
    if (f.length < 4 || !img.naturalWidth) return null;
    const r = img.getBoundingClientRect(), cs = getComputedStyle(img);
    let rw = r.width, rh = r.height, ox = 0, oy = 0;
    if (cs.objectFit === 'cover' || cs.objectFit === 'contain') {
      const k = (cs.objectFit === 'cover' ? Math.max : Math.min)(r.width / img.naturalWidth, r.height / img.naturalHeight);
      rw = img.naturalWidth * k; rh = img.naturalHeight * k;
      const pos = cs.objectPosition.split(' ').map(v => v.endsWith('%') ? parseFloat(v) / 100 : null);
      ox = (r.width - rw) * (pos[0] == null ? 0.5 : pos[0]);
      oy = (r.height - rh) * (pos[1] == null ? 0.5 : pos[1]);
    }
    const left = r.left + ox + rw * f[0] / 100, top = r.top + oy + rh * f[1] / 100;
    return { left, top, right: left + rw * f[2] / 100, bottom: top + rh * f[3] / 100 };
  }
  const TEXT_SEL = '.body .hl .ln, .body p, .body li, .body .payload, .body .callout, .body .kw, .body .big, .body .cta-word';
  const meets = (e, f) => e.width && e.left < f.right && e.right > f.left && e.top < f.bottom && e.bottom > f.top;

  // text sitting on a marked face moves off it: its zone slides above or below the face when there is room
  function dodgeFaces() {
    const faces = [...S.querySelectorAll('.bleed img[data-face], .stage-img img[data-face]')].map(faceRect).filter(Boolean);
    if (!faces.length) return;
    const b = body.getBoundingClientRect();
    ['.zt', '.zm', '.zb'].forEach(sel => {
      const z = S.querySelector(sel);
      if (!z) return;
      const zr = z.getBoundingClientRect();
      faces.forEach(f => {
        if (![...z.querySelectorAll('*')].some(t => meets(t.getBoundingClientRect(), f))) return;
        const others = ['.zt', '.zm', '.zb'].filter(s => s !== sel).map(s => S.querySelector(s)).filter(Boolean).map(o => o.getBoundingClientRect());
        const fits = dy => zr.top + dy >= b.top - 1 && zr.bottom + dy <= b.bottom + 1 &&
          !others.some(o => o.left < zr.right && o.right > zr.left && o.top < zr.bottom + dy && o.bottom > zr.top + dy);
        const up = f.top - 24 - zr.bottom, down = f.bottom + 24 - zr.top;   // up < 0, down > 0
        const pick = [up, down].filter(fits).sort((a, c) => Math.abs(a) - Math.abs(c))[0];
        if (pick !== undefined) {
          z.style.transform = `translateY(${Math.round(pick)}px)`;
          notes.push('moved text off the face');
        }
      });
    });
  }

  // a photo behind the text with its face marked (data-face="x,y,w,h", % of the photo): no text may cover that face
  function faceCheck() {
    S.querySelectorAll('img[data-face]').forEach(img => {
      const f = img.dataset.face.split(',').map(Number);
      if (f.length < 4 || !img.naturalWidth) return;
      const r = img.getBoundingClientRect(), cs = getComputedStyle(img);
      let rw = r.width, rh = r.height, ox = 0, oy = 0;
      if (cs.objectFit === 'cover' || cs.objectFit === 'contain') {
        const k = (cs.objectFit === 'cover' ? Math.max : Math.min)(r.width / img.naturalWidth, r.height / img.naturalHeight);
        rw = img.naturalWidth * k; rh = img.naturalHeight * k;
        const pos = cs.objectPosition.split(' ').map(v => v.endsWith('%') ? parseFloat(v) / 100 : null);
        ox = (r.width - rw) * (pos[0] == null ? 0.5 : pos[0]);
        oy = (r.height - rh) * (pos[1] == null ? 0.5 : pos[1]);
      }
      const face = { left: r.left + ox + rw * f[0] / 100, top: r.top + oy + rh * f[1] / 100 };
      face.right = face.left + rw * f[2] / 100; face.bottom = face.top + rh * f[3] / 100;
      S.querySelectorAll('.body .hl .ln, .body p, .body li, .body .payload, .body .callout, .body .kw, .body .big, .stickers.front .sticker').forEach(t => {
        const e = t.getBoundingClientRect();
        if (e.width && e.left < face.right && e.right > face.left && e.top < face.bottom && e.bottom > face.top)
          notes.push(`TEXT OVER THE FACE: "${t.textContent.trim().slice(0, 40)}" covers the face in the photo. Move the text, or set "focus" so the face moves.`);
      });
    });
  }

  function zoomOf(el) { let z = 1; for (let e = el; e && e !== document; e = e.parentElement) { const v = parseFloat(getComputedStyle(e).zoom); if (v) z *= v; } return z; }

  function check() {
    // smallest readable text inside the body (the chrome is allowed to be small)
    let min = 1e9, minEl = '';
    S.querySelectorAll('.body *').forEach(el => {
      const own = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
      // small print by design (labels, the follow line) is allowed; reading text is not
      if (!own || el.closest('.chrome, .label, .pl-label, .note, .follow, .cw-pre, .media-label, .tag, cite, .versus .t')) return;
      if (!el.getClientRects().length) return;
      const s = fsz(el) * zoomOf(el);
      if (s < min) { min = s; minEl = el.textContent.trim().slice(0, 40); }
    });
    if (min < 1e9) {
      const floor = px(css(S, '--min-text'), 26);
      if (min < floor) notes.push(`SMALL TEXT: ${Math.round(min)}px ("${minEl}"). Under ${floor}px is hard to read on a phone.`);
    }
    // stickers: one that could not be drawn, and one in front that sits on reading text
    S.querySelectorAll('.sticker-error').forEach(e => notes.push(`STICKER BROKEN: ${e.dataset.error}`));
    const reading = [...S.querySelectorAll('.body .hl .ln, .body p, .body li, .body .payload, .body .callout, .body .kw')]
      .map(t => [t, t.getBoundingClientRect()]).filter(([, r]) => r.width);
    S.querySelectorAll('.stickers.front .sticker').forEach(st => {
      const s = st.getBoundingClientRect();
      if (!s.width) return;
      reading.forEach(([t, r]) => {
        const w = Math.min(s.right, r.right) - Math.max(s.left, r.left), h = Math.min(s.bottom, r.bottom) - Math.max(s.top, r.top);
        if (w > 0 && h > 0 && w * h > 0.25 * r.width * r.height)   // a corner overlap is styling; covering a quarter is not
          notes.push(`STICKER OVER TEXT: a ${[...st.classList].find(c => c.startsWith('st-')) || 'sticker'} covers "${t.textContent.trim().slice(0, 40)}". Move it.`);
      });
    });
    // a big empty band in the middle (no middle zone, top and bottom far apart): say so, the slide looks unfinished
    const zt = S.querySelector('.zt'), zb = S.querySelector('.zb');
    if (zt && zb && !S.querySelector('.zm') && !S.querySelector('.stage-img, .bleed')) {
      const gap = zb.getBoundingClientRect().top - zt.getBoundingClientRect().bottom;
      if (gap > S.clientHeight * 0.3)
        notes.push(`ROOM TO FILL: ${Math.round(gap)}px empty in the middle. Add a list, a picture or a number, or let the bottom part sit under the top ("css": ".zb{margin-top:0}").`);
    }
    // body text running into the chrome or off the slide
    const W = S.clientWidth, H = S.clientHeight, bodyR = body.getBoundingClientRect();
    const chrome = [...S.querySelectorAll('.chrome > *')].filter(c => c.offsetParent && getComputedStyle(c).visibility !== 'hidden')
      .map(c => c.getBoundingClientRect());
    S.querySelectorAll('.body .hl .ln, .body p, .body li, .body .pair, .body .chip, .body .card, .body .payload, .body .callout, .body .big, .body .kw, .body .media').forEach(el => {
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height) return;
      if (r.left < -1 || r.top < -1 || r.right > W + 1 || r.bottom > H + 1) notes.push(`OFF THE SLIDE: "${el.textContent.trim().slice(0, 40)}"`);
      else if (r.right > bodyR.right + 4 || r.left < bodyR.left - 4) notes.push(`PAST THE MARGIN: "${el.textContent.trim().slice(0, 40)}"`);
      chrome.forEach(c => {
        if (r.left < c.right && r.right > c.left && r.top < c.bottom && r.bottom > c.top)
          notes.push(`RUNS INTO THE CHROME: "${el.textContent.trim().slice(0, 40)}"`);
      });
    });
    return Math.round(min < 1e9 ? min : 0);
  }

  function vars() {
    const b = S.getBoundingClientRect();
    const set = (name, v) => S.style.setProperty(name, Math.round(v) + 'px');
    const zt = S.querySelector('.zt'), zm = S.querySelector('.zm'), zb = S.querySelector('.zb');
    if (zt) set('--zt-bottom', zt.getBoundingClientRect().bottom - b.top);
    if (zm) { const r = zm.getBoundingClientRect(); set('--zm-top', r.top - b.top); set('--zm-bottom', r.bottom - b.top); }
    const content = zb && zb.children.length ? zb : null;
    if (content) { const r = content.getBoundingClientRect(); set('--zb-top', r.top - b.top); set('--zb-h', r.height); }
    else set('--zb-top', b.height - px(css(S, '--pad-bottom'), 140) + 40);
  }

  function sizePictures() {   // a framed picture's box = the picture itself (portrait or landscape), never letterboxed
    S.querySelectorAll('.media:not(.cover) img').forEach(img => {
      const fig = img.parentElement, nw = img.naturalWidth, nh = img.naturalHeight;
      if (!nw || !nh || !fig.clientWidth || !fig.clientHeight) return;
      const k = Math.min(fig.clientWidth / nw, fig.clientHeight / nh);
      img.style.width = (nw * k).toFixed(0) + 'px';
      img.style.height = (nh * k).toFixed(0) + 'px';
      img.style.maxWidth = 'none';
    });
  }

  function run() {
    sizePictures();
    fitLines();
    widthFix();
    shrink();
    grow();
    widthFix();
    clearHead();
    dodgeFaces();
    faceCheck();
    const minText = check();
    vars();
    document.getElementById('qa').textContent = JSON.stringify({ notes: [...new Set(notes)], minText });
    document.documentElement.dataset.done = '1';
  }
  (document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve()).then(() => {
    const imgs = [...document.images].map(i => i.complete ? null : new Promise(r => { i.onload = i.onerror = r; })).filter(Boolean);
    Promise.all(imgs).then(run);
  });
})();
