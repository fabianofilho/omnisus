use _native::{decode::Encoding, error::Error, reader::Reader};
use arrow_array::{Array, Int64Array, StringArray};
use arrow_schema::DataType;
use proptest::prelude::*;

fn dbf(fields: &[(&str, u8, u16)], rows: &[&[u8]]) -> Vec<u8> {
    let h = 33 + fields.len() * 32;
    let r = 1 + fields.iter().map(|f| usize::from(f.2)).sum::<usize>();
    let mut out = vec![0; h];
    out[0] = 3;
    out[4..8].copy_from_slice(&(rows.len() as u32).to_le_bytes());
    out[8..10].copy_from_slice(&(h as u16).to_le_bytes());
    out[10..12].copy_from_slice(&(r as u16).to_le_bytes());
    for (i, (name, kind, width)) in fields.iter().enumerate() {
        let off = 32 + i * 32;
        out[off..off + name.len()].copy_from_slice(name.as_bytes());
        out[off + 11] = *kind;
        out[off + 16] = *width as u8;
        if *kind == b'C' {
            out[off + 17] = (*width >> 8) as u8;
        }
    }
    out[h - 1] = 13;
    for row in rows {
        assert_eq!(row.len(), r);
        out.extend_from_slice(row);
    }
    out.push(0x1a);
    out
}

#[test]
fn batches_count_active_rows_and_outlive_closed_reader() {
    let data = dbf(
        &[("C", b'C', 3), ("N", b'N', 16)],
        &[
            b" 0019007199254740993",
            b"*badxxxxxxxxxxxxxxxx",
            b"    1152921504606846",
        ],
    );
    let mut reader = Reader::new(data, Encoding::Latin1, 1).unwrap();
    let first = reader.next_batch().unwrap().unwrap();
    let second = reader.next_batch().unwrap().unwrap();
    assert_eq!(first.num_rows(), 1);
    assert_eq!(
        first
            .column(0)
            .as_any()
            .downcast_ref::<StringArray>()
            .unwrap()
            .value(0),
        "001"
    );
    assert_eq!(
        first
            .column(1)
            .as_any()
            .downcast_ref::<Int64Array>()
            .unwrap()
            .value(0),
        9007199254740993
    );
    assert_eq!(
        second
            .column(0)
            .as_any()
            .downcast_ref::<StringArray>()
            .unwrap()
            .value(0),
        ""
    );
    assert!(reader.next_batch().unwrap().is_none());
    reader.close();
    reader.close();
    drop(reader);
    assert_eq!(first.column(1).len(), 1);
}

#[test]
fn null_schema_and_numeric_families_are_inferred_per_batch() {
    let data = dbf(&[("N", b'N', 3)], &[b"    ", b"   1", b" 1.5"]);
    let mut reader = Reader::new(data.clone(), Encoding::Latin1, 1).unwrap();
    assert_eq!(
        reader
            .next_batch()
            .unwrap()
            .unwrap()
            .schema()
            .field(0)
            .data_type(),
        &DataType::Null
    );
    assert_eq!(
        reader
            .next_batch()
            .unwrap()
            .unwrap()
            .schema()
            .field(0)
            .data_type(),
        &DataType::Int64
    );
    assert_eq!(
        reader
            .next_batch()
            .unwrap()
            .unwrap()
            .schema()
            .field(0)
            .data_type(),
        &DataType::Float64
    );
    assert!(matches!(
        Reader::new(data, Encoding::Latin1, 3).unwrap().next_batch(),
        Err(Error::Type(_))
    ));
}

#[test]
fn header_checks_geometry_types_flags_and_real_descriptor_terminator() {
    let good = dbf(&[("C", b'C', 1)], &[b" a"]);
    for len in 0..good.len() - 1 {
        assert!(
            matches!(
                Reader::new(good[..len].to_vec(), Encoding::Latin1, 7),
                Err(Error::Invalid(_))
            ),
            "len={len}"
        );
    }
    let mut bad = good.clone();
    bad[4..8].copy_from_slice(&u32::MAX.to_le_bytes());
    assert!(matches!(
        Reader::new(bad, Encoding::Latin1, 7),
        Err(Error::Invalid(_))
    ));
    let mut bad = good.clone();
    bad[10] = 3;
    assert!(matches!(
        Reader::new(bad, Encoding::Latin1, 7),
        Err(Error::Invalid(_))
    ));
    let mut bad = good.clone();
    bad[64] = 0;
    assert!(matches!(
        Reader::new(bad, Encoding::Latin1, 7),
        Err(Error::Invalid(_))
    ));
    assert!(matches!(
        Reader::new(dbf(&[("L", b'L', 1)], &[]), Encoding::Latin1, 7),
        Err(Error::Unsupported(_))
    ));
    let mut fox = good.clone();
    fox[0] = 0x30;
    fox.splice(65..65, [0x7fu8; 263]);
    fox[8..10].copy_from_slice(&328u16.to_le_bytes());
    assert!(
        Reader::new(fox, Encoding::Latin1, 7)
            .unwrap()
            .next_batch()
            .unwrap()
            .is_some()
    );
    assert!(matches!(
        Reader::new(good, Encoding::Latin1, 0),
        Err(Error::Value(_))
    ));
}

