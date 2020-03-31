import csv
from datetime import datetime, date
import logging
import os
from contextlib import contextmanager

log = logging.getLogger(__name__)

GOB_CSV_ENCODING = "utf-8-sig"


def parse_date_time(s):
    if not s:
        return None
    if len(s) > 10:
        return datetime.fromisoformat(s)
    else:
        return date.fromisoformat(s)


def parse_yesno_boolean(value):
    return True if value == "J" or value == "Y" else False if value == "N" else None


def is_valid_date_range(start, end):
    # Temporarily reject ranges with same value for start and end
    # return end is None or start <= end
    return end is None or start < end


@contextmanager
def _context_reader(
    source, quotechar=None, quoting=csv.QUOTE_NONE, encoding=GOB_CSV_ENCODING,
):
    with open(source, encoding=encoding) as f:
        rows = csv.DictReader(f, delimiter=";", quotechar=quotechar, quoting=quoting)
        yield (r for r in rows)


def logging_callback(source_path, original_callback):
    """
    Provides callback function that logs errors on failure

    Because the csv files provided contained all kinds of weird
    data..
    """

    def result(r):
        try:
            return original_callback(r)
        except:  # noqa we reraise the exception.
            log.error(f"Could not process row while parsing {source_path}: {r}")
            raise

    return result


def process_csv(
    path,
    file_name,
    process_row_callback,
    quotechar='"',
    encoding="utf-8-sig",
    max_rows=None,
):
    source = os.path.join(path, file_name)
    cb = logging_callback(source, process_row_callback)
    with _context_reader(
        source, quotechar=quotechar, quoting=csv.QUOTE_MINIMAL, encoding=encoding,
    ) as rows:
        count = 0
        for row in rows:
            count += 1
            if max_rows and count > max_rows:
                break
            result = cb(row)
            if result:
                yield result
