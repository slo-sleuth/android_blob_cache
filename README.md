# Android Gallery BlobCache Files

***Based on the analysis of Android 9 and 10 `imgcache` files found in the
Android Gallery application***

## Contents
- [Android Gallery BlobCache Files](#android-gallery-blobcache-files)
  - [Contents](#contents)
  - [Introduction](#introduction)
  - [Index File Format](#index-file-format)
  - [Data File Format](#data-file-format)
    - [File Header](#file-header)
    - [File Blobs](#file-blobs)
  - [The parse_blob_cache.py Script](#the-parse_blob_cachepy-script)
    - [Usage](#usage)
    - [Database Schema](#database-schema)

## Introduction
Android caches thumbnails of media files in a compound file called known as a
[*blob cache*](https://cs.android.com/android/platform/superproject/+/master:packages/apps/Gallery2/gallerycommon/src/com/android/gallery3d/common/BlobCache.java).
Blob caches are map 64-bit keys to byte arrays and actually consist three files:
an index file and two data files.  One data file is used at a time and new
entries are appended to the active file until it reaches its size limit.  The
inactive file is swapped with the previous file and truncated (old date is
deleted) before new entries are added.  Blob caches are the modern incarnation of the
thumbcache in older Android versions.

Blob cache data files contain jpeg thumbnails of cached media files making them
of interest to forensic examiners.  Thumbnails will persist even after the
source file is deleted or moved.  While some commercial tools carve the
thumbnails, they do not parse the associated metadata, and thus this project was
born.

Data files are named a variant of `imgcache` (e.g., cloudimgcache, imgcache,
screen_imgcache, and the not so obvious rev_geocoding), and files can be
identified by their 4-byte signature.  They have numbered extensions, `.0` and
`.1`.  The index file, unsurprisingly, adopts the `.idx` extension.  Thus, a
complete blob cache file set will have the form:

```
cloudimgcache.0
cloudimgcache.1
cloudimgcache.idx
```

## Index File Format

The index file format (all integers are stored little-endian):

| offset | type  | Value                      | Description                                             |
| ------ | ----- | -------------------------- | ------------------------------------------------------- |
| 0      |       | Magic number               | 0x303027B3                                              |
| 4      | int32 | MaxEntries                 | Max number of hash entries per region.                  |
| 8      | int32 | MaxBytes                   | Max number of data bytes per region (including header). |
| 12     | int32 | ActiveRegion               | The active growing region: 0 or 1.                      |
| 16     | int32 | ActiveEntries              | The number of hash entries used in the active region.   |
| 20     | int32 | ActiveBytes                | The number of data bytes used in the active region.     |
| 24     | int32 | Version                    | Version number.                                         |
| 28     | int32 | Checksum                   | of [0..28).                                             |
| 32     |       | Hash entries for region 0. | The size is X = (12 * MaxEntries bytes).                |
| 32 + X |       | Hash entries for region 1. | The size is also X.                                     |

This project does not currently process the blob cache index.

## Data File Format

The file has a 4-byte signature, but no footer.

### File Header

| File Offset | Size    | Value      |
| ----------- | ------- | ---------- |
| 0           | 4 bytes | 0x108524BD |

### File Blobs

Cached thumbnails are stored in "blobs" in a structured data format:

- Blob header (20 bytes)
- Blob (variable length)
  - record metadata
  - JPEG thumbnail

The records are contiguous with no buffers.  The 20 bytes are organized as follows:

| Record offset | Type   | Description                         |
| ------------- | ------ | ----------------------------------- |
| 0             | binary | Key                                 |
| 8             | int32  | Checksum                            |
| 12            | int32  | blob offset                         |
| 16            | int32  | blob size (bytes)                   |
| 20            | binary | blob content (metadata + thumbnail) |

Thus, the next blob offset can be calculated by:
- current blob offset + blob header length (20b) + blob length

The blob metadata is plus sign ("+") delimited and encoded in UTF-16-LE or
UTF-32-LE.  The UTF-32 encoding can end in a UTF-16-LE string (more on that to
come).  

> **WARNING:** There is no size flag to indicate the length of the metadata, and
> separating the fields blindly using the "+" separator is dangerous: Android
> file paths can and do include the plus sign.

The structure of the record metadata is fairly consistent, but variations have
been observed.

| Position | Type    | Description                                                                              |
| -------- | ------- | ---------------------------------------------------------------------------------------- |
| 0        | string  | The Gallery application internal path                                                    |
| 1        | integer | Unknown purpose (not always present), possibly defines the number of remaining positions |
| 2        | string  | The original file path (not always present)                                              |
| 3        | integer | Unixepoch time stamp, original image modification date.                                  |
| 4        | string  | Variably occurring field, observed to contain Google user name in encrypted media files  |

> **NOTE**: UTF-32-LE encoded metadata was observed to have a plus sign delimited,
> UTF-16-LE encoded string appended to the metadata.  The string was
> consistently `kar`.  The purpose of the string is not known.  Conveniently,
> while the original file maybe encrypted, the thumbnail in the blob cache is not.

The metadata is pre-pended to the thumbnail.  Because the metadata length is
undefined, the only reliable means to find the end of the metadata is to seek
the jpeg thumbnail signature.

## The parse_blob_cache.py Script

The `parse_blob_cache.py` script uses the information in the section above to
identify and parse an Android blob cache file and write the content to SQLite.
Record headers and payload data are written to their own tables, and a view is
provided with UTC and local date stamp interpretations.

When the resulting database is viewed with [DB Browser for
SQLite](https://sqlitebrowser.org/), the thumbnails are viewable in the Database
Cell Editor (enable automatic mode adjustment two automatically switch from text
to image viewer)  Each table includes a raw data blob to validate the table
values.  

A new sanitize option has been added to allow creation of an blob cache file free
of thumbnail content so that the file can be shared with others without
transmitting undesirable or unlawful thumbnail content.  This is useful for
sharing blob cache files with the program author to improve output.

### Usage

```
$ python3 parse_blob_cache.py -h
usage: parse_blob_cache.py [-h] [-d] [-s] FILE

Extracts thumbnails and file metadata from Android blob cache files.

positional arguments:
  FILE            blob cache file to parse

optional arguments:
  -h, --help      show this help message and exit
  -d, --database  Write to SQLite database (default)
  -s, --sanitize  Write an blobcache file with thumbnails overwritten.

Writes output to a SQLite database named after the cache file and to the current
working directory. The sanitize option is useful for sharing blob cache metadata without
disclosing the content of the thumbnail images. Future versions may export thumbnails
to a directory and create a CSV.
```

### Database Schema

```sql
CREATE TABLE blob (
    Offset INTEGER PRIMARY KEY,
    InternalPath TEXT,
    Unk INTEGER,
    OriginalFilePath TEXT,
    TimeStamp INTEGER,
    Extra TEXT,
    Thumbnail BLOB,
    RawMetadata BLOB
);

CREATE TABLE blob_header (
    Offset INTEGER PRIMARY KEY,
    Key BLOB,
    Checksum INTEGER,
    BlobOffset INTEGER,
    BlobLength INTEGER,
    RawBlobHeader BLOB
);

CREATE VIEW Parsed_Blob_Cache AS
    SELECT
        blob.offset AS RecordOffset,
        CASE 
            WHEN length(TimeStamp) == 13 THEN datetime(TimeStamp/1000, 'unixepoch')
            ELSE datetime(TimeStamp, 'unixepoch')
        END as UTC,
        CASE 
            WHEN length(TimeStamp) == 13 THEN datetime(TimeStamp/1000, 'unixepoch', 'localtime')
            ELSE datetime(TimeStamp, 'unixepoch', 'localtime') 
        END as LocalTime,
        OriginalFilePath,
        Extra,
        InternalPath,
        Thumbnail
    FROM blob;
```
