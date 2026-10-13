"""lyrics.txt -> the words of the section, in sung order (imported by lyrics_sync.py, lyrics_ctc_align.py and
cues_from_alignment.py; stdlib only, so it also runs in the separation venv).

lyrics.txt = the CONFIRMED words of the part of the song the edit uses, one line per sung line, in song order, every word
that is sung inside the section (also the ones that stay off screen). Blank lines, lines starting with `#` and
`[Chorus]`-style headers are ignored. A token is one word:
  word             sung as typed (accents and case are dropped for the aligner), shown on screen in capitals
  sung=SHOWN       the sung form differs from the text on screen:  takin=TAKING  (an aligner reads letters, not spelling)
  sung=-           aligned but not shown (a word sung over a kill that must stay clear, an ad-lib)
  word@12.34       pin: the word is sung at timeline beat 12.34 (a word the alignment got wrong; the sync sheet shows which)
Punctuation around a word is not shown (a trailing , . ; : and quotes / brackets) except ? and !. Numbers and symbols are
written as sung ("two", "and" for &). A token with no letter or digit at all (a lone dash) is skipped."""
import re
import unicodedata

_EDGE = ",.;:…\"“”‘()[]{}"                 # stripped around the SHOWN text (a ? or ! stays)


def sung_form(token):
    """The form given to the aligner: lowercase letters a-z and inner apostrophes; accents dropped (ç -> c)."""
    t = unicodedata.normalize("NFKD", token.replace("’", "'").replace("`", "'").lower())
    t = "".join(c for c in t if (c.isalnum() or c == "'") and not unicodedata.combining(c))
    return t.strip("'")


def parse(path):
    """-> [{"sung", "shown" (None = not shown), "pin" (beat or None), "line" (1-based line number), "raw"}, ...]"""
    words = []
    for no, raw_line in enumerate(open(path, encoding="utf-8-sig").read().splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith(("#", "[")):
            continue
        for tok in line.split():
            raw, pin = tok, None
            m = re.search(r"@(-?\d+(?:\.\d+)?)$", tok)
            if m:
                pin, tok = float(m.group(1)), tok[:m.start()]
            if "=" in tok:
                sung_t, shown_t = tok.split("=", 1)
            else:
                sung_t, shown_t = tok, None
            if not any(c.isalnum() for c in sung_t) and not shown_t:
                continue                                  # a lone dash, an ellipsis
            sung = sung_form(sung_t)
            if not sung:
                raise SystemExit("%s line %d: '%s' has no letter to align." % (path, no, raw))
            if shown_t is None:
                shown = sung_t.upper().strip(_EDGE) or sung.upper()
            elif shown_t == "-":
                shown = None
            else:
                shown = shown_t.upper().strip(_EDGE)
            if shown is not None and not shown:
                raise SystemExit("%s line %d: '%s' shows nothing." % (path, no, raw))
            words.append({"sung": sung, "shown": shown, "pin": pin, "line": no, "raw": raw})
    if not words:
        raise SystemExit("%s holds no words (one line per sung line of the section; see lyrics_words.py)." % path)
    return words
