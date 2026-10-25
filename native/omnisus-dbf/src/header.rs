use crate::{
    decode::{Encoding, decode},
    error::{Error, Result},
};
use std::collections::HashSet;

#[derive(Debug)]
pub struct Field {
    pub name: String,
    pub kind: u8,
    pub offset: usize,
    pub length: usize,
}

#[derive(Debug)]
pub struct Header {
    pub fields: Vec<Field>,
    pub header_len: usize,
    pub record_len: usize,
    pub record_count: usize,
}

impl Header {
    pub fn parse(data: &[u8], encoding: Encoding) -> Result<Self> {
        let invalid = || Error::Invalid("invalid or truncated DBF geometry".into());
        if data.len() < 33 {
            return Err(invalid());
        }
        let header_len = usize::from(u16::from_le_bytes([data[8], data[9]]));
        let record_len = usize::from(u16::from_le_bytes([data[10], data[11]]));
        let record_count = u32::from_le_bytes([data[4], data[5], data[6], data[7]]) as usize;
        if header_len < 33 || header_len > data.len() || record_len == 0 {
            return Err(invalid());
        }
        let payload = record_count
            .checked_mul(record_len)
            .and_then(|n| header_len.checked_add(n))
            .ok_or_else(invalid)?;
        if payload > data.len() {
            return Err(invalid());
        }
        if !matches!(&data[payload..], [] | [0x1a, ..]) {
            return Err(Error::Invalid(
                "unexpected bytes after declared DBF records".into(),
            ));
        }
        if !matches!(data[0], 0x03 | 0x30) {
            return Err(Error::Unsupported(format!(
                "DBF version 0x{:02x} is not supported",
                data[0]
            )));
        }
        if data[14] != 0 || data[15] != 0 {
            return Err(Error::Unsupported(
                "transactional or encrypted DBF is not supported".into(),
            ));
        }
        let mut descriptor = 32usize;
        let mut offset = 1usize;
        let mut fields = Vec::new();
        let mut names = HashSet::new();
        while descriptor < header_len && !matches!(data[descriptor], b'\r' | b'\n') {
            let end = descriptor.checked_add(32).ok_or_else(invalid)?;
            if end > header_len {
                return Err(invalid());
            }
            let field = &data[descriptor..end];
            let kind = field[11];
            if !matches!(kind, b'C' | b'N' | b'D') {
                return Err(Error::Unsupported(format!(
                    "DBF field type 0x{kind:02x} is not supported"
                )));
            }
            let length = usize::from(field[16])
                + if kind == b'C' {
                    usize::from(field[17]) << 8
                } else {
                    0
                };
            let name_end = field[..11].iter().position(|&b| b == 0).unwrap_or(11);
            let name = decode(&field[..name_end], encoding)?;
            if !names.insert(name.clone()) {
                return Err(Error::Unsupported(
                    "duplicate DBF field names are not supported".into(),
                ));
            }
            fields.push(Field {
                name,
                kind,
                offset,
                length,
            });
            offset = offset.checked_add(length).ok_or_else(invalid)?;
            if offset > record_len {
                return Err(invalid());
            }
            descriptor = end;
        }
        if descriptor >= header_len || offset != record_len {
            return Err(invalid());
        }
        if fields.is_empty() {
            return Err(Error::Unsupported(
                "DBF tables without fields are not supported".into(),
            ));
        }
        // FoxPro's extended header follows the first real CR/LF terminator.
        Ok(Self {
            fields,
            header_len,
            record_len,
            record_count,
        })
    }
}
