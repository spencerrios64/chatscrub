#!/usr/bin/env python3
"""chatscrub - remove API keys, emails, phone numbers and other private details from AI chats.

usage:
  python chatscrub.py files OUT.zip INPUT [INPUT ...] [--words "name, address"] [--ips] [--skip phones,emails]
  python chatscrub.py text [FILE] [--words "name, address"] [--ips] [--skip phones,emails]

INPUT is an AI export (.zip or .json), which keeps its format, or any text file.
'text' reads FILE (or standard input) and prints the scrubbed text. Standard library only.
It works by pattern, so it cannot know that a word is a name or a secret: use --words for those.
"""
import argparse
import html
import json
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

def iso(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v / 1000 if v > 1e11 else v, tz=timezone.utc).isoformat()
    if isinstance(v, dict):
        d = v.get("$date")
        n = d.get("$numberLong") if isinstance(d, dict) else d
        if n is None:
            return None
        try:
            return iso(float(n))
        except (TypeError, ValueError):
            return str(n)
    return str(v)


def strip_html(s):
    s = re.sub(r"(?i)<br\s*/?>|</(p|li|h\d|div|tr|pre)>", "\n", s)
    s = html.unescape(re.sub(r"<[^>]*>", "", s))
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def parse_mapping(data):
    """ChatGPT and DeepSeek both export a 'mapping' tree of messages."""
    deepseek, convs = False, []
    for c in data:
        mp = c.get("mapping") or {}
        chain, node = [], c.get("current_node")
        if node:
            while node and mp.get(node):
                chain.append(mp[node])
                node = mp[node].get("parent")
            chain.reverse()
        else:
            node = "root" if "root" in mp else next((k for k, v in mp.items() if not v.get("parent")), None)
            seen = set()
            while node and mp.get(node) and node not in seen:
                seen.add(node)
                chain.append(mp[node])
                kids = mp[node].get("children") or []
                node = kids[-1] if kids else None
        msgs = []
        for e in chain:
            m = e.get("message")
            if not m:
                continue
            if isinstance(m.get("fragments"), list):
                deepseek = True
                for f in m["fragments"]:
                    role = {"REQUEST": "user", "RESPONSE": "assistant"}.get(f.get("type"))
                    text = str(f.get("content") or "").strip()
                    if role and text:
                        msgs.append((role, text))
                continue
            role = (m.get("author") or {}).get("role")
            if role not in ("user", "assistant"):
                continue
            parts = (m.get("content") or {}).get("parts") or []
            text = "\n".join(p for p in parts if isinstance(p, str)).strip()
            if text:
                msgs.append((role, text))
        date = c.get("create_time") or c.get("inserted_at") or c.get("update_time") or c.get("updated_at")
        convs.append({"title": c.get("title"), "date": iso(date), "messages": msgs})
    return [("DeepSeek" if deepseek else "ChatGPT", convs)]


def parse_claude(data):
    convs = []
    for c in data:
        msgs = []
        for m in c.get("chat_messages", []):
            text = (m.get("text") or "").strip()
            if not text:
                text = "\n".join(b.get("text", "") for b in m.get("content", []) if b.get("type") == "text").strip()
            if text:
                msgs.append(("user" if m.get("sender") == "human" else "assistant", text))
        convs.append({"title": c.get("name"), "date": iso(c.get("created_at")), "messages": msgs})
    return [("Claude", convs)]


def parse_grok(data):
    convs = []
    for c in data["conversations"]:
        info, msgs = c.get("conversation") or {}, []
        for r in c.get("responses") or []:
            m = r.get("response") or r
            text = str(m.get("message") or "").strip()
            if text:
                who = str(m.get("sender") or "").lower()
                msgs.append(("user" if who in ("human", "user") else "assistant", text))
        convs.append({"title": info.get("title"), "date": iso(info.get("create_time") or info.get("created_at")), "messages": msgs})
    return [("Grok", convs)]


def parse_gemini(data):
    """Takeout 'My Activity' has one entry per prompt and no chat ids: group by day."""
    days = {}
    for it in data:
        if not re.search("gemini", it.get("header") or "", re.I) or not it.get("title"):
            continue
        t = str(it.get("time") or "")
        turn = [("user", re.sub(r"^Prompted\s+", "", str(it["title"])).strip())]
        reply = "\n".join(strip_html(h.get("html") or "") for h in it.get("safeHtmlItem") or []).strip()
        if reply:
            turn.append(("assistant", reply))
        days.setdefault(t[:10] or "undated", []).append((t, turn))
    convs = [{"title": "Gemini prompts", "date": None if day == "undated" else day,
              "messages": [m for _, turn in sorted(turns, key=lambda x: x[0]) for m in turn]}
             for day, turns in days.items()]
    return [("Gemini", convs)] if convs else []


