"""What goes inside the code: each type has fields and builds the text that phones understand."""

TYPES = ["Link", "Text", "Wi-Fi", "Contact", "E-mail", "Phone", "SMS", "WhatsApp", "Location"]

# (key, label, kind, default)  kind: line | multi | choice:a,b,c | secret
FIELDS = {
    "Link": [("url", "Web address", "line", "https://")],
    "Text": [("text", "Text", "multi", "")],
    "Wi-Fi": [("ssid", "Network name", "line", ""), ("pw", "Password", "line", ""),
              ("sec", "Security", "choice:WPA,WEP,none", "WPA"), ("hidden", "Hidden network", "choice:no,yes", "no")],
    "Contact": [("name", "Full name", "line", ""), ("org", "Company", "line", ""), ("title", "Job title", "line", ""),
                ("tel", "Phone", "line", ""), ("mail", "E-mail", "line", ""), ("web", "Website", "line", ""),
                ("adr", "Address", "line", "")],
    "E-mail": [("to", "To", "line", ""), ("subject", "Subject", "line", ""), ("body", "Message", "multi", "")],
    "Phone": [("tel", "Phone number", "line", "+49")],
    "SMS": [("tel", "Phone number", "line", "+49"), ("body", "Message", "multi", "")],
    "WhatsApp": [("tel", "Phone number with country code", "line", "+49"), ("body", "Message (optional)", "multi", "")],
    "Location": [("lat", "Latitude", "line", ""), ("lon", "Longitude", "line", "")],
}


def _esc_wifi(s):
    return "".join("\\" + c if c in '\\;,:"' else c for c in s)


def _esc_v(s):
    return s.replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")


def _pct(s):
    from urllib.parse import quote
    return quote(s, safe="")


def _digits(s):
    return "".join(c for c in s if c.isdigit())


def build(kind, v):
    g = lambda k: (v.get(k) or "").strip()
    if kind == "Link":
        u = g("url")
        return u if u and "://" in u or u.startswith("mailto:") else ("https://" + u if u and u != "https://" else "")
    if kind == "Text":
        return v.get("text", "")
    if kind == "Wi-Fi":
        if not g("ssid"):
            return ""
        sec = g("sec") or "WPA"
        pw = "" if sec == "none" else _esc_wifi(v.get("pw", ""))
        return f"WIFI:T:{'nopass' if sec == 'none' else sec};S:{_esc_wifi(g('ssid'))};" + (f"P:{pw};" if pw else "") + ("H:true;" if g("hidden") == "yes" else "") + ";"
    if kind == "Contact":
        if not (g("name") or g("tel") or g("mail")):
            return ""
        L = ["BEGIN:VCARD", "VERSION:3.0", f"FN:{_esc_v(g('name'))}", f"N:{_esc_v(g('name'))};;;;"]
        if g("org"): L.append(f"ORG:{_esc_v(g('org'))}")
        if g("title"): L.append(f"TITLE:{_esc_v(g('title'))}")
        if g("tel"): L.append(f"TEL:{g('tel')}")
        if g("mail"): L.append(f"EMAIL:{g('mail')}")
        if g("web"): L.append(f"URL:{g('web')}")
        if g("adr"): L.append(f"ADR:;;{_esc_v(g('adr'))};;;;")
        L.append("END:VCARD")
        return "\n".join(L)
    if kind == "E-mail":
        if not g("to"):
            return ""
        q = [f"{k}={_pct(v.get(k, ''))}" for k in ("subject", "body") if g(k)]
        return f"mailto:{g('to')}" + ("?" + "&".join(q) if q else "")
    if kind == "Phone":
        return f"tel:{g('tel')}" if _digits(g("tel")) else ""
    if kind == "SMS":
        return f"SMSTO:{g('tel')}:{v.get('body', '')}" if _digits(g("tel")) else ""
    if kind == "WhatsApp":
        d = _digits(g("tel"))
        return f"https://wa.me/{d}" + (f"?text={_pct(v.get('body', '').strip())}" if g("body") else "") if d else ""
    if kind == "Location":
        try:
            la, lo = float(g("lat").replace(",", ".")), float(g("lon").replace(",", "."))
        except ValueError:
            return ""
        return f"geo:{la},{lo}" if -90 <= la <= 90 and -180 <= lo <= 180 else ""
    return ""
