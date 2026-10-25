use crate::{
    decode::{self, Encoding, Number},
    error::{Error, Result},
    header::Header,
};
use arrow_array::{
    ArrayRef, NullArray, RecordBatch, RecordBatchOptions,
    builder::{Date32Builder, Float64Builder, Int64Builder, StringBuilder},
};
use arrow_schema::{Field, Schema};
use std::sync::Arc;

enum Column {
    Text(StringBuilder),
    Null(usize),
    Int(Int64Builder),
    Float(Float64Builder),
    Date(Date32Builder),
}

impl Column {
    fn append(&mut self, data: &[u8], kind: u8, encoding: Encoding) -> Result<()> {
        if let Self::Text(builder) = self {
            let value = decode::text(data, encoding)?;
            if builder
                .values_slice()
                .len()
                .checked_add(value.len())
                .is_none_or(|n| n > i32::MAX as usize)
            {
                return Err(Error::Value(
                    "text batch exceeds Arrow string offset range; reduce batch_rows".into(),
                ));
            }
            builder.append_value(value);
            return Ok(());
        }
        if kind == b'D' {
            let value = decode::date(data)?;
            // A date column stays Arrow null until its first value, like numbers.
            if let Self::Null(count) = self {
                let count = *count;
                match value {
                    None => *self = Self::Null(count + 1),
                    Some(days) => {
                        let mut b = Date32Builder::new();
                        b.append_nulls(count);
                        b.append_value(days);
                        *self = Self::Date(b);
                    }
                }
                return Ok(());
            }
            let Self::Date(b) = self else {
                return Err(Error::Type("DBF date column holds a non-date value".into()));
            };
            b.append_option(value);
            return Ok(());
        }
        let value = decode::number(data)?;
        if let Self::Null(count) = self {
            let count = *count;
            match value {
                Number::Null => {
                    *self = Self::Null(count + 1);
                    return Ok(());
                }
                Number::Int(_) => {
                    let mut b = Int64Builder::new();
                    b.append_nulls(count);
                    *self = Self::Int(b);
                }
                Number::Float(_) => {
                    let mut b = Float64Builder::new();
                    b.append_nulls(count);
                    *self = Self::Float(b);
                }
            }
        }
        match (self, value) {
            (Self::Int(b), Number::Null) => b.append_null(),
            (Self::Int(b), Number::Int(v)) => b.append_value(v),
            (Self::Float(b), Number::Null) => b.append_null(),
            (Self::Float(b), Number::Float(v)) => b.append_value(v),
            _ => {
                return Err(Error::Type(
                    "incompatible integer and float families in DBF batch".into(),
                ));
            }
        }
        Ok(())
    }

    fn finish(self) -> ArrayRef {
        match self {
            Self::Text(mut b) => Arc::new(b.finish()),
            Self::Null(n) => Arc::new(NullArray::new(n)),
            Self::Int(mut b) => Arc::new(b.finish()),
            Self::Float(mut b) => Arc::new(b.finish()),
            Self::Date(mut b) => Arc::new(b.finish()),
        }
    }
}

pub fn build(
    data: &[u8],
    header: &Header,
    encoding: Encoding,
    rows: &[usize],
) -> Result<RecordBatch> {
    let mut columns = header
        .fields
        .iter()
        .map(|f| {
            if f.kind == b'C' {
                Column::Text(StringBuilder::new())
            } else {
                Column::Null(0)
            }
        })
        .collect::<Vec<_>>();
    for &record in rows {
        for (field, column) in header.fields.iter().zip(&mut columns) {
            // Header geometry and each record index are checked before batching.
            let start = record
                .checked_add(field.offset)
                .ok_or_else(|| Error::Invalid("field offset overflow".into()))?;
            let end = start
                .checked_add(field.length)
                .ok_or_else(|| Error::Invalid("field width overflow".into()))?;
            let bytes = data
                .get(start..end)
                .ok_or_else(|| Error::Invalid("truncated DBF field".into()))?;
            column.append(bytes, field.kind, encoding)?;
        }
    }
    let arrays = columns.into_iter().map(Column::finish).collect::<Vec<_>>();
    let fields = header
        .fields
        .iter()
        .zip(&arrays)
        .map(|(f, a)| Field::new(&f.name, a.data_type().clone(), true))
        .collect::<Vec<_>>();
    RecordBatch::try_new_with_options(
        Arc::new(Schema::new(fields)),
        arrays,
        &RecordBatchOptions::new().with_row_count(Some(rows.len())),
    )
    .map_err(|e| Error::Value(e.to_string()))
}
