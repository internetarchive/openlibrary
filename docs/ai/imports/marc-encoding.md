# MARC Binary Encoding and Unicode Pipeline

How Open Library converts raw MARC binary records into Unicode strings. Understanding this pipeline is essential for diagnosing duplicate author records, garbled diacritics, and encoding-related import failures.

Covered here: `catalog/marc/marc_binary.py`, `catalog/marc/mnemonics.py`, and how they relate to `pymarc.MARC8ToUnicode`.

## The Two MARC Character Encodings

A MARC binary record signals its character encoding via byte 9 of the leader (the 24-byte header). Open Library reads this in `MarcBinary.marc8()`:

```python
def marc8(self) -> bool:
    return self.leader()[9] == " "  # space = MARC8; "a" = UTF-8
```

- **MARC8** (leader byte 9 = space) — the legacy 8-bit encoding used by most pre-2000 catalog records. Diacritics are encoded as two-byte sequences: combining modifier BEFORE base character (opposite of Unicode's combining-after convention).
- **UTF-8** (leader byte 9 = "a") — modern records. Bytes are UTF-8 encoded strings.

## The Complete Encoding Pipeline

### UTF-8 path (clean, consistent)

```
Binary field bytes
  ↓ data.decode("utf-8")
  ↓ unicodedata.normalize("NFC", ...)    ← NFC applied here
  → Precomposed NFC Unicode string
```

Result: `"é"` stored as U+00E9 (single precomposed character).

### MARC8 path (three-stage, missing NFC)

```
Binary field bytes
  ↓ mnemonics.read(data)                 ← Stage 1: expand mnemonic escapes
  ↓ marc8.translate(data)                ← Stage 2: MARC8 bytes → Unicode
  → NFD Unicode string                   ← BUG: no NFC normalization applied
```

Result: `"é"` stored as `"é"` (two characters: base e + combining acute accent).

## Stage 1: mnemonics.py

`catalog/marc/mnemonics.py` handles MARC's mnemonic escape sequences — printed representations like `{eacute}` for é that appear in some records.

```python
re_brace = re.compile(b"(\\{.+?\\})")

def read(input: bytes) -> bytes:
    return re_brace.sub(lambda x: mapping.get(x.group(1), x.group(1)), input)
```

Key: the output of `mnemonics.read()` is still **MARC8 bytes**, not Unicode. The module comment says explicitly: "result is in MARC8 and still needs to be converted to Unicode". Examples from the mapping dict:

| Mnemonic | MARC8 bytes | What it represents |
|----------|------------|-------------------|
| `{eacute}` | `b"\xe2e"` | MARC8 combining acute (`\xe2`) + base letter `e` |
| `{Auml}` | `b"\xe8A"` | MARC8 combining diaeresis (`\xe8`) + base `A` |
| `{acute}` | `b"\xe2"` | Standalone acute accent combining mark |
| `{llig}` | `b"\xeb"` | Left ligature combining mark |

Unknown mnemonics (not in the mapping) pass through unchanged as literal `{text}` bytes.

## Stage 2: pymarc MARC8ToUnicode

`marc8.translate()` is `pymarc.MARC8ToUnicode`. It converts MARC8 bytes to Unicode:

- **MARC8**: combining modifier BEFORE base char — `\xe2` + `e` → (acute, e)
- **Unicode NFD**: combining modifier AFTER base char — `e` + U+0301 → (e, combining acute)
- **Unicode NFC**: precomposed character — `é` → U+00E9 (single codepoint)

**Empirically (pymarc 5.3.1):** `MARC8ToUnicode` outputs **NFC form** for standard combining character cases — `\xe2e` (combining acute + e) → `U+00E9 é` (precomposed). Tested across common Latin diacritics (é, ü, ñ, ç, etc.). The library internally converts MARC8’s combining-before-base convention and emits precomposed characters where possible.

## The Defensive Fix: Explicit NFC for Both Branches

`BinaryDataField.translate()` in `marc_binary.py` before PR #13017:

```python
def translate(self, data: bytes) -> str:
    """NFC normalized unicode str"""
    if self.rec.marc8():
        data = mnemonics.read(data)
        return marc8.translate(data)          # ← no explicit NFC
    return normalize("NFC", data.decode("utf8"))  # ← NFC here
```

The MARC8 branch lacked an explicit `normalize("NFC", ...)` call, even though the docstring promised NFC output. In practice pymarc 5.3.1 produces NFC, so this was not causing observed failures. PR #13017 adds the explicit call to:

1. **Make both branches symmetric** — the docstring contract is now enforced, not just coincidentally true
2. **Guard against future pymarc changes** — a pymarc version that emits NFD would silently break the contract; the explicit call prevents that
3. **Remove the asymmetry** — the two branches look inconsistent to readers; both now explicitly normalize

**One-line fix** (in `catalog/marc/marc_binary.py`):
```python
# Before:
return marc8.translate(data)
# After:
return normalize("NFC", marc8.translate(data))
```

## Impact Assessment

Because pymarc 5.3.1 already outputs NFC, there is **no observed impact** on author deduplication or stored values from this specific issue. The fix is defensive.

`match.py::normalize()` also applies NFC at comparison time as a belt-and-suspenders measure:
```python
def normalize(s: str) -> str:
    s = unicodedata.normalize("NFC", s)
    ...
```

If a future pymarc version were to output NFD, that would cause author deduplication failures:
- `"Müller"` (NFC, U+00FC) from a modern UTF-8 record ≠ `"Müller"` (NFD) from a MARC8 record
- Same person, different stored documents

The fix in PR #13017 prevents this scenario from ever occurring.

## Control Field Encoding

Control fields (tags 00x, including the critical 008 date/country field) use a different decode path:

```python
# In MarcBinary.read_fields():
yield tag, line[:-1].decode("utf-8", errors="replace")
```

The `errors="replace"` means encoding errors produce U+FFFD replacement characters rather than exceptions. `parse.py` cleans these from field 008:

```python
re_bad_char = re.compile("�")
# In read_edition():
f = re_bad_char.sub(" ", tag_008)
```

This means a corrupt 008 date (e.g., year field) is silently replaced with spaces rather than propagating an error or skipping the record. The leader itself uses the same `errors="replace"` approach — a corrupted leader byte 9 could misidentify the encoding, causing MARC8 records to be decoded as UTF-8 or vice versa.

## Leader Encoding Reliability

`MarcBinary.marc8()` trusts the cataloger's encoding declaration without validation:

```python
def marc8(self) -> bool:
    return self.leader()[9] == " "
```

Real-world MARC records from older catalogs sometimes have incorrect leader declarations — MARC8-encoded content with an "a" (UTF-8) declaration, or vice versa. When this happens, `marc8.translate()` receives UTF-8 bytes and produces garbled output, or `data.decode("utf-8")` fails on valid MARC8 bytes. There is no fallback detection or retry logic.

## MARC Field Parsing Flow

For reference, here is the full binary MARC parsing sequence in `MarcBinary`:

```
MarcBinary(bytes)
  ↓ __init__: validate total_length from bytes[0:5]
  ↓ leader(): bytes[0:24].decode("utf-8", errors="replace")
  ↓ iter_directory(): parse 12-byte entries from bytes[24:base_address]
       each entry: tag(3) + length(4) + offset(5)
  ↓ read_fields(want=None):
       control fields (tag < "010"):
         yield tag, field_bytes.decode("utf-8", errors="replace")
       data fields:
         yield tag, BinaryDataField(self, field_bytes)
  ↓ BinaryDataField.translate():
       if marc8: mnemonics.read() → marc8.translate() → NFC normalize  ← NFC (both paths)
       else: bytes.decode("utf-8") → NFC normalize                          ← NFC
```

## Related: parse.py Field Extraction

`catalog/marc/parse.py::read_edition()` consumes the output of `MarcBinary.read_fields()` and extracts OL fields:

- **Author `$0` subfields** → `remote_ids` (LCNAF key, ISNI, GND)
- **Author `$6` subfields** → `alternate_names` for CJK parallel entries
- **Field 008 bytes 15-17** → `publish_country` (3-char MARC code)
- **Field 008 bytes 7-10** → `publish_date` (4-char year)
- **Field 020** → ISBN-10 and ISBN-13 (with cleaning in `normalize_import_record`)
- **Fields 700/710** → `contribs` list (non-primary contributors)

The `lang_map` dict in `parse.py` remaps deprecated/variant MARC language codes (e.g., `"scr"` → `"hrv"` for Croatian) before storing the language on the edition.

## Debugging MARC Encoding Issues

To diagnose encoding problems in a specific MARC record:

```python
from openlibrary.catalog.marc.marc_binary import MarcBinary

with open("record.mrc", "rb") as f:
    data = f.read()

rec = MarcBinary(data)
print("MARC8 encoding:", rec.marc8())
print("Leader:", rec.leader())

for tag, field in rec.read_fields():
    if hasattr(field, "translate"):
        raw_bytes = field.data
        translated = field.translate(raw_bytes)
        # Check normalization form:
        import unicodedata
        is_nfc = translated == unicodedata.normalize("NFC", translated)
        print(f"{tag}: NFC={is_nfc} value={translated!r}")
```

To verify pymarc normalization and the fix:
```python
from unicodedata import normalize, is_normalized
from pymarc import MARC8ToUnicode

marc8 = MARC8ToUnicode(quiet=True)

# A MARC8 field containing é (combining acute + e)
marc8_bytes = b"\xe2e"  # combining acute BEFORE base e (MARC8 convention)
result = marc8.translate(marc8_bytes)
print(f"Result: {result!r}")                              # 'é' (U+00E9) — NFC
print(f"Is NFC: {is_normalized('NFC', result)}")          # True (pymarc 5.3.1)
print(f"NFC form: {normalize('NFC', result)!r}")          # same — idempotent
print(f"Same after NFC: {result == normalize('NFC', result)}")  # True
```
