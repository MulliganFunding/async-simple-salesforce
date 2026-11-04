"""Tests for the async CSV helpers in aio/bulk2.py"""

import csv

import pytest

from simple_salesforce.aio.bulk2 import _count_csv, _get_csv_fieldnames, _split_csv
from simple_salesforce.bulk2 import (
    ColumnDelimiter,
    LineEnding,
    _convert_dict_to_csv,
    _delimiter_char,
    _line_ending_char,
)

QUOTINGS = [csv.QUOTE_ALL, csv.QUOTE_MINIMAL, csv.QUOTE_NONE]
LINE_ENDINGS = [LineEnding.LF, LineEnding.CRLF]
COLUMN_DELIMITERS = [
    ColumnDelimiter.BACKQUOTE,
    ColumnDelimiter.CARET,
    ColumnDelimiter.COMMA,
    ColumnDelimiter.PIPE,
    ColumnDelimiter.SEMICOLON,
    ColumnDelimiter.TAB,
]


@pytest.fixture
def simple_csv_data():
    return "id,name\n1,Alice\n2,Bob\n3,Charlie\n"


@pytest.fixture
def simple_csv_dict_data():
    return [
        {"id": "1", "name": "Alice"},
        {"id": "2", "name": "Bob"},
        {"id": "3", "name": "Charlie"},
    ]


def convert(data, line_ending, column_delimiter):
    return data.replace(",", _delimiter_char[column_delimiter]).replace(
        "\n", _line_ending_char[line_ending]
    )


def write_csv(tmp_path, data):
    path = tmp_path / "data.csv"
    path.write_bytes(data.encode("utf-8"))
    return str(path)


@pytest.mark.parametrize("quoting", QUOTINGS)
@pytest.mark.parametrize("line_ending", LINE_ENDINGS)
@pytest.mark.parametrize("column_delimiter", COLUMN_DELIMITERS)
@pytest.mark.parametrize("from_file", [True, False])
async def test_count_csv(
    tmp_path, simple_csv_data, quoting, line_ending, column_delimiter, from_file
):
    converted_data = convert(simple_csv_data, line_ending, column_delimiter)
    source = (
        {"filename": write_csv(tmp_path, converted_data)}
        if from_file
        else {"data": converted_data}
    )
    record_count = await _count_csv(
        **source,
        quoting=quoting,
        line_ending=line_ending,
        column_delimiter=column_delimiter,
        skip_header=True,
    )
    assert record_count == 3


@pytest.mark.parametrize("quoting", QUOTINGS)
@pytest.mark.parametrize("line_ending", LINE_ENDINGS)
@pytest.mark.parametrize("column_delimiter", COLUMN_DELIMITERS)
@pytest.mark.parametrize("from_file", [True, False])
async def test_split_csv(
    tmp_path,
    simple_csv_data,
    simple_csv_dict_data,
    quoting,
    line_ending,
    column_delimiter,
    from_file,
):
    converted_data = convert(simple_csv_data, line_ending, column_delimiter)
    source = (
        {"filename": write_csv(tmp_path, converted_data)}
        if from_file
        else {"records": converted_data}
    )
    split_results = [
        chunk
        async for chunk in _split_csv(
            **source,
            quoting=quoting,
            line_ending=line_ending,
            column_delimiter=column_delimiter,
        )
    ]
    assert len(split_results) == 1
    assert sum(count for count, _ in split_results) == 3

    split_results = [
        chunk
        async for chunk in _split_csv(
            **source,
            max_records=1,
            quoting=quoting,
            line_ending=line_ending,
            column_delimiter=column_delimiter,
        )
    ]
    assert split_results == [
        (
            1,
            _convert_dict_to_csv(
                data=[record],
                line_ending=line_ending,
                column_delimiter=column_delimiter,
                quoting=quoting,
                sort_keys=True,
            ),
        )
        for record in simple_csv_dict_data
    ]


@pytest.mark.parametrize("line_ending", LINE_ENDINGS)
async def test_split_csv_file_with_multiline_field(tmp_path, line_ending):
    records = [
        {"Id": "1", "Description": "first line\nsecond line"},
        {"Id": "2", "Description": 'has "quotes", and a comma'},
        {"Id": "3", "Description": "plain"},
    ]
    data = _convert_dict_to_csv(records, line_ending=line_ending, sort_keys=True)
    filename = write_csv(tmp_path, data)

    assert await _count_csv(filename=filename, skip_header=True) == 3

    split_results = [
        chunk
        async for chunk in _split_csv(
            filename=filename, max_records=1, line_ending=line_ending
        )
    ]
    assert [count for count, _ in split_results] == [1, 1, 1]
    assert [chunk for _, chunk in split_results] == [
        _convert_dict_to_csv([record], line_ending=line_ending, sort_keys=True)
        for record in records
    ]


async def test_get_csv_fieldnames(tmp_path):
    filename = write_csv(tmp_path, "Id|Name\n1|Alice\n")
    assert await _get_csv_fieldnames(
        filename=filename, column_delimiter=ColumnDelimiter.PIPE
    ) == ["Id", "Name"]
    assert await _get_csv_fieldnames(records=[{"Id": "1"}]) == ["Id"]
    with pytest.raises(ValueError):
        await _get_csv_fieldnames()
