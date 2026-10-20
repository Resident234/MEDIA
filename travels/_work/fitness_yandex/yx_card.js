(() => {
  // Probe one organisation card: what contacts / messengers / coords are exposed.
  const out = {
    url: location.href,
    title: document.title,
    h1: (() => { const e = document.querySelector('h1'); return e ? e.innerText.trim() : null; })(),
    ratingAria: Array.from(document.querySelectorAll('[aria-label*="ценка"]'))
      .map(e => e.getAttribute('aria-label')).slice(0, 5),
    coordsAttr: Array.from(document.querySelectorAll('[data-coordinates]'))
      .map(e => e.getAttribute('data-coordinates')).slice(0, 5),
    // phone-like elements
    phones: Array.from(document.querySelectorAll('[class*="phone"]')).map(e => ({
      cls: e.className && String(e.className).slice(0, 60),
      t: e.innerText.replace(/\s+/g, ' ').slice(0, 120),
      href: e.href || (e.querySelector('a') ? e.querySelector('a').href : null)
    })).slice(0, 20),
    links: Array.from(document.querySelectorAll('a[href]')).map(a => ({
      t: a.innerText.replace(/\s+/g, ' ').trim().slice(0, 60),
      h: a.href.slice(0, 220),
      cls: a.className ? String(a.className).slice(0, 60) : ''
    })).filter(l => !/login\.yandex|passport|static\.|apple\.com|google\.|\/maps\/set|\/maps$/i.test(l.h)).slice(0, 60),
    buttons: Array.from(document.querySelectorAll('button')).map(b =>
      b.innerText.replace(/\s+/g, ' ').trim().slice(0, 50)).filter(t => t).slice(0, 40)
  };
  return JSON.stringify(out);
})()
