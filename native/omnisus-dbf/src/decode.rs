use crate::error::{Error, Result};

#[derive(Clone, Copy, Debug)]
pub enum Encoding {
    Latin1,
    Cp1252,
    Ascii,
    Utf8,
}

impl Encoding {
    pub fn from_name(name: &str) -> Result<Self> {
        match name {
            "iso8859-1" | "latin-1" | "latin1" => Ok(Self::Latin1),
            "cp1252" => Ok(Self::Cp1252),
            "ascii" => Ok(Self::Ascii),
            "utf-8" | "utf8" => Ok(Self::Utf8),
            _ => Err(Error::Unsupported(format!(
                "encoding {name:?} is not supported"
            ))),
        }
    }
    fn name(self) -> &'static str {
        match self {
            Self::Latin1 => "iso8859-1",
            Self::Cp1252 => "cp1252",
            Self::Ascii => "ascii",
            Self::Utf8 => "utf-8",
        }
    }
}

#[derive(Debug, PartialEq)]
pub enum Number {
    Null,
    Int(i64),
    Float(f64),
}

/// Decode descriptor names without applying field-value padding rules.
pub fn decode(data: &[u8], encoding: Encoding) -> Result<String> {
    let failure = |start, end| Error::Decode {
        encoding: encoding.name(),
        data: data.to_vec(),
        start,
        end,
    };
    if matches!(encoding, Encoding::Utf8) {
        return std::str::from_utf8(data).map(str::to_owned).map_err(|e| {
            failure(
                e.valid_up_to(),
                e.valid_up_to() + e.error_len().unwrap_or(data.len() - e.valid_up_to()),
            )
        });
    }
    // Fast path also preserves ASCII control bytes verbatim.
    if data.is_ascii() {
        return Ok(String::from_utf8(data.to_vec()).expect("validated ASCII"));
    }
    const CP1252: [u16; 32] = [
        0x20ac, 0, 0x201a, 0x0192, 0x201e, 0x2026, 0x2020, 0x2021, 0x02c6, 0x2030, 0x0160, 0x2039,
        0x0152, 0, 0x017d, 0, 0, 0x2018, 0x2019, 0x201c, 0x201d, 0x2022, 0x2013, 0x2014, 0x02dc,
        0x2122, 0x0161, 0x203a, 0x0153, 0, 0x017e, 0x0178,
    ];
    let mut value = String::with_capacity(data.len());
    for (i, &byte) in data.iter().enumerate() {
        let codepoint = match encoding {
            Encoding::Ascii if byte >= 128 => return Err(failure(i, i + 1)),
            Encoding::Cp1252 if (0x80..0xa0).contains(&byte) => {
                let codepoint = CP1252[usize::from(byte - 0x80)];
                if codepoint == 0 {
                    return Err(failure(i, i + 1));
                }
                codepoint
            }
            _ => u16::from(byte),
        };
        value.push(char::from_u32(u32::from(codepoint)).expect("single-byte encoding scalar"));
    }
    Ok(value)
}

pub fn text(data: &[u8], encoding: Encoding) -> Result<String> {
    let end = data
        .iter()
        .rposition(|&b| b != 0 && b != b' ')
        .map_or(0, |i| i + 1);
    decode(&data[..end], encoding)
}

fn strip_stars_nuls(mut data: &[u8]) -> &[u8] {
    while data.first().is_some_and(|b| matches!(*b, b'*' | 0)) {
        data = &data[1..];
    }
    while data.last().is_some_and(|b| matches!(*b, b'*' | 0)) {
        data = &data[..data.len() - 1];
    }
    data
}

fn python_strip(mut data: &[u8]) -> &[u8] {
    // Rust's ASCII whitespace deliberately excludes VT; Python bytes.strip includes it.
    let whitespace = |b: &u8| matches!(*b, b' ' | b'\t' | b'\r' | b'\n' | 0x0b | 0x0c);
    while data.first().is_some_and(whitespace) {
        data = &data[1..];
    }
    while data.last().is_some_and(whitespace) {
        data = &data[..data.len() - 1];
    }
    data
}

