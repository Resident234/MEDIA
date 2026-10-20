(() => {
  // Card detail tab (?tab=features) + generic link dump of whatever page is
  // loaded (also reused for the organisation's own website).
  const q = (s) => Array.from(document.querySelectorAll(s));
  const txt = (e) => (e.innerText || "").replace(/\s+/g, " ").trim();
  const MSG = /wa\.me|api\.whatsapp|whatsapp|t\.me|telegram\.me|telegram\.org|tg:\/\//i;
  return JSON.stringify({
    url: location.href,
    title: document.title,
    h1: (() => { const e = document.querySelector('h1'); return e ? txt(e).slice(0, 80) : null; })(),
    msgLinks: q('a[href]').filter(a => MSG.test(a.href))
      .map(a => ({ t: txt(a).slice(0, 60), h: a.href.slice(0, 200) })).slice(0, 25),
    phones: q('a[href^="tel:"]').map(a => ({ t: txt(a).slice(0, 40), h: a.getAttribute('href') })).slice(0, 10),
    emails: q('a[href^="mailto:"]').map(a => a.getAttribute('href')).slice(0, 5),
    tgHandles: (txt(document.body).match(/@[A-Za-z][\w]{3,}/g) || []).slice(0, 20),
    // contact-ish rows of the details tab
    rows: q('[class*="feature"] , [class*="details"] dt, [class*="details"] dd, [class*="business-contacts"] li')
      .map(e => txt(e).slice(0, 100)).filter(t => t).slice(0, 40),
    bodyHas: {
      whatsapp: /whatsapp|ватсап|ватсап|вотсап/i.test(txt(document.body)),
      telegram: /telegram|телеграм/i.test(txt(document.body))
    },
    // ±90 chars around every mention, to attribute a handle to the right club
    ctx: (() => {
      const t = txt(document.body);
      const res = [];
      const rx = /(?:whatsapp|ватсап|вотсап|telegram|телеgram|телеграм|t\.me|wa\.me|[A-Za-z0-9_.]+@[A-Za-z][\w]{3,})/gi;
      let m;
      while ((m = rx.exec(t)) && res.length < 12) {
        res.push(t.slice(Math.max(0, m.index - 90), m.index + 110));
        rx.lastIndex += 200;
      }
      return res;
    })(),
    textHead: txt(document.body).slice(0, 600)
  });
})()
