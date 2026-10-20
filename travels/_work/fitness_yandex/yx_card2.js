(() => {
  // Extract the contact payload of one organisation card.
  //
  // Trap to avoid: the card footer carries Yandex's OWN social links
  // (vk.com/yandex.maps, t.me/mapsyandex, zen.yandex.ru). Those are not the
  // organisation's Telegram, so messenger links are only accepted when they
  // do not point at a Yandex property and are taken with their class + label.
  const q = (s) => Array.from(document.querySelectorAll(s));
  const txt = (e) => (e.innerText || "").replace(/\s+/g, " ").trim();
  const MSG = /wa\.me|api\.whatsapp|whatsapp|t\.me|telegram\.(me|org)|tg:\/\/|viber|instagram|facebook|vk\.com/i;
  const YX = /yandex|mapsyandex|zen\.yandex|vk\.com\/yandex\.maps/i;

  const anchors = q('a[href]').map(a => ({ t: txt(a).slice(0, 60), h: a.href, c: String(a.className).slice(0, 70) }));
  const msgLinks = anchors.filter(l => MSG.test(l.h)).map(l => ({
    t: l.t, h: l.h, c: l.c, ownOrg: YX.test(l.h) ? 0 : 1 }));
  const extLinks = q('[class*="business-urls-view"] a[href], [class*="website"] a[href]')
    .map(a => ({ t: txt(a).slice(0, 60), h: a.href }));
  const phones = q('[class*="phones-view__phone-number"], [class*="phones-view__number"], a[href^="tel:"]')
    .map(e => ({ t: txt(e).slice(0, 60), h: e.getAttribute('href') }));
  const social = q('[class*="social-links-view"] a[href], [class*="social"] a[href]')
    .map(a => ({ t: txt(a).slice(0, 40), h: a.href, c: String(a.className).slice(0, 70) }));
  const btns = q('button[class*="whatsapp"], button[class*="telegram"], a[class*="whatsapp"], a[class*="telegram"], [class*="messenger"]')
    .map(e => ({ tag: e.tagName, c: String(e.className).slice(0, 80), t: txt(e).slice(0, 60), h: e.href || null }));
  const emails = anchors.filter(l => /^mailto:/i.test(l.h)).map(l => l.h);
  const contactBlock = q('[class*="business-contacts-view"]').map(txt);

  return JSON.stringify({
    url: location.href,
    title: document.title,
    h1: (() => { const e = document.querySelector('h1'); return e ? txt(e) : null; })(),
    coords: q('[data-coordinates]').map(e => e.getAttribute('data-coordinates')),
    rating: q('[aria-label*="ценка"]').map(e => e.getAttribute('aria-label')).slice(0, 3),
    categories: q('[class*="categories-info-view"] a').map(txt),
    address: q('[class*="header-view__address"], [class*="contacts-view__address"]')
      .map(e => ({ t: txt(e).slice(0, 120), h: e.getAttribute('href') })).slice(0, 4),
    phones: phones,
    msgLinks: msgLinks,
    extLinks: extLinks,
    social: social,
    btns: btns,
    emails: emails,
    contactBlock: contactBlock,
    hours: q('[class*="workbench-view"], [class*="working-time"], [class*="business-hours"]')
      .map(e => txt(e).slice(0, 160)).slice(0, 3)
  });
})()
