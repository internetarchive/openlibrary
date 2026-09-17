use once_cell::sync::Lazy;
use regex::Regex;

static MULTIPLE_SPACES_RE: Lazy<Regex> = Lazy::new(|| Regex::new(r"\s+").unwrap());

static DDC_RE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(
        r"(?ix)(
        (?P<prestar>\*)?
        (?P<neg>-)?
        (?P<j>j)?
        C?
        (?P<number>\d{1,3}(\.+\s?\d+)?)
        (?P<poststar>\*?)
        (?P<s>\s?s)?
        (?P<B>\s?\[?B\]?)?
        (?P<ninetwo>\s(092|920|92))?
    )
    |
    (\[?(?P<fic>Fic|E)\.?\]?)",
    )
    .unwrap()
});

static RE_DDC_SMALL: Lazy<Regex> = Lazy::new(|| Regex::new(r"^0?\d{1,2}$").unwrap());
static VALID_CHARS_SET: Lazy<std::collections::HashSet<char>> = Lazy::new(|| {
    let printable: String = (32u8..=126).map(|c| c as char).collect();
    let drop = "/'′',"; // includes ’ and ,
    let mut set = std::collections::HashSet::new();
    for c in printable.chars() {
        if !drop.contains(c) {
            set.insert(c);
        }
    }
    set.insert('\n');
    set.insert('\r');
    set.insert('\t');
    // keep printable minus /'′’, — actually python: set(printable) - set("/'′',")
    // printable includes those, we remove them.
    // Rebuild correctly:
    set
});

fn collapse_multiple_space(s: &str) -> String {
    MULTIPLE_SPACES_RE.replace_all(s, " ").to_string()
}

fn is_word_char(c: char) -> bool {
    c.is_alphanumeric() || c == '_'
}

