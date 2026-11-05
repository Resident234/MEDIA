// Google Maps place-card extractor.
// Emits: name, url, lat, lon, rating, reviews, category, phone, website_url,
// website_host, address, hours_today, hours_week[], plus the raw item-id list.
(() => {
  const out = {url: location.href};
  const main = document.querySelector('div[role="main"]') || document.body;

  // --- name ---
  const h1 = main.querySelector('h1.DUwDvf, h1');
  out.name = h1 ? h1.textContent.trim() : null;

  // --- coordinates: prefer <meta>, then URL !8m2!3d<lat>!4d<lon> segment ---
  const coord = document.querySelector('meta[itemprop="coordinates"]');
  if (coord) {
    const parts = (coord.getAttribute('content') || '').split(',').map(s => s.trim());
    out.lat = parseFloat(parts[0]);
    out.lon = parseFloat(parts[1]);
  }
  if (!isFinite(out.lat) || !isFinite(out.lon)) {
    const m = location.href.match(/!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)/);
    if (m) { out.lat = parseFloat(m[1]); out.lon = parseFloat(m[2]); }
  }
  if (!isFinite(out.lat) || !isFinite(out.lon)) {
    const m = location.href.match(/@(-?\d+\.\d+),(-?\d+\.\d+),\d+z/);
    if (m) { out.lat = parseFloat(m[1]); out.lon = parseFloat(m[2]); }
  }

  // --- rating + reviews (from the F7nice block near the top) ---
  const f7 = main.querySelector('div.F7nice');
  out.rating = null; out.reviews = null;
  if (f7) {
    const rs = f7.querySelector('span[aria-hidden="true"]');
    if (rs) out.rating = parseFloat((rs.textContent || '').replace(',', '.'));
    const ra = f7.querySelector('span[aria-label]');
    if (ra) {
      const m = (ra.getAttribute('aria-label') || '').replace(/[^\d]/g, '');
      if (m) out.reviews = parseInt(m, 10);
    }
    if (out.reviews == null) {
      const m2 = (f7.textContent || '').match(/\(([\d\s\u00a0\u202F]+)\)/);
      if (m2) out.reviews = parseInt(m2[1].replace(/[^\d]/g, ''), 10);
    }
  }

  // --- category (a BUTTON.DkEaL like «Фитнес-клуб» under the rating block) ---
  out.category = null;
  const catBtn = main.querySelector('button.DkEaL, button[class*="DkEaL"], button[data-item-id^="category:"]');
  if (catBtn) {
    out.category = (catBtn.textContent || catBtn.getAttribute('aria-label') || '').trim() || null;
  }
  if (!out.category) {
    // Walk text nodes: category often appears as a top-level text right after h1
    const body = (main.innerText || '').split('\n').map(s => s.trim()).filter(Boolean);
    const idx = body.findIndex(s => s === out.name);
    if (idx >= 0) {
      // skip rating number and reviews "(...)" line
      for (let i = idx + 1; i < Math.min(idx + 6, body.length); i++) {
        const s = body[i];
        if (/^(Посмотреть|Добавить|Проложить|Сохранить|Поделиться|Отправить|Оставить|Позвонить|Написать|Открыто|Закрыто|Круглосуточно|Пользователи|Также искали|Фото|Вопросы|Отзывы|Часы|Описание|Подробнее|Оценить)/i.test(s)) continue;
        if (/^\d+[.,]\d$/.test(s)) continue;
        if (/^\(\d+\)$/.test(s)) continue;
        if (/^(Открыто|Закрыто)/i.test(s)) continue;
        if (s.length > 2 && s.length < 60 && !/^\s*$/.test(s)) { out.category = s; break; }
      }
    }
  }

  // --- info buttons: address / phone / authority(website) / oloc / label ---
  out.phone = null; out.address = null; out.website_host = null; out.website_url = null;
  const items = [];
  for (const b of main.querySelectorAll('[data-item-id]')) {
    const id = b.getAttribute('data-item-id') || '';
    const aria = (b.getAttribute('aria-label') || '').trim();
    items.push({tag: b.tagName, id: id, aria: aria.slice(0, 200)});
    if (id === 'address' || id.startsWith('address:')) {
      out.address = (aria.replace(/^Адрес:\s*/i, '') || '').trim() || null;
    } else if (id.startsWith('phone:')) {
      out.phone = (aria.replace(/^Телефон:\s*/i, '') || '').trim() || null;
    } else if (id === 'authority' || id.startsWith('website:')) {
      const host = (aria.replace(/^Сайт:\s*/i, '') || '').trim();
      if (host) out.website_host = host;
      const a = b.tagName === 'A' ? b : b.querySelector('a[href^="http"]');
      if (a) out.website_url = a.href;
    }
  }
  out.info_items = items;
  if (!out.website_url && out.website_host) {
    out.website_url = 'https://' + out.website_host;
  }

  // --- hours: aria-labels like "четверг,07:00-23:00, Скопировать часы работы" ---
  out.hours_today = null;
  out.hours_week = [];
  const seenHours = new Set();
  for (const e of main.querySelectorAll('[aria-label]')) {
    const v = e.getAttribute('aria-label') || '';
    const m = v.match(/^(понедельник|вторник|среда|четверг|пятница|суббота|воскресенье),(\d{1,2}:\d{2}[^\s,]*--[^\s,]*|\d{1,2}:\d{2}[–\-]\d{1,2}:\d{2})/i);
    if (m) {
      const line = m[1] + ': ' + m[2];
      if (!seenHours.has(line)) { seenHours.add(line); out.hours_week.push(line); }
      if (!out.hours_today) out.hours_today = line;
    }
  }
  if (!out.hours_today) {
    // Fall back to the "Открыто · Закрывается в 23:00" text near the top
    const t = (main.innerText || '');
    const m = t.match(/(Открыто|Закрыто|Круглосуточно)[^\n]{0,60}/i);
    if (m) out.hours_today = m[0].trim();
  }

  return JSON.stringify(out);
})()