pub fn number(raw: &[u8]) -> Result<Number> {
    // bytes.strip(), then strip(b'*\0'); int/float accept outer ASCII whitespace.
    let data = python_strip(strip_stars_nuls(python_strip(raw)));
    if data.is_empty() {
        return Ok(Number::Null);
    }
    let invalid = || Error::Value("invalid numeric DBF value".into());
    if !data.is_ascii() {
        return Err(invalid());
    }
    // Python permits underscores only between decimal digits, for both int and float.
    for (i, &b) in data.iter().enumerate() {
        if b == b'_'
            && (i == 0
                || i + 1 == data.len()
                || !data[i - 1].is_ascii_digit()
                || !data[i + 1].is_ascii_digit())
        {
            return Err(invalid());
        }
    }
    let normalized = data
        .iter()
        .filter(|&&b| b != b'_')
        .map(|&b| if b == b',' { b'.' } else { b })
        .collect::<Vec<_>>();
    let s = std::str::from_utf8(&normalized).map_err(|_| invalid())?;
    let unsigned = s.strip_prefix(['+', '-']).unwrap_or(s);
    if !unsigned.is_empty() && unsigned.bytes().all(|b| b.is_ascii_digit()) {
        return s
            .parse::<i64>()
            .map(Number::Int)
            .map_err(|_| Error::Value("integer is outside the Arrow int64 range".into()));
    }
    // Rust accepts the same decimal/exponent grammar after validated underscores.
    // Special float spellings are case insensitive in Python.
    let float = if unsigned.eq_ignore_ascii_case("nan") {
        if s.starts_with('-') {
            -f64::NAN
        } else {
            f64::NAN
        }
    } else if unsigned.eq_ignore_ascii_case("inf") || unsigned.eq_ignore_ascii_case("infinity") {
        if s.starts_with('-') {
            f64::NEG_INFINITY
        } else {
            f64::INFINITY
        }
    } else {
        s.parse::<f64>().map_err(|_| invalid())?
    };
    Ok(Number::Float(float))
}

/// Python `int(bytes)` for the short slices of a date: outer whitespace, one sign,
/// ASCII digits with single underscores between digits. `None` where Python raises.
fn python_int(raw: &[u8]) -> Option<i64> {
    let data = python_strip(raw);
    let digits = data
        .strip_prefix(b"+")
        .or_else(|| data.strip_prefix(b"-"))
        .unwrap_or(data);
    let valid = !digits.is_empty()
        && digits.first().is_some_and(u8::is_ascii_digit)
        && digits.last().is_some_and(u8::is_ascii_digit)
        && digits.iter().all(|&b| b.is_ascii_digit() || b == b'_')
        && !digits.windows(2).any(|w| w == b"__");
    if !valid {
        return None;
    }
    let value = digits
        .iter()
        .filter(|&&b| b != b'_')
        .try_fold(0i64, |acc, &b| {
            acc.checked_mul(10)?.checked_add(i64::from(b - b'0'))
        })?;
    Some(if data.first() == Some(&b'-') {
        -value
    } else {
        value
    })
}

/// Days since 1970-01-01 of a valid proleptic Gregorian date (Hinnant's days_from_civil).
fn days_from_civil(year: i64, month: i64, day: i64) -> i64 {
    let y = if month <= 2 { year - 1 } else { year };
    let era = y.div_euclid(400);
    let yoe = y - era * 400;
    let mp = (month + 9) % 12;
    let doy = (153 * mp + 2) / 5 + day - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    era * 146_097 + doe - 719_468
}

/// dbfread2 `parseD`: `date(int(data[:4]), int(data[4:6]), int(data[6:8]))`; on failure,
/// a value made only of spaces, zeros and NULs is null and anything else is an error.
pub fn date(raw: &[u8]) -> Result<Option<i32>> {
    let part = |range: std::ops::Range<usize>| {
        python_int(&raw[range.start.min(raw.len())..range.end.min(raw.len())])
    };
    let parsed = match (part(0..4), part(4..6), part(6..8)) {
        (Some(y), Some(m), Some(d)) if (1..=9999).contains(&y) && (1..=12).contains(&m) => {
            let leap = y % 4 == 0 && (y % 100 != 0 || y % 400 == 0);
            let last = match m {
                2 if leap => 29,
                2 => 28,
                4 | 6 | 9 | 11 => 30,
                _ => 31,
            };
            (1..=last).contains(&d).then(|| days_from_civil(y, m, d))
        }
        _ => None,
    };
    match parsed {
        // Every year 1 to 9999 fits in i32 days.
        Some(days) => Ok(Some(days as i32)),
        None if raw.iter().all(|&b| matches!(b, b' ' | b'0' | 0)) => Ok(None),
        None => Err(Error::Value(format!(
            "invalid date {:?}",
            String::from_utf8_lossy(raw)
        ))),
    }
}