pub fn normalize_ddc(ddc: &str) -> Vec<String> {
    // mimic python: collapse spaces, strip, filter VALID_CHARS
    let collapsed = collapse_multiple_space(ddc.trim());
    // VALID_CHARS filtering
    let filtered: String = collapsed
        .chars()
        .filter(|c| {
            // printable check: python printable includes digits, letters, punctuation, whitespace
            // VALID_CHARS = set(printable) - set("/'′',")
            // So keep if c in printable and not in "/'′',"
            let printable = c.is_ascii() && (*c as u8 >= 32 && *c as u8 <= 126)
                || *c == '\t'
                || *c == '\n'
                || *c == '\r'
                || *c == ' '
                || *c == '\x0c';
            if !printable {
                // python printable includes \t\n\r\x0b\x0c etc — but we approximate.
                // For simplicity allow unicode? Python filters to printable only, so non-printable removed.
                return false;
            }
            !matches!(*c, '/' | '\'' | '′' | '’' | ',')
        })
        .collect();

    let mut results: Vec<String> = Vec::new();
    for mat in DDC_RE.find_iter(&filtered) {
        let m = mat.as_str();
        // Get capture groups via regex captures
        let caps = DDC_RE.captures(m).unwrap();
        let prestar = caps.name("prestar").map(|x| x.as_str()).unwrap_or("");
        let neg = caps.name("neg").map(|x| x.as_str()).unwrap_or("");
        let j = caps.name("j").map(|x| x.as_str()).unwrap_or("");
        let number = caps.name("number").map(|x| x.as_str()).unwrap_or("");
        let poststar = caps.name("poststar").map(|x| x.as_str()).unwrap_or("");
        let s = caps.name("s").map(|x| x.as_str()).unwrap_or("");
        let b = caps.name("B").map(|x| x.as_str()).unwrap_or("");
        let ninetwo = caps.name("ninetwo").map(|x| x.as_str()).unwrap_or("");
        let fic = caps.name("fic").map(|x| x.as_str()).unwrap_or("");

        let start = mat.start();
        let end = mat.end();

        // word boundary checks: mimic python re.search(r"\b", ddc[start-1])
        // For single char before/after check if boundary exists.
        // We'll approximate: if start>0 and is_word_char(prev) == is_word_char(curr_first) then not boundary -> skip? Actually python checks if search finds \b in single char string.
        // re.search(r"\b", "a") will find boundary? Let's just implement proper boundary: start should be at word boundary, end should be at word boundary.
        // Word boundary defined as transition between \w and \W.
        // So check: (start==0 || is_word_char(prev) != is_word_char(first)) and similarly for end.
        // But python's code is odd; we try to emulate: if start>0 and re.search(r"\b", filtered[start-1..start]) is Some then continue? That would be if single char contains boundary — which for "a" returns Some at pos0? Test with python quickly mental: re.search(r"\b", "a") returns match at 0 (since \b at start of word). So it would skip many valid matches. So we instead implement intended logic: DDC should start/end at word boundaries.
        // We'll use proper boundary check.

        // Python (utils/ddc.py:58-65) checks \b against the SINGLE adjacent chars:
        //   skip if start>0 and ddc[start-1] is a word char
        //   skip if end<len and ddc[end]     is a word char
        // (not a transition check — the char at `end` itself decides)
        let prev_is_word = start > 0
            && filtered
                .chars()
                .nth(start - 1)
                .map(is_word_char)
                .unwrap_or(false);
        if prev_is_word {
            continue;
        }
        let next_is_word = filtered.chars().nth(end).map(is_word_char).unwrap_or(false);
        if next_is_word {
            continue;
        }

        let mut prefix = String::new();
        let mut suffix = String::new();
        if !neg.is_empty() {
            prefix.push('-');
        }
        if !j.is_empty() {
            prefix.push('j');
        }
        if !prestar.is_empty() || !poststar.is_empty() {
            suffix = "*".to_string();
        }
        if !s.trim().is_empty() {
            suffix.push_str(" s");
        }
        if !b.trim().is_empty() {
            suffix.push_str(" B");
        }
        if !ninetwo.is_empty() {
            suffix.push_str(ninetwo);
        }

        let number_str: String;
        if !number.is_empty() {
            // check for ) after number
            let number_end = caps.name("number").unwrap().end();
            if number_end < filtered.len() && filtered.chars().nth(number_end).unwrap() == ')' {
                suffix.push_str(" s");
            }
            let parts: Vec<&str> = number.split('.').collect();
            let integer = parts[0].trim();
            let decimal = if parts.len() > 1 {
                format!(".{}", parts[parts.len() - 1].trim())
            } else {
                String::new()
            };
            let int_val: i32 = integer.parse().unwrap_or(0);
            number_str = format!("{:03}{}", int_val, decimal);
            // discard catalog edition number: if results not empty and number matches ^0?\d{1,2}$
            if !results.is_empty() {
                if RE_DDC_SMALL.is_match(number) {
                    continue;
                }
            }
        } else if !fic.is_empty() {
            // title case
            let mut fic_title = fic.to_lowercase();
            if fic_title.len() > 0 {
                fic_title = fic_title[..1].to_uppercase() + &fic_title[1..];
            }
            number_str = format!("[{}]", fic_title);
        } else {
            continue;
        }

        let base = format!("{}{}{}", prefix, number_str, suffix);
        results.push(base.clone());
        if prefix == "j" {
            results.push(format!("{}{}", number_str, suffix));
        }
    }
    results
}

pub fn choose_sorting_ddc(ddcs: &[String]) -> String {
    let preferred: Vec<&String> = ddcs
        .iter()
        .filter(|d| {
            d.chars()
                .next()
                .map(|c| c.is_ascii_digit())
                .unwrap_or(false)
        })
        .collect();
    let candidates: Vec<&String> = if !preferred.is_empty() {
        preferred
    } else {
        ddcs.iter().collect()
    };
    // Python: max(preferred or ddcs, key=len) -> first max wins
    let mut best: Option<&String> = None;
    let mut best_len: usize = 0;
    for s in candidates {
        let l = s.len();
        if l > best_len {
            best_len = l;
            best = Some(s);
        }
    }
    best.unwrap().to_string()
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn test_basic() {
        assert_eq!(normalize_ddc("123"), vec!["123"]);
        assert_eq!(normalize_ddc("j123"), vec!["j123", "123"]);
        assert_eq!(normalize_ddc("813/.54"), vec!["813.54"]);
        // 92 rides along as a suffix on the same result (matches openlibrary/utils/ddc.py)
        assert_eq!(normalize_ddc("823.914 92"), vec!["823.914 92"]);
    }
}
