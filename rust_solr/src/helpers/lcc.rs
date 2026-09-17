use once_cell::sync::Lazy;
use regex::Regex;

static LCC_PARTS_RE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(
        r"(?ix)^
    (?P<letters>[A-HJ-NP-VWZ][A-Z-]{0,2})
    \s?
    (?P<number>\d{1,4}(\.\d+)?)?
    (?P<cutter1>\s*\.\s*[^\d\s\[]{1,3}\d*\S*)?
    (?P<rest>\s.*)?
    $",
    )
    .unwrap()
});

fn collapse_multiple_space(s: &str) -> String {
    static RE: Lazy<Regex> = Lazy::new(|| Regex::new(r"\s+").unwrap());
    RE.replace_all(s, " ").to_string()
}

fn clean_raw_lcc(raw_lcc: &str) -> String {
    let mut lcc = collapse_multiple_space(&raw_lcc.replace('\\', " "));
    lcc = lcc.trim().to_string();
    if (lcc.starts_with('[') && lcc.ends_with(']')) || (lcc.starts_with('(') && lcc.ends_with(')'))
    {
        lcc = lcc[1..lcc.len() - 1].to_string();
    }
    lcc
}

pub fn short_lcc_to_sortable_lcc(lcc: &str) -> Option<String> {
    let cleaned = clean_raw_lcc(lcc);
    let caps = LCC_PARTS_RE.captures(&cleaned)?;
    let letters_raw = caps.name("letters")?.as_str().to_uppercase();
    let letters = format!("{:-<3}", letters_raw);
    if letters == "CPB" {
        return None;
    }
    let number_str = caps.name("number").map(|m| m.as_str()).unwrap_or("");
    let number_val: f64 = if number_str.is_empty() {
        0.0
    } else {
        number_str.parse().unwrap_or(0.0)
    };
    let cutter1 = if let Some(m) = caps.name("cutter1") {
        let raw = m.as_str();
        let lstripped = raw.trim_start_matches(|c| c == ' ' || c == '.');
        if lstripped.is_empty() {
            String::new()
        } else {
            // lstrip only " ." then prefix "."
            let inner = raw.trim_start_matches(|c| c == ' ' || c == '.');
            format!(".{}", inner.trim_start_matches(|c| c == ' ' || c == '.'))
        }
    } else {
        String::new()
    };
    // Handle lstrip correctly: python does ".".lstrip? Actually ".": lstrip(" .") -> but we want one dot prefix
    let cutter1_correct = if caps.name("cutter1").is_some() {
        let raw = caps.name("cutter1").unwrap().as_str();
        let lstripped = raw.trim_start_matches(|c| c == ' ' || c == '.');
        if lstripped.is_empty() {
            String::new()
        } else {
            format!(".{}", lstripped)
        }
    } else {
        String::new()
    };
    let rest_raw = caps.name("rest").map(|m| m.as_str()).unwrap_or("");
    let rest = if rest_raw.trim().is_empty() {
        String::new()
    } else {
        format!(" {}", rest_raw.trim())
    };
    let result = format!("{}{:013.8}{}{}", letters, number_val, cutter1_correct, rest);
    Some(result)
}

pub fn sortable_lcc_to_short_lcc(lcc: &str) -> String {
    let caps = match LCC_PARTS_RE.captures(lcc) {
        Some(c) => c,
        // Unparseable (e.g. cutter like ".2" breaks round-trip). Python asserts here;
        // fall back to the input instead of panicking the whole chunk.
        None => return lcc.to_string(),
    };
    let letters_raw = caps.name("letters").unwrap().as_str();
    let letters = letters_raw.trim_end_matches('-').to_string();
    let number_raw = caps.name("number").map(|m| m.as_str()).unwrap_or("");
    // Python: parts["number"].strip("0").strip(".") — strips zeros from BOTH ends, then dots
    let number = number_raw
        .trim_matches('0')
        .trim_end_matches('.')
        .to_string();
    let cutter1_raw = caps.name("cutter1").map(|m| m.as_str()).unwrap_or("");
    let cutter1 = cutter1_raw.trim().to_string();
    let rest_raw = caps.name("rest").map(|m| m.as_str()).unwrap_or("");
    let rest = if rest_raw.trim().is_empty() {
        String::new()
    } else {
        format!(" {}", rest_raw.trim())
    };
    format!("{}{}{}{}", letters, number, cutter1, rest)
}

pub fn choose_sorting_lcc(sortable_lccs: &[String]) -> String {
    // Python: max(sortable_lccs, key=lambda s: len(sortable_lcc_to_short_lcc(s))) -> first max wins
    let mut best: Option<&String> = None;
    let mut best_len: usize = 0;
    for s in sortable_lccs {
        let l = sortable_lcc_to_short_lcc(s).len();
        if l > best_len {
            best_len = l;
            best = Some(s);
        }
    }
    best.unwrap().clone()
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn test_lcc() {
        assert_eq!(
            short_lcc_to_sortable_lcc("PZ73.S758345255 2011").unwrap(),
            "PZ-0073.00000000.S758345255 2011"
        );
        assert_eq!(
            short_lcc_to_sortable_lcc("PZ8.3.G276Lo 1971").unwrap(),
            "PZ-0008.30000000.G276Lo 1971"
        );
        assert!(short_lcc_to_sortable_lcc("CPB Box no. 1516").is_none());
    }
}
