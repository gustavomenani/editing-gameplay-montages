"""Align the confirmed lyrics (lyrics.txt) to the recognised words (lyrics_whisper.json) and write lines.json, which
lyrics_align.py reads instead of the hand-built LINES list. No hand-counting of recognised words.

usage: python lyrics_lines.py [lyrics.txt] [lyrics_whisper.json] [options]       (plain python: numpy is not needed)
  -o FILE        output, default lines.json
  --min-q Q      a line is reported LOW below this match quality, default 0.75 (see below)
  --keep-low     write the LOW lines to lines.json too (default: they are only reported)
  --all          keep the lines outside the video too (default: when timeline.py is importable, only the lines that sit
                 in the part of the track the video uses, T.R0..T.R1, are written; the others are listed as "outside")
  --from S --to S   use this track window (seconds) instead of the one of timeline.py
  --no-repeats   do not look for repeats of a typed line (see 3.)
lyrics.txt: one line per SUNG line, in song order, typed or pasted after the words were confirmed against a lyrics
page (reference-style.md, "Lyric words"). Case, accents and punctuation do not matter; a typo or a missing syllable is
tolerated. Blank lines, lines starting with # and section headers like [Refrão] are ignored. The file may hold the
whole song or only the part the video uses; a line the song does not reach (the recognition may stop at t_end) is reported.

How it works
1. The lyric words (accents, case and punctuation removed) are aligned to ALL recognised words (all segments, in order)
   by dynamic programming with an edit-distance similarity (a word match counts by similarity; a short word must be
   exact; a recognised word that is a cut-off start of the lyric word, "fal" for "falange", counts 0.7), plus
   1 lyric word = 2 recognised words (status "rec-split": the recogniser split it, "a través") and 2 lyric words =
   1 recognised word ("rec-merged"). A lyric word without a recognised word is a gap (cost 1.0), a recognised word that no
   lyric word claims is a gap too (0.25 between lines, 0.6 inside a line, so a word repeated in the song is taken from the
   copy that sits next to its own line); the recognised words before the first and after the last lyric word are free
   (an ad lib, "yeah yeah", a sentence the recogniser invented).
2. A lyric word takes the start time of its recognised word. A lyric word with no recognised word gets an ESTIMATED time
   from its neighbours (status "est", "~" in the table and "est" in lines.json: shared out by word length between two
   timed words, 0.30 s steps before the first / after the last; no guess across a pause of more than 1.2 s per word).
   The second of two lyric words in one recognised word gets a share of its duration (also "~").
3. Recognised stretches of 3+ words that no lyric word claimed are matched against every typed line: a chorus that
   is typed once and sung again is found as a repeat of that line ("repeat of N").
4. Line quality q = sum of the similarities of its words / number of its words (1.0 = every word found as typed).
   A line is LOW when q < --min-q, when fewer than 2 of its words were found, when two found words lie more than 3 s
   apart, or when 3 or more found words sit at the same instant (a recogniser glitch). LOW lines are listed with the
   reason and are NOT written (--keep-low writes them): fix the typed words, or the recognition, or leave the line out.
   The table's "?" marks a found word that is doubtful (similarity < 0.8 or recogniser probability < 0.35).
   After the table: every stretch of 3+ recognised words that match no typed word (a line missing from lyrics.txt, or
   noise), and a summary line.

Output lines.json: {"whisper_sha1": ..., "lines": [{"line", "text", "words": [...], "times": [...], "est": [...],
"sim": [...], "q", "repeat_of"}]}: "words" are the display words (upper case, edge punctuation removed), "times" the
seconds in the track (lyrics_align.py turns them into beats). Words that could not be timed at all are not in "words"
(listed under "untimed"). The sha1 lets lyrics_align.py refuse a lines.json made from an older lyrics_whisper.json."""
import argparse, hashlib, json, math, os, re, statistics, sys, unicodedata

GAP_L = 1.0          # a lyric word the recognition does not have
GAP_R = 0.25         # a recognised word that is not in the lyrics (ad lib, hallucination, an untyped line), between two lines
GAP_RI = 0.6         # the same inside a line: the words of a sung line follow each other, so a stray word costs more (this is
                     # also what puts a repeated word such as "eu" on the copy that sits next to its line, not an earlier one)
