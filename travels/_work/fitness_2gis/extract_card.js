// Extraction run on a 2GIS web card: contacts, messengers, hours, prices.
(() => {
  const abs = (h) => { try { return new URL(h, location.href).href; } catch (e) { return h; } };
  const txt = document.body ? document.body.innerText : "";
  const links = Array.from(document.querySelectorAll("a")).map((a) => ({
    href: a.getAttribute("href") || "",
    full: abs(a.getAttribute("href") || ""),
    text: (a.innerText || a.title || a.getAttribute("aria-label") || "").trim().slice(0, 120),
  }));
  const pick = (re, useFull) =>
    Array.from(new Set(links.filter((l) => re.test(useFull ? l.full + " " + l.text : l.href + " " + l.text))
      .map((l) => (useFull ? l.full : l.href))));
  const btns = Array.from(document.querySelectorAll("button")).map((b) => (b.innerText || b.getAttribute("aria-label") || "").trim().slice(0, 60)).filter(Boolean);
  return JSON.stringify({
    url: location.href,
    title: document.title,
    len: txt.length,
    tel: pick(/^tel:|tel:/i, false),
    wa: pick(/wa\.me|whatsapp/i, true),
    tg: pick(/t\.me|telegram/i, true),
    ig: pick(/instagram\.com/i, true),
    vk: pick(/vk\.com/i, true),
    fb: pick(/facebook\.com|fb\.com/i, true),
    yt: pick(/youtube\.com/i, true),
    site: pick(/^https?:\/\//i, true).filter((u) => !/2gis|yandex|google|apple|play\.market|vk\.com|instagram|facebook|youtube|wa\.me|t\.me/i.test(u)),
    btns: Array.from(new Set(btns)).slice(0, 40),
    captcha: /captcha|подозрительная активность|робот|не бот/i.test(txt.slice(0, 1200)) || /captcha/i.test(location.href),
    snippet: txt.slice(0, 2500),
  });
})()
