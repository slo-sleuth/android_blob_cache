# Android Imgcache Files

***Based on the analysis of Android 9 imgcache files found in the Android
Gallery application***

## Contents
- [Android Imgcache Files](#android-imgcache-files)
  - [Contents](#contents)
  - [Introduction](#introduction)
  - [File Format](#file-format)
    - [File Header](#file-header)
    - [File Records](#file-records)
  - [The parse_imgcache.py Script](#the-parse_imgcachepy-script)
    - [Usage](#usage)
    - [Database Schema](#database-schema)



## Introduction
Android caches thumbnails of media files in a compound file called `imgcache.0`
or a variant thereof.  Imgcache files can be identified by their 4-byte
signature and are the modern incarnation of the thumbcache in older Android
versions.

Imgcache files are known to retain thumbnails of deleted images, and many
commercial tools carve the thumbnails from the cache file as part of routine
processing.  However, not all the tools recover the associated metadata that can
be invaluable in an investigation.

## File Format

The file has a 4-byte signature, but no footer.

### File Header

| File Offset | Size    | Value      |
| ----------- | ------- | ---------- |
| 0           | 4 bytes | 0x108524BD |

### File Records

Cached thumbnails are stored in a structured data format:

- Record header (20 bytes)
- Payload (variable length)
  - record metadata
  - JPEG thumbnail

The records are contiguous with no buffers.

| Record offset | Length | Type   | Description                   |
| ------------- | ------ | ------ | ----------------------------- |
| 0             | 4      | Unk    | Unknown                       |
| 4             | 4      | Unk    | Unknown                       |
| 8             | 4      | Unk    | Unknown                       |
| 12            | 4      | uint32 | File offset of current record |
| 16            | 4      | uint32 | Size of payload               |
| 20            | varies | binary | Payload                       |

Thus, the next record offset can be calculated by:
- current record offset + record header length (20) + payload length

The record metadata is plus sign ("+") delimited and encoded in UTF-16-LE or
UTF-32-LE.  The UTF-32 encoding can end in a UTF-16-LE string (more that to
come).  

> **WARNING:** There is no size flag to indicate the length of the metadata, and
> separating the fields blindly using the "+" separator is dangerous: Android
> file paths can and do include the plus sign.

The structure of the record metadata is fairly consistent, but variations have
been observed.

| Position | Type    | Description                                                                             |
| -------- | ------- | --------------------------------------------------------------------------------------- |
| 0        | string  | The Gallery application internal path                                                   |
| 1        | integer | Unknown purpose (not always present)                                                    |
| 2        | string  | The original file path (not always present)                                             |
| 3        | integer | Unixepoch time stamp, original image modification date.                                 |
| 4        | string  | Variably occurring field, observed to contain Google user name in encrypted media files |

NOTE: UTF-32-LE encoded metadata was observed to have a plus sign delimited,
UTF-16-LE encoded string appended to the metadata.  The string was consistently
`kar`.  The purpose of the string is not known.  Conveniently, while the
original file maybe encrypted, the thumbnail in the imgcache is not.

The metadata is pre-pended to the thumbnail.  The metadata length is undefined,
so the only reliable means to find the end of the metadata is to seek the jpeg
thumbnail signature.

## The parse_imgcache.py Script

The `parse_imgcache.py` script uses the information in the section above to
identify and parse an Android imgcache file and write the content to SQLite.
Record headers and payload data are written to their own tables, and a view is provided
with UTC and local date stamp interpretations.

When the resulting database is viewed with [DB Browser for
SQLite](https://sqlitebrowser.org/), the thumbnails are viewable in the Database
Cell Editor (enable automatic mode adjustment two automatically switch from text
to image viewer)  Each table includes a raw data blob to validate the table
values.  

A new sanitize option has been added to allow creation of an imgcache file free
of thumbnail content so that the file can be shared with others without
transmitting undesirable or unlawful thumbnail content.  This is useful for
sharing imgcache files with the program author to improve output.

### Usage

```
$ python3 Projects/android_imgcache/parse_imgcache.py -h                          1 ⨯
usage: parse_imgcache.py [-h] [-d] [-s] FILE

Extracts thumbnails and file metadata from Android imgcache files.

positional arguments:
  FILE            imgcache file to parse

optional arguments:
  -h, --help      show this help message and exit
  -d, --database  Write to SQLite database (default)
  -s, --sanitize  Write an imgcache file with thumbnails overwritten.

Writes output to a SQLite database named after the cache file and to the current
working directory. The sanitize option is useful for sharing imgcache metadata without
disclosing the content of the thumbnail images. Future versions may export thumbnails
to a directory and create a CSV.
```

### Database Schema

```sql
CREATE TABLE payload (
    Offset INTEGER PRIMARY KEY,
    InternalPath TEXT,
    Unk INTEGER,
    OriginalFilePath TEXT,
    TimeStamp INTEGER,
    Extra TEXT,
    Thumbnail BLOB,
    RawMetadata BLOB
);

CREATE TABLE record_header (
    Offset INTEGER PRIMARY KEY,
    val1 INTEGER,
    val2 INTEGER,
    val3 INTEGER,
    RecordOffset INTEGER,
    PayloadLength INTEGER,
    RawRecordHeader BLOB
);

CREATE VIEW Parsed_Records as
    select
        payload.offset as RecordOffset,
        datetime(TimeStamp, 'unixepoch') as UTC,
        datetime(TimeStamp, 'unixepoch', 'localtime') as LocalTime,
        OriginalFilePath,
        Extra,
        InternalPath,
        Thumbnail
    from payload;
```