#[test]
fn errors_after_first_batch_do_not_replay_or_decode_deleted_values() {
    let data = dbf(&[("N", b'N', 3)], &[b"   1", b"*bad", b" bad"]);
    let mut reader = Reader::new(data, Encoding::Latin1, 1).unwrap();
    assert!(reader.next_batch().unwrap().is_some());
    assert!(matches!(reader.next_batch(), Err(Error::Value(_))));
    assert!(reader.next_batch().unwrap().is_none());
}

proptest! {
    #![proptest_config(ProptestConfig::with_cases(512))]
    #[test]
    fn arbitrary_inputs_never_panic(data in proptest::collection::vec(any::<u8>(),0..8192), batch_rows in 1usize..128) {
        if let Ok(mut reader)=Reader::new(data,Encoding::Latin1,batch_rows) {
            while let Ok(Some(_))=reader.next_batch() {}
        }
    }
    #[test]
    fn valid_values_survive_batch_boundaries(values in proptest::collection::vec(-9999i64..99999,0..100), batch_rows in 1usize..31) {
        let rows=values.iter().map(|v| format!(" {v:>6}").into_bytes()).collect::<Vec<_>>();
        let refs=rows.iter().map(Vec::as_slice).collect::<Vec<_>>();
        let mut reader=Reader::new(dbf(&[("N",b'N',6)],&refs),Encoding::Latin1,batch_rows).unwrap();
        let mut actual=Vec::new();
        while let Some(batch)=reader.next_batch().unwrap() {
            prop_assert!(batch.num_rows()>0 && batch.num_rows()<=batch_rows);
            actual.extend(batch.column(0).as_any().downcast_ref::<Int64Array>().unwrap().values().iter().copied());
        }
        prop_assert_eq!(actual,values);
    }
}

#[test]
fn eof_stops_before_padding_and_empty_descriptor_tables_are_unsupported() {
    let mut data = dbf(&[("C", b'C', 1)], &[b" a"]);
    data.extend_from_slice(b"\0\0 arbitrary bytes after EOF");
    let mut reader = Reader::new(data, Encoding::Latin1, 7).unwrap();
    assert_eq!(reader.next_batch().unwrap().unwrap().num_rows(), 1);
    assert!(reader.next_batch().unwrap().is_none());
    assert!(matches!(
        Reader::new(dbf(&[], &[b" "]), Encoding::Latin1, 7),
        Err(Error::Unsupported(_))
    ));
}

#[test]
fn shared_synthetic_corpus_is_read_directly_from_repository() {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../tests/fixtures/dbf");
    for name in ["text-latin1.dbf", "numeric-exact.dbf", "date.dbf"] {
        let data = std::fs::read(root.join(name)).expect("required shared fixture");
        let mut reader = Reader::new(data, Encoding::Latin1, 1).unwrap();
        let mut count = 0;
        while let Some(batch) = reader.next_batch().unwrap() {
            count += batch.num_rows();
        }
        assert!(count > 0);
    }
    assert!(matches!(
        Reader::new(
            std::fs::read(root.join("unsupported-logical.dbf")).unwrap(),
            Encoding::Latin1,
            1
        ),
        Err(Error::Unsupported(_))
    ));
}

#[test]
fn date_fields_follow_dbfread_parse_d() {
    use arrow_array::Date32Array;
    let data = dbf(
        &[("D", b'D', 8)],
        &[
            b" 19700102",
            b"         ",
            b" 00000000",
            b" 2_240101",
            b" 20240229",
        ],
    );
    let mut reader = Reader::new(data, Encoding::Latin1, 10).unwrap();
    let batch = reader.next_batch().unwrap().unwrap();
    assert_eq!(batch.schema().field(0).data_type(), &DataType::Date32);
    let column = batch
        .column(0)
        .as_any()
        .downcast_ref::<Date32Array>()
        .unwrap();
    let values = (0..column.len())
        .map(|i| column.is_valid(i).then(|| column.value(i)))
        .collect::<Vec<_>>();
    // 0224-01-01 and 2024-02-29 as days since the epoch.
    assert_eq!(values, [Some(1), None, None, Some(-637_714), Some(19_782)]);
}

#[test]
fn null_only_date_batch_stays_arrow_null_and_bad_date_fails() {
    let data = dbf(&[("D", b'D', 8)], &[b"         ", b" 20241301"]);
    let mut reader = Reader::new(data, Encoding::Latin1, 1).unwrap();
    let first = reader.next_batch().unwrap().unwrap();
    assert_eq!(first.schema().field(0).data_type(), &DataType::Null);
    assert!(matches!(reader.next_batch(), Err(Error::Value(_))));
}
