#!/usr/bin/env python3

import argparse
import re
import sqlite3
import sys
from struct import unpack

# groups 1, 2 in the follow expression are optional because there are instances
# when the original file path is not present in the record
meta_re = re.compile('(.+?)\+(\d)?\+?(.+?\.\w{3,4})?\+?(\d{10})\+?(.+){0,}')

def detect_codec(data: bytes, codecs: tuple=(('utf-32-le', 4), 
    ('utf-16-le', 2))) -> tuple:
    """Attempt to detect codec of data.  Returns codec string and corresponding 
    code point length."""
    
    for values in codecs:
        codec, cp_len = values
        try:
            data.decode(codec)
            return codec, cp_len
        except:
            pass
    print(f'Codec detection error: {data}')
    sys.exit(1)

def construct_db(db: str):
    """Build empty database 'db'."""

    con = sqlite3.connect(db)
    c = con.cursor()
    c.executescript('''
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
    ''')
    con.commit()
    return con

def main():

    parser = argparse.ArgumentParser(description='Extract thumbnails and file \
        metadata from Android imgcache file.', epilog='Writes output to a \
        SQLite database named after the cache file and to the same directory. \
        Future versions will export thumbnails to a directory and create a \
        CSV.')
    parser.add_argument('FILE', help="imgcache file to parse")
    parser.add_argument('-db', "-database", action='store_true', default=True,
        help='Write to SQLite database (default)')

    args = parser.parse_args()

    if args.db:
        db_name = args.FILE + '.sqlite'
        db = construct_db(db_name)
        c = db.cursor()

    with open(args.FILE, 'rb') as f:

        # Determine file size to gracefully exit loop
        fsize = f.seek(0, 2)
        f.seek(0)
        
        # Read file header, quit if wrong file type provided
        file_header = f.read(4)
        if not file_header == b'\x10\x85\x24\xBD':
            print("Error: Not an imgcache file")
            sys.exit(1)

        # Read each record, structured as 20 byte header, variable length string
        # with fields separated by '+', followed by thumbnail image.
        offset = 0
        while True:
            offset = f.tell()

            # Quit at EOF
            if offset == fsize:
                break

            # Read 20 byte record header, last 4 bytes are the file metadata + 
            # thumbnail size
            rec_header = unpack('<5I', f.read(20))
            
            # Split metadata from thumbnail data using thumbnail header.  
            # Metadata is variable length and has no size indicator.
            thumbnail_header = b'\xff\xd8\xff\xe0'
            metadata, thumbnail = f.read(rec_header[4]).split(thumbnail_header)
            thumbnail = thumbnail_header + thumbnail

            # Metadata is plus sign delimited (causing issues with paths 
            # including # plus signs).  It can be encoded utf-16-le, 
            # utf-32-le.  All utf-32 strings are ended with a utf-16 '+kar' 
            # string which is ignored in decoding.
            codec, cp_len = detect_codec(metadata[:4])
            decoded_meta = metadata.decode(codec, 'ignore')
            try:
                meta_list = meta_re.findall(decoded_meta)[0]
            except IndexError as e:
                print(f'Metadata in record at Offset: {offset} not understood, adding RawData only')
                meta_list = [None] * 5

            if args.db:  # Default for now, but CSV will be a future option
                apath, unk, fpath, ts, xtra = meta_list
                if not xtra:
                    xtra = None
                c.execute('''INSERT INTO meta (Offset, AppPath, Unk, FilePath,
                    TimeStamp, Extra, RawMeta) VALUES (?,?,?,?,?,?,?);''', 
                    (offset, apath, unk, fpath, ts, xtra, metadata))
                c.execute('''INSERT INTO thumbnails (Offset, Thumbnail) VALUES 
                    (?,?);''', (offset, thumbnail))

            else:
                print(offset, meta_list, thumbnail[:4])
        if args.db:
            db.commit()

if __name__ == "__main__":
    main()
    sys.exit(0)