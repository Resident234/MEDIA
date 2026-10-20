# -*- coding: utf-8 -*-
"""Turn the raw card dumps into the final Yandex table.

usage: python cards_parse.py <cards_dir> <list_jsonl> <out_jsonl> <out_tsv>

Only links that belong to the organisation are kept: the card footer always
carries Yandex's own social links (t.me/mapsyandex, vk.com/yandex.maps,
zen.yandex.ru), and those were flagged ownOrg=0 during extraction. wa.me URLs
are stripped of the pre-filled "?text=Обращение из Яндекс Карт..." boilerplate,
and the phone the messenger points at is cross-checked against the card phone.
"""
import glob
import io
import json
import os
import re
import sys

WA = re.compile(r"(?:https?://)?(?:www\.)?(wa\.me|api\.whatsapp\.com/send\?phone=)", re.I)
TG = re.compile(r"(?:https?://)?(?:www\.)?(t\.me|telegram\.me|telegram\.org|telegram\.dog)/", re.I)
HERE = os.path.dirname(os.path.abspath(__file__))


def clean_wa(h):
    """Drop the prefilled "text=Обращение из Яндекс Карт...", keep the number."""
    if "?" in h and "wa.me/" not in h:
        keep = [p for p in h.split("?", 1)[1].split("&") if p.startswith("phone=")]
        return h.split("?", 1)[0] + (("?" + "&".join(keep)) if keep else "")
    h = h.split("?")[0]
    return h if h.startswith("http") else "https://" + h


def msg_host(h, names):
    """True only if the link's own host is a messenger host.

    Sites get this wrong: dorobgym.tj publishes "https://dorobgym.tj/t.me/..."
    (a relative authoring mistake), and that is neither a Telegram link nor this
    club's channel, so it must not be folded into the row.
    """
    from urllib.parse import urlparse
    u = urlparse(h if "//" in h else "//" + h)
    host = (u.netloc or u.path).split(":")[0].lower()
    return any(host == n or host.endswith("." + n) for n in names)


def wa_num(h):
    """Digits of the phone a wa.me / api.whatsapp link points at."""
    m = re.search(r"(?:wa\.me/|phone=)(\d{6,})", h)
    return m.group(1) if m else ""


def tail(s, n=11):
    """Last n digits, used to compare a messenger number with the card phone."""
    return re.sub(r"\D", "", s or "")[-n:]