def parse_archive(data):
    names, by = {"claude": "Claude", "chatgpt": "ChatGPT"}, {}
    for c in data:
        src = str(c.get("source") or "other")
        by.setdefault(names.get(src, src[:1].upper() + src[1:]), []).append({
            "title": c.get("title"), "date": iso(c.get("created_at") or c.get("updated_at")),
            "messages": [(m["role"], m["text"]) for m in c.get("messages", []) if (m.get("text") or "").strip()]})
    return list(by.items())


def detect(doc):
    """Return [(ai_name, conversations)] for one parsed JSON document, or [] if it isn't a chat export."""
    if isinstance(doc, list) and doc and isinstance(doc[0], dict):
        f = doc[0]
        if "mapping" in f:
            return parse_mapping(doc)
        if "chat_messages" in f:
            return parse_claude(doc)
        if "header" in f and "title" in f and "time" in f:
            return parse_gemini(doc)
        if "messages" in f and "source" in f:
            return parse_archive(doc)
    if isinstance(doc, dict) and isinstance(doc.get("conversations"), list) \
            and any(isinstance(c, dict) and c.get("responses") for c in doc["conversations"]):
        return parse_grok(doc)
    return []


def read_export(path):
    """Return [(file name, parsed JSON)] for the chat files inside an export (.zip or .json)."""
    path = Path(path)
    if zipfile.is_zipfile(path):
        out = []
        with zipfile.ZipFile(path) as z:
            for n in z.namelist():
                m = re.search(r"(^|/)(conversations[^/]*|prod-grok-backend|MyActivity)\.json$", n, re.I)
                if not m or (m.group(2).lower() == "myactivity" and not re.search("gemini", n, re.I)):
                    continue
                out.append((n, json.loads(z.read(n))))
        return out
    return [(path.name, json.loads(path.read_text(encoding="utf-8")))]


def load_chats(paths):
    """Return (chats, problems). A chat is {ai, title, date, messages: [{role, text}]}."""
    chats, problems = [], []
    for p in paths:
        try:
            found = [g for _, doc in read_export(p) for g in detect(doc)]
        except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as e:
            problems.append(f"{p}: could not read ({e})")
            continue
        if not found:
            problems.append(f"{p}: no chats recognised")
            continue
        for ai, convs in found:
            for c in convs:
                if c["messages"]:
                    chats.append({"ai": ai, "title": str(c["title"] or "Untitled"), "date": (c["date"] or "")[:10],
                                  "messages": [{"role": r, "text": t} for r, t in c["messages"]]})
    return chats, problems


def luhn(s):
    total, alt = 0, False
    for ch in reversed(s):
        d = int(ch)
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


def digits(s):
    return re.sub(r"\D", "", s)


def phone_ok(m):
    n = len(digits(m))
    return (9 <= n <= 15 and not re.search(r"^\d{4}[-./]\d{1,2}[-./]\d{1,2}|^\d{1,2}[-./]\d{1,2}[-./]\d{4}|\n", m)
            and not re.search(r"^\d+\.\d+$|^\d{1,3}(?:\.\d{1,3}){3}$", m))


