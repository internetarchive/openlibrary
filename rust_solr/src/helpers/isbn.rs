fn canonical(isbn: &str) -> String {
    isbn.chars()
        .filter(|c| c.is_ascii_digit() || *c == 'X' || *c == 'x')
        .map(|c| if c == 'x' { 'X' } else { c })
        .collect()
}

fn check_digit_10(isbn9: &str) -> Option<char> {
    if isbn9.len() != 9 || !isbn9.chars().all(|c| c.is_ascii_digit()) {
        return None;
    }
    let mut sum: i32 = 0;
    for (i, c) in isbn9.chars().enumerate() {
        sum += ((i + 1) as i32) * (c.to_digit(10).unwrap() as i32);
    }
    let r = sum % 11;
    if r == 10 {
        Some('X')
    } else {
        Some(std::char::from_digit(r as u32, 10).unwrap())
    }
}

fn check_digit_13(isbn12: &str) -> Option<char> {
    if isbn12.len() != 12 || !isbn12.chars().all(|c| c.is_ascii_digit()) {
        return None;
    }
    let mut sum = 0;
    for (i, c) in isbn12.chars().enumerate() {
        let d = c.to_digit(10).unwrap() as i32;
        let w = if i % 2 == 1 { 3 } else { 1 };
        sum += w * d;
    }
    let r = 10 - (sum % 10);
    if r == 10 {
        Some('0')
    } else {
        Some(std::char::from_digit(r as u32, 10).unwrap())
    }
}

fn isbn_13_to_10(isbn13: &str) -> Option<String> {
    let c = canonical(isbn13);
    if c.len() != 13 || !c.chars().all(|v| v.is_ascii_digit()) || !c.starts_with("978") {
        return None;
    }
    let check = check_digit_13(&c[..12])?;
    if check != c.chars().last().unwrap() {
        return None;
    }
    let core = &c[3..12];
    let check10 = check_digit_10(core)?;
    Some(format!("{}{}", core, check10))
}

fn isbn_10_to_13(isbn10: &str) -> Option<String> {
    let c = canonical(isbn10);
    if c.len() != 10 || !c[..9].chars().all(|v| v.is_ascii_digit()) {
        return None;
    }
    let check = check_digit_10(&c[..9])?;
    if check != c.chars().last().unwrap() {
        return None;
    }
    let core = format!("978{}", &c[..9]);
    let check13 = check_digit_13(&core)?;
    Some(format!("{}{}", core, check13))
}

pub fn opposite_isbn(isbn: &str) -> Option<String> {
    let c = canonical(isbn);
    if let Some(v) = isbn_13_to_10(&c) {
        return Some(v);
    }
    if let Some(v) = isbn_10_to_13(&c) {
        return Some(v);
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn test_opposite() {
        assert_eq!(
            opposite_isbn("9781576079454"),
            Some("1576079457".to_string())
        );
        assert_eq!(
            opposite_isbn("1576079457"),
            Some("9781576079454".to_string())
        );
    }
}