def main():
    cdir, listj, outj, outtsv = sys.argv[1:5]
    lst = {json.loads(l)["id"]: json.loads(l) for l in io.open(listj, encoding="utf-8") if l.strip()}
    rows = []
    for path in glob.glob(os.path.join(cdir, "*.json")):
        cid = os.path.basename(path)[:-5]
        d = json.load(io.open(path, encoding="utf-8"))
        meta = lst.get(cid, {})
        msg = [l for l in d.get("msgLinks", []) if l.get("ownOrg")]
        wa = [clean_wa(l["h"]) for l in msg
              if WA.search(l["h"]) and msg_host(l["h"], ("wa.me", "api.whatsapp.com", "whatsapp.com"))]
        tg = [l["h"].split("?")[0] for l in msg
              if TG.search(l["h"]) and msg_host(l["h"], ("t.me", "telegram.me", "telegram.org", "telegram.dog"))]
        phones = []
        for p in d.get("phones", []):
            t = re.sub(r"[^\d+]", "", p["t"] or "")
            if len(re.sub(r"\D", "", t)) >= 9 and t not in phones:
                phones.append(t)
        coords = (d.get("coords") or [meta.get("coords") or ""])[0]
        lon, lat = (coords.split(",") + ["", ""])[:2]
        rate = None
        for a in d.get("rating", []):  # first badge = the org rating, later ones are per-review
            m = re.search(r"Оценка (\d+[.,]\d+) Из", a)
            if m:
                rate = float(m.group(1).replace(",", "."))
                break
        wag = wa[0] if wa else None
        wan = wa_num(wag or "")
        soc = sorted({l["h"] for l in msg if not WA.search(l["h"]) and not TG.search(l["h"])})
        rows.append({
            "id": cid,
            "name": d.get("h1") or meta.get("name"),
            "url": (d.get("url") or meta.get("url") or "").split("?")[0],
            "lon": lon.strip(), "lat": lat.strip(),
            "rating": rate if rate is not None else meta.get("rating"),
            "rating_list": meta.get("rating"),
            "reviews": meta.get("reviews"),
            "address": (d.get("address") or [{}])[0].get("t"),
            "phones": phones,
            "whatsapp": wag,
            "wa_number": wan,
            "wa_is_card_phone": bool(wan) and any(tail(wan) == tail(p) for p in phones),
            "telegram": tg[0] if tg else None,
            "site": (d.get("extLinks") or [{}])[0].get("h"),
            "social_other": soc,
            "categories": d.get("categories"),
        })
    rows.sort(key=lambda r: -(r["rating"] or 0))

    # Second channel: the organisation's own website listed on the card. Kept in
    # separate *_site fields so a link published by the site is never presented
    # as if Yandex's card carried it.
    for r in rows:
        r["whatsapp_site"] = r["telegram_site"] = None
        r["site_msg_notes"] = []
        if not r.get("site"):
            continue
        host = re.sub(r"^https?://", "", r["site"]).rstrip("/")
        path = os.path.join(HERE, "extra", "site_" + re.sub(r"\W+", "_", host) + ".json")
        if not os.path.exists(path):
            continue
        s = json.load(io.open(path, encoding="utf-8"))
        for l in s.get("msgLinks", []):
            h = l["h"]
            if "t.me/https" in h or "t.me/http" in h:
                # "https://t.me/https://t.me/+xxxx" — the author pasted a full
                # URL after t.me/, so the href is broken and the invite itself
                # is not verifiable from the card; recorded, not repaired
                r["site_msg_notes"].append("битая ссылка в HTML: %s" % h)
                continue
            if WA.search(h) and msg_host(h, ("wa.me", "api.whatsapp.com", "whatsapp.com")):
                r["whatsapp_site"] = clean_wa(h)
            elif TG.search(h) and msg_host(h, ("t.me", "telegram.me", "telegram.org", "telegram.dog")):
                r["telegram_site"] = h.split("?")[0]
            elif TG.search(h) or WA.search(h):
                r["site_msg_notes"].append("ссылка на мессенджер не по адресу мессенджера: %s" % h)
        # broken authoring on the site is kept as a note, not silently repaired
        sp = [re.sub(r"[^\d+]", "", p["t"]) for p in s.get("phones", []) if p.get("t")]
        sp = [p for p in sp if len(re.sub(r"\D", "", p)) >= 9]
        if sp and r["phones"] and not any(tail(x) == tail(y) for x in sp for y in r["phones"]):
            r["site_msg_notes"].append("телефон сайта (%s) не совпадает с телефоном карточки (%s)"
                                       % (sp[0], r["phones"][0]))

    cols = ["name", "rating", "reviews", "lon", "lat", "whatsapp", "telegram",
            "whatsapp_site", "telegram_site", "phones", "site", "address", "url"]
    with io.open(outj, "w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    with io.open(outtsv, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\t".join(cols) + "\n")
        for r in rows:
            vals = []
            for c in cols:
                v = r[c]
                if c == "phones":
                    v = " / ".join(v or [])
                vals.append("" if v is None else str(v))
            fh.write("\t".join(vals) + "\n")
    print("cards parsed: %d  with whatsapp: %d  with telegram: %d  with phone: %d" %
          (len(rows), sum(1 for r in rows if r["whatsapp"]),
           sum(1 for r in rows if r["telegram"]), sum(1 for r in rows if r["phones"])))
    # Console codepage here is cp866: keep the progress line ASCII-safe, the
    # readable Cyrillic lives in the JSONL/TSV outputs.
    esc = lambda s: str(s).encode("unicode_escape").decode("ascii")
    for r in rows:
        print("  %-40s %s  wa=%s tg=%s" % (
            esc(r["name"])[:40], r["rating"], esc(r["whatsapp"] or "-")[:60],
            esc(r["telegram"] or "-")))


if __name__ == "__main__":
    main()