A = re.ASCII
# Order matters: the most specific patterns run first. ok() can veto a match.
PATTERNS = [
    {"id": "keys", "label": "API keys, tokens and private keys", "on": True, "tag": "[KEY REMOVED]",
     "re": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----|\b(?:sk-ant-[\w-]{20,}|sk-(?:proj-|or-v1-)?[\w-]{20,}|AIza[\w-]{30,}|gh[pousr]_\w{30,}|github_pat_\w{30,}|gsk_\w{30,}|hf_\w{30,}|xox[abprs]-[\w-]{10,}|A[KS]IA[0-9A-Z]{16}|eyJ[\w-]{10,}\.[\w-]{10,}\.[\w-]{10,})|\bBearer\s+[\w.~+/-]{20,}=*", A)},
    {"id": "logins", "label": "Passwords inside links (https://user:pass@...)", "on": True, "tag": "[LOGIN REMOVED]",
     "re": re.compile(r"(?P<pre>\b[a-z][\w+.-]*://)[^\s/:@]+:[^\s/@]+(?=@)", A | re.I)},
    {"id": "emails", "label": "Email addresses", "on": True, "tag": "[EMAIL REMOVED]",
     "re": re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", A)},
    {"id": "cards", "label": "Card numbers", "on": True, "tag": "[CARD REMOVED]",
     "re": re.compile(r"(?<![\w.-])\d(?:[ -]?\d){12,18}(?![\w-])", A), "ok": lambda m: luhn(digits(m))},
    {"id": "ips", "label": "IP addresses (can also hit version numbers like 1.2.3.4)", "on": False, "tag": "[IP REMOVED]",
     "re": re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b", A)},
    {"id": "phones", "label": "Phone numbers", "on": True, "tag": "[PHONE REMOVED]",
     "re": re.compile(r"(?<![\w.,:/-])\+?\(?\d[\d\s().-]{7,17}\d(?![\w/-])", A), "ok": phone_ok},
]
LABEL = {p["id"]: p["label"] for p in PATTERNS}
LABEL["words"] = "Your own words"

# Fields that hold ids and timestamps: changing them would break the export.
KEEP = re.compile(r"(id|uuid|.*_id|.*_uuid|parent|children|current_node|.*_at|.*_time|time|sender|role|type|status|model.*|content_type|recipient)", re.I)


def parse_words(s):
    return sorted({w.strip() for w in re.split(r"[\n,]+", s or "") if len(w.strip()) >= 2}, key=len, reverse=True)


def scrub(text, on, words, counts):
    """on: {pattern id: bool}. words: extra strings to remove. counts is updated in place."""
    for p in PATTERNS:
        if not on.get(p["id"]):
            continue

        def sub(m, p=p):
            if p.get("ok") and not p["ok"](m.group(0)):
                return m.group(0)
            counts[p["id"]] = counts.get(p["id"], 0) + 1
            return (m.groupdict().get("pre") or "") + p["tag"]

        text = p["re"].sub(sub, text)
    if words:
        def sub_word(m):
            counts["words"] = counts.get("words", 0) + 1
            return "[REMOVED]"

        text = re.sub("|".join(re.escape(w) for w in words), sub_word, text, flags=re.I)
    return text


def scrub_doc(v, on, words, counts, key=None):
    """Scrubs every text value inside an export document and leaves its structure alone."""
    keep = key is not None and KEEP.fullmatch(key)
    if isinstance(v, str):
        return v if keep else scrub(v, on, words, counts)
    if isinstance(v, list):
        return v if keep else [scrub_doc(x, on, words, counts, key) for x in v]
    if isinstance(v, dict):
        return {k: scrub_doc(x, on, words, counts, k) for k, x in v.items()}
    return v


def describe(counts):
    return ", ".join(f"{LABEL[k]}: {n}" for k, n in counts.items()) or "nothing found"


def settings(a):
    on = {p["id"]: p["on"] for p in PATTERNS}
    if a.ips:
        on["ips"] = True
    for k in (a.skip or "").split(","):
        if k.strip():
            if k.strip() not in on:
                sys.exit(f"--skip: unknown kind '{k.strip()}' (choose from {', '.join(on)})")
            on[k.strip()] = False
    return on, parse_words(a.words)


def unique(name, used):
    p, n, out = Path(name), 2, name
    while out.lower() in used:
        out = f"{p.stem} ({n}){p.suffix}"
        n += 1
    used.add(out.lower())
    return out


def run_files(a):
    on, words = settings(a)
    counts, used, files, failed = {}, set(), [], False
    for src in a.inputs:
        try:
            if re.search(r"\.(zip|json)$", src, re.I):
                for name, doc in read_export(src):
                    out = "scrubbed/" + unique(Path(name).name, used)
                    files.append((out, json.dumps(scrub_doc(doc, on, words, counts), ensure_ascii=False, separators=(",", ":"))))
            else:
                out = "scrubbed/" + unique(Path(src).name, used)
                files.append((out, scrub(Path(src).read_text(encoding="utf-8", errors="replace"), on, words, counts)))
        except (OSError, ValueError, zipfile.BadZipFile) as e:
            failed = True
            print(f"{src}: could not read ({e})", file=sys.stderr)
    if not files:
        print("Nothing to write.", file=sys.stderr)
        return 1
    with zipfile.ZipFile(a.out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, text in files:
            z.writestr(name, text)
    print(f"wrote {a.out}: {len(files)} file(s). Removed: {describe(counts)}.")
    return 1 if failed else 0


def run_text(a):
    on, words = settings(a)
    counts = {}
    src = sys.stdin.read() if not a.file or a.file == "-" else Path(a.file).read_text(encoding="utf-8", errors="replace")
    sys.stdout.write(scrub(src, on, words, counts))
    print(f"\nRemoved: {describe(counts)}.", file=sys.stderr)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="mode", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--words", help="extra words to remove (names, addresses, usernames), separated by commas")
    common.add_argument("--ips", action="store_true", help="also remove IP addresses (also hits version numbers like 1.2.3.4)")
    common.add_argument("--skip", help="kinds to leave alone, separated by commas: " + ", ".join(p["id"] for p in PATTERNS))
    f = sub.add_parser("files", parents=[common], help="scrub export files into a zip")
    f.add_argument("out", help="zip file to write")
    f.add_argument("inputs", nargs="+", help="exports (.zip or .json) or text files")
    t = sub.add_parser("text", parents=[common], help="scrub a text file or standard input")
    t.add_argument("file", nargs="?", help="text file (default: standard input)")
    a = ap.parse_args(argv)
    return run_files(a) if a.mode == "files" else run_text(a)


if __name__ == "__main__":
    sys.exit(main())