JOIN = 0.4           # extra cost of a split / merge (1 lyric word = 2 recognised or 2 = 1)
SPREAD = 3.0         # seconds: two consecutive found words of a line further apart than this -> LOW
NEG = -1e18


def norm(w):
    s = unicodedata.normalize("NFKD", w.lower())
    return "".join(c for c in s if c.isalnum() and not unicodedata.combining(c))


def show(w):
    return re.sub(r"^[^\w*]+|[^\w*]+$", "", w).upper()


def read_text(path):
    raw = open(path, "rb").read()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252")


def lev(a, b):
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


_sim = {}


def sim(a, b):
    """Similarity 0..1 of two normalised words, 0 below the acceptance floor (short words must be exact)."""
    k = (a, b)
    if k not in _sim:
        m = max(len(a), len(b))
        s = 1 - lev(a, b) / m if m else 0.0
        if a.startswith(b) and len(b) >= 3 and len(b) >= 0.4 * len(a):   # the recogniser cut the word short ("fal" for "falange")
            s = max(s, 0.7)
        floor = 0.99 if m <= 3 else 0.6 if m <= 5 else 0.55
        _sim[k] = s if s >= floor else 0.0
    return _sim[k]


def gain(a, b, s=None):
    """Score of matching two words: more for long words and for a close match, never below 0.3 when accepted."""
    s = sim(a, b) if s is None else s
    if s <= 0:
        return None
    full = 2.0 + 0.2 * min(len(a), 8)
    return full * max((s - 0.4) / 0.6, 0.15)


def align(L, R, line_of):
    """Align lyric words L to recognised words R (lists of normalised strings; line_of[i] = line number of lyric word i).
    Free: recognised words before the first and after the last lyric word. Returns (score, match) with
    match[i] = (rec positions, similarity[, 1 or 2 for a word that shares a recognised word]) or None."""
    N, M = len(L), len(R)
    H = [[NEG] * (M + 1) for _ in range(N + 1)]
    P = [[None] * (M + 1) for _ in range(N + 1)]
    for j in range(M + 1):
        H[0][j] = 0.0
    for i in range(1, N + 1):
        H[i][0] = H[i - 1][0] - GAP_L
        P[i][0] = "L"
        li = L[i - 1]
        for j in range(1, M + 1):
            best, ptr = H[i - 1][j] - GAP_L, "L"
            v = H[i][j - 1] - (GAP_RI if 0 < i < N and line_of[i - 1] == line_of[i] else GAP_R)
            if v > best:
                best, ptr = v, "R"
            g = gain(li, R[j - 1])
            if g is not None and H[i - 1][j - 1] + g > best:
                best, ptr = H[i - 1][j - 1] + g, "M"
            if j >= 2:                                         # the recogniser split the word in two
                cat = R[j - 2] + R[j - 1]
                g = gain(li, cat) if sim(li, cat) >= 0.8 else None
                if g is not None and H[i - 1][j - 2] + g - JOIN > best:
                    best, ptr = H[i - 1][j - 2] + g - JOIN, "S"
            if i >= 2:                                         # the recogniser merged two words
                cat = L[i - 2] + li
                g = gain(cat, R[j - 1]) if sim(cat, R[j - 1]) >= 0.8 else None
                if g is not None and H[i - 2][j - 1] + g - JOIN > best:
                    best, ptr = H[i - 2][j - 1] + g - JOIN, "P"
            H[i][j], P[i][j] = best, ptr
    j = max(range(M + 1), key=lambda q: H[N][q])
    score, i = H[N][j], N
    match = [None] * N
    while i > 0:
        p = P[i][j]
        if p == "L":
            i -= 1
        elif p == "R":
            j -= 1
        elif p == "M":
            match[i - 1] = ([j - 1], sim(L[i - 1], R[j - 1]))
            i, j = i - 1, j - 1
        elif p == "S":
            match[i - 1] = ([j - 2, j - 1], sim(L[i - 1], R[j - 2] + R[j - 1]))
            i, j = i - 1, j - 2
        else:                                                  # "P": lyric words i-1 and i share recognised word j
            s_ = sim(L[i - 2] + L[i - 1], R[j - 1])
            match[i - 1] = ([j - 1], s_, 2)
            match[i - 2] = ([j - 1], s_, 1)
            i, j = i - 2, j - 1
    return score, match


