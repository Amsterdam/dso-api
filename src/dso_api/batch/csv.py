import csv
import datetime
import logging
import os
from contextlib import contextmanager

log = logging.getLogger(__name__)

GOB_CSV_ENCODING = "utf-8-sig"


def iso_datum_tijd(s):
    if not s:
        return None
    if len(s) > 10:
        pat = "%Y-%m-%dT%H:%M:%S"
    else:
        pat = "%Y-%m-%d"

    return datetime.datetime.strptime(s, pat).date()


def get_janee_boolean(value):
    return True if value == "J" else False if value == "N" else None


def datum_geldig(start, eind):
    return eind is None or start <= eind


def _wrap_row(r, headers):
    return dict(zip(headers, r))


@contextmanager
def _context_reader(
    source,
    quotechar=None,
    quoting=csv.QUOTE_NONE,
    with_header=True,
    encoding=GOB_CSV_ENCODING,
):

    if not os.path.exists(source):
        raise ValueError("File not found: {}".format(source))

    with open(source, encoding=encoding) as f:
        rows = csv.reader(f, delimiter=";", quotechar=quotechar, quoting=quoting)

        if with_header:
            headers = next(rows)
            yield (_wrap_row(r, headers) for r in rows)
        else:
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
            log.error("Could not process row while parsing %s", source_path)
            for k, v in r.items():
                log.error("%s: '%s'", k, v)
            raise

    return result


def process_csv(
    path,
    file_name,
    process_row_callback,
    with_header=True,
    quotechar='"',
    source=None,
    encoding="utf-8-sig",
    max_rows=None,
):

    if not source:
        source = os.path.join(path, file_name)

    cb = logging_callback(source, process_row_callback)

    with _context_reader(
        source,
        quotechar=quotechar,
        quoting=csv.QUOTE_MINIMAL,
        with_header=with_header,
        encoding=encoding,
    ) as rows:
        count = 0
        for row in rows:
            count += 1
            if max_rows and count > max_rows:
                break
            result = cb(row)
            if result:
                yield result
