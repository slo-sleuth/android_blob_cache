# Android Imgcache Files

__*Based on the analysis of Android 9 imgcache files found in the Android Gallery application*__

## Contents
- [Introduction](#Introduction)
- [File Format](#File-format)
  - [File Header](#File-Header)
  - [File Records](#File-Records)
- [parse_imgcache.py](#The-Parse_imgcache.py-Script)
  - [Usage](#Usage)
  - [Database Schema](#Database-schema)



## Introduction
Android caches thumbnails of media files in a compound file called `imgcache.0` or a variant thereof.  Imgcache files can be identified by their 4-byte signature and are the modern incarnation of the thumbcache in older Android versions.

Imgcache files are known to retain thumbnails of deleted images, and many commercial tools carve the thumbnails from the cache file as part of routine processing.  However, not all the tools recover the associated metadata that can be invaluable in an investigation.

## File Format

The file has a 4-byte signature, but no footer.

### File Header

|File Offset|Size|Value
|---|---|---
|0|4 bytes|0x108524BD

### File Records

Cached thumbnails are stored in a structured data format:

- record header
  - the last 4 byte of the header indicate the metadata + thumbnail size
- record metadata
  - undefined variable length
  - four or more plus sign delimited fields
    - Gallery app internal path
    - Unidentified integer
    - Original file path
    - Time stamp (undetermined if it is thumbnail creation or original file modification date)
    - Extra data, observed to be the Google user account name for encrypted media files
- JPEG thumbnail

The records are contiguous with no separators between them.

|Record offset|Length|Type|Description
|---|---|---|---
|0|4|Unk|Unknown
|4|4|Unk|Unknown
|8|4|Unk|Unknown
|12|4|Unk|Unknown
|16|4|uint32|Size of metadata + thumbnail
|20|varies|binary|metadata and thumbnail

The record metadata is plus sign ("+") delimited and encoded in UTF-16-LE or UTF-32-LE.  The UTF-32 encoding can end in a UTF-16-LE string (more that to come).  

**WARNING:** *There is no size flag to indicate the length of the metadata, and separating the fields using the fields blindly using the "+" separator is dangerous: Android file paths can and to include the plus sign.*

The structure of the record metadata if fairly consistent, but variations have been observed.

|Position|Type|Description
|---|---|---
|0|string|The Gallery application internal path
|1|integer|Unknown purpose
|2|string|The original file path
|3|integer|Unixepoch time stamp, original image modification date.
|4|string|Variably occuring field, observed to contain Google user name in encrypted media files

UTF-32-LE encoded metadata was observed to have a plus sign delimited, UTF-16-LE encoded string appended to the metadata.  The string was consistently `kar`.  The purpose of the string is not known.

The metadata is prepended to the thumbnail.  No values in the record header matched the metadata length, so the only reliable means to find the end of the metadata is to seek the jpeg signature.

## The parse_imgcache.py Script

The `parse_imgcache.py` script uses the information in the section above to identify and parse an Android imgcache file and write the content to SQLite.  Metadata and thumbnails are written to their own tables, but a view is provided joining the tables.

When the resulting database is viewed with [DB Browser for SQLite](https://sqlitebrowser.org/), the thumbnails are viewable in the Database Cell Editor (enable automatic mode adjustment two automatically switch from text to image viewer)

The "meta" table contains a "RawMeta" field with the original binary metadata for examination.  The 20-byte record header is not presently included in the output file.

### Usage

```
% python3 parse_imgcache.py -h
usage: parse_imgcache.py [-h] [-db] FILE

Extract thumbnails and file metadata from Android imgcache file.

positional arguments:
  FILE            imgcache file to parse

optional arguments:
  -h, --help      show this help message and exit
  -db, -database  Write to SQLite database (default)

Writes output to a SQLite database named after the cache file and to the same directory.  Future versions will export thumbnails to a directory and create a CSV.
```

### Database Schema

```sql
CREATE TABLE meta (
    Offset INTEGER PRIMARY KEY,
    AppPath TEXT,
    Unk INTEGER,
    FilePath TEXT,
    TimeStamp INTEGER,
    Extra TEXT,
    RawMeta BLOB
);

CREATE TABLE thumbnails (
    Offset INTEGER PRIMARY KEY,
    Thumbnail BLOB
);

CREATE VIEW files as
    select
        meta.offset as RecordOffset,
        datetime(TimeStamp, 'unixepoch', 'localtime') as LocalTime,
        FilePath,
        Extra,
        AppPath,
        Thumbnail
    from meta
    left join thumbnails on meta.offset = thumbnails.offset;
```