def load_lyrics(path):
    lines = []
    for raw in read_text(path).splitlines():
        t = raw.strip()
        if not t or t.startswith("#") or re.fullmatch(r"\[[^\]]*\]", t):
            continue
        toks = [(show(w), norm(w)) for w in t.split()]
        toks = [(d, n) for d, n in toks if n and d]
        if toks:
            lines.append({"text": t, "disp": [d for d, _ in toks], "norm": [n for _, n in toks]})
    return lines


def estimate(times, lens):
    """Fill, inside one line, the times of the lyric words that have no recognised word (times[k] is None there; lens[k]
    the length of the word). Between two timed words: shared out by word length, unless the gap is a pause (more than
    1.2 s per word): then no guess. Before the first timed word: 0.30 s steps ending at it; after the last: 0.30 s steps
    from it. Mutates times; returns the set of estimated indices."""
    est = set()
    n = len(times)
    k = 0
    while k < n:
        if times[k] is not None:
            k += 1
            continue
        a = k
        while k < n and times[k] is None:
            k += 1
        b = k                                                  # missing run a..b-1
        c = b - a
        tp = times[a - 1] if a > 0 else None
        tn = times[b] if b < n else None
        if tp is not None and tn is not None:
            if tn - tp > 1.2 * (c + 1):
                continue
            w = [lens[q] + 1 for q in range(a - 1, b)]
            tot = float(sum(w))
            out = [tp + (tn - tp) * sum(w[:m + 1]) / tot for m in range(c)]
        elif tn is not None:
            out = [tn - 0.30 * (c - m) for m in range(c)]
        elif tp is not None:
            out = [tp + 0.30 * (m + 1) for m in range(c)]
        else:
            continue
        for m in range(c):
            times[a + m] = round(out[m], 3)
            est.add(a + m)
    return est


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")             # a lyric character the console cannot show must not stop the run
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("lyrics", nargs="?", default="lyrics.txt")
    ap.add_argument("whisper", nargs="?", default="lyrics_whisper.json")
    ap.add_argument("-o", "--out", default="lines.json")
    ap.add_argument("--min-q", type=float, default=0.75)
    ap.add_argument("--keep-low", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--from", dest="t_from", type=float)
    ap.add_argument("--to", dest="t_to", type=float)
    ap.add_argument("--no-repeats", action="store_true")
    a = ap.parse_args()
    for f, what in ((a.lyrics, "the lyrics file (one line per sung line)"), (a.whisper, "the recognition: run transcribe.py first")):
        if not os.path.exists(f):
            sys.exit("lyrics_lines.py: %s is missing (%s; reference-style.md, \"Lyric words\")." % (f, what))
    raw_w = open(a.whisper, "rb").read()
    rec = []
    for s in json.loads(raw_w.decode("utf-8")):
        for w in s["words"]:
            n = norm(w["w"])
            if n:
                rec.append({"w": w["w"].strip(), "n": n, "s": w["s"], "e": w["e"], "p": w.get("p", 1.0)})
    lines = load_lyrics(a.lyrics)
    if not lines:
        sys.exit("lyrics_lines.py: %s holds no words." % a.lyrics)
    if not rec:
        sys.exit("lyrics_lines.py: %s holds no recognised words." % a.whisper)

    # timeline (optional): beats for the table and the part of the track the video uses
    beat, window = None, None
    sys.path.insert(0, os.getcwd())
    try:
        import timeline as T
        beat = lambda t: (t - T.BEAT0) / T.PER - T.M0
        window = (T.beat_time(T.R0) - 1.0, T.beat_time(T.R1) + 0.5)
    except Exception as e:                                     # no timeline.py here, or it needs another venv
        print("note: timeline.py not usable (%s: %s): no beat column, no video window." % (type(e).__name__, e))
    if a.t_from is not None or a.t_to is not None:
        window = (a.t_from if a.t_from is not None else -1e9, a.t_to if a.t_to is not None else 1e9)

    # 1. alignment of all lyric words to all recognised words
    flat = [(li, k) for li, ln in enumerate(lines) for k in range(len(ln["norm"]))]
    Ln = [lines[li]["norm"][k] for li, k in flat]
    score, match = align(Ln, [r["n"] for r in rec], [li for li, k in flat])
    used = set(q for m in match if m for q in m[0])

    # 3. repeats: unclaimed recognised stretches that are another sung copy of a typed line
    occ = [(li, [(k, match[g]) for g, (l2, k) in enumerate(flat) if l2 == li], None) for li in range(len(lines))]
    if not a.no_repeats:
        uniq = {}
        for li, ln in enumerate(lines):
            if len(ln["norm"]) >= 2:
                uniq.setdefault(" ".join(ln["norm"]), li)
        for _ in range(300):
            runs, cur = [], []
            for q in range(len(rec)):
                if q in used:
                    if cur:
                        runs.append(cur)
                    cur = []
                else:
                    cur.append(q)
            if cur:
                runs.append(cur)
            best = None
            for run in runs:
                if len(run) < 3:
                    continue
                for li in uniq.values():
                    L2 = lines[li]["norm"]
                    sc, m2 = align(L2, [rec[q]["n"] for q in run], [0] * len(L2))
                    found = [m for m in m2 if m]
                    qual = sum(m[1] for m in found) / len(L2)
                    if len(found) >= max(2, math.ceil(0.6 * len(L2))) and qual >= a.min_q and (best is None or (qual, sc) > best[:2]):
                        best = (qual, sc, li, [(k, ([run[q] for q in m[0]],) + tuple(m[1:]) if m else None) for k, m in enumerate(m2)])
            if best is None:
                break
            occ.append((best[2], best[3], best[2]))
            for _, m in best[3]:
                if m:
                    used.update(m[0])

    # per occurrence: times, kinds, quality
    entries = []
    for oi, (li, ms, rep) in enumerate(occ):
        ln = lines[li]
        entries.append({"line": li + 1, "repeat_of": (rep + 1) if rep is not None else None, "text": ln["text"],
                        "disp": ln["disp"], "norm": ln["norm"], "m": [m for _, m in ms]})
    # global time list (in output order of the lyrics file for the main matches, repeats on their own)
    for e in entries:
        n = len(e["disp"])
        e["t"], e["kind"], e["sim"], e["p"], e["rec"] = [None] * n, [None] * n, [0.0] * n, [None] * n, [None] * n
        for k, m in enumerate(e["m"]):
            if not m:
                continue
            qs = m[0]
            r0 = rec[qs[0]]
            if len(m) == 3:                                    # lyric words share one recognised word
                dur = max(r0["e"] - r0["s"], 0.0)
                two = e["norm"][k - 1 if m[2] == 2 else k + 1]
                mine = e["norm"][k]
                first, second = (mine, two) if m[2] == 1 else (two, mine)
                frac = len(first) / (len(first) + len(second))
                e["t"][k] = r0["s"] if m[2] == 1 else r0["s"] + dur * frac
                e["kind"][k] = "rec-merged"                  # the recogniser merged two lyric words into one
            elif len(qs) == 2:
                e["t"][k], e["kind"][k] = r0["s"], "rec-split"   # the recogniser split one lyric word in two
            else:
                e["t"][k], e["kind"][k] = r0["s"], "ok" if m[1] >= 0.995 else "fuzzy"
            e["sim"][k], e["p"][k], e["rec"][k] = m[1], min(rec[q]["p"] for q in qs), " ".join(rec[q]["w"] for q in qs)
    # estimate the words with no recognised word, entry by entry
    for e in entries:
        times = list(e["t"])
        est = estimate(times, [len(w) for w in e["norm"]])
        e["t"] = times
        e["est"] = [k in est or e["kind"][k] == "rec-merged" and e["m"][k][2] == 2 for k in range(len(times))]
        for k in est:
            e["kind"][k] = "est"
    for e in entries:
        n = len(e["disp"])
        found = [k for k in range(n) if e["kind"][k] in ("ok", "fuzzy", "rec-split", "rec-merged")]
        e["q"] = sum(e["sim"]) / n
        reasons = []
        if n >= 2 and len(found) < 2:
            reasons.append("only %d of %d words found" % (len(found), n))
        elif not found:
            reasons.append("not found in the recognition")
        if e["q"] < a.min_q:
            reasons.append("q %.2f < %.2f" % (e["q"], a.min_q))
        ft = [e["t"][k] for k in found if e["kind"][k] != "rec-merged"]
        if any(y - x > SPREAD for x, y in zip(ft, ft[1:])):
            reasons.append("found words further than %.0f s apart" % SPREAD)
        if sum(y - x < 0.03 for x, y in zip(ft, ft[1:])) >= 2:
            reasons.append("several words at the same instant (recogniser glitch)")
        e["low"] = reasons
        tt = [t for t in e["t"] if t is not None]
        e["t_mid"] = statistics.median(tt) if tt else None
        e["outside"] = bool(window and tt and not any(window[0] <= t <= window[1] for t in tt)) and not a.all
    entries.sort(key=lambda e: (e["t_mid"] is None, e["t_mid"] or 0, e["line"]))

    # table: ~ = estimated time (no recognised word), ? = doubtful word (similarity < 0.8 or probability < 0.35)
    print("   %-13s %-15s %7s %7s %5s %5s  status" % ("lyric word", "recognised", "time s", "beat" if beat else "", "sim", "p"))
    for e in entries:
        tag = "OUTSIDE the video" if e["outside"] else ("LOW: " + "; ".join(e["low"]) if e["low"] else "ok")
        print("-- line %d%s  q=%.2f  %s  | %s" % (e["line"], " (repeat of %d)" % e["repeat_of"] if e["repeat_of"] else "", e["q"], tag,
                                                  e["text"][:70]))
        if e["outside"]:
            continue
        if all(t is None for t in e["t"]):
            print("   (none of its %d words was found in the recognition)" % len(e["disp"]))
            continue
        for k, d in enumerate(e["disp"]):
            t, kind = e["t"][k], e["kind"][k]
            bad = (kind in ("fuzzy", "rec-split", "rec-merged") and e["sim"][k] < 0.8) or (e["p"][k] is not None and e["p"][k] < 0.35)
            mark = "~" if e["est"][k] else ("?" if bad else " ")
            print(" %s %-13s %-15s %7s %7s %5s %5s  %s" % (
                mark, d[:13], (e["rec"][k] or "-")[:15], "%.2f" % t if t is not None else "-",
                ("%.2f" % beat(t) if t is not None else "") if beat else "",
                "%.2f" % e["sim"][k] if e["sim"][k] else "-", "%.2f" % e["p"][k] if e["p"][k] is not None else "-",
                kind or "MISSING (nothing to time it from)"))
    # recognised words nobody claimed (inside the window): a missing typed line shows up here
    claimed = set(q for e in entries for m in e["m"] if m for q in m[0])
    runs, cur = [], []
    for q in range(len(rec)):
        if q in claimed:
            cur and runs.append(cur)
            cur = []
        else:
            cur.append(q)
    cur and runs.append(cur)
    runs = [r for r in runs if len(r) >= 3 and (not window or window[0] <= rec[r[0]]["s"] <= window[1])]
    if runs:
        print("\nrecognised words that match no typed word (3+ in a row): a line missing from %s, or recogniser noise:" % a.lyrics)
        for r in runs:
            print("  %6.2f-%6.2f  %s" % (rec[r[0]]["s"], rec[r[-1]]["e"], " ".join(rec[q]["w"] for q in r)))

    keep = [e for e in entries if not e["outside"] and (not e["low"] or a.keep_low) and any(t is not None for t in e["t"])]
    low = [e for e in entries if not e["outside"] and e["low"]]
    est_n = sum(sum(e["est"]) for e in keep)
    print("\n%d lines written to %s; %d LOW%s; %d outside the video; %d estimated word(s) (~)" % (
        len(keep), a.out, len(low),
        "" if not low else " (%s: %s)" % ("written, --keep-low" if a.keep_low else "NOT written",
                                          ", ".join("line %d" % e["line"] for e in low)),
        sum(e["outside"] for e in entries), est_n))
    if not keep:
        sys.exit("lyrics_lines.py: no usable line: %s not written. Check that lyrics.txt is the song of lyrics_whisper.json and "
                 "that the lines are inside the recognised part." % a.out)
    out = {"whisper_sha1": hashlib.sha1(raw_w).hexdigest(), "lines": []}
    for e in keep:
        ok = [k for k in range(len(e["disp"])) if e["t"][k] is not None]
        out["lines"].append({"line": e["line"], "repeat_of": e["repeat_of"], "text": e["text"], "q": round(e["q"], 3),
                             "low": e["low"], "words": [e["disp"][k] for k in ok], "times": [round(e["t"][k], 3) for k in ok],
                             "est": [e["est"][k] for k in ok], "sim": [round(e["sim"][k], 3) for k in ok],
                             "untimed": [e["disp"][k] for k in range(len(e["disp"])) if e["t"][k] is None]})
    json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
