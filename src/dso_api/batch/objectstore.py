import logging
import os
import time
from functools import lru_cache
from pathlib import Path

from swiftclient.client import Connection

from dso_api import settings

log = logging.getLogger(__name__)

logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("swiftclient").setLevel(logging.WARNING)

container = os.getenv("GOB_OBJECTSTORE_ENV", "productie")

connection = {
    "auth_version": "2.0",
    "authurl": "https://identity.stack.cloudvps.com/v2.0",
    "user": "GOB_user",
    "key": os.getenv("GOB_OBJECTSTORE_PASSWORD", "insecure"),
    "tenant_name": "BGE000081_GOB",
    "os_options": {
        "tenant_id": "2ede4a78773e453db73f52500ef748e5",
        "region_name": "NL",
    },
}


@lru_cache(maxsize=None)
def get_conn():
    assert os.getenv("GOB_OBJECTSTORE_PASSWORD")
    return Connection(**connection)


def file_exists(target):
    target = Path(target)
    return target.is_file()


def download_file(
    file_path, target_path=None, target_root=settings.DATA_DIR, file_last_modified=None,
):
    path = file_path.split("/")

    file_name = path[-1]
    log.info(f"Create file {file_name} in {target_root}")
    file_name = path[-1]

    if target_path:
        newfilename = "{}/{}".format(target_root, target_path)
    else:
        newfilename = "{}/{}".format(target_root, file_name)

    if file_exists(newfilename):
        st = os.stat(newfilename)
        age_seconds = time.time() - st.st_mtime
        if age_seconds < 24 * 60 * 60:  # If not older then a day skip download
            log.debug("Skipped file exists: %s", newfilename)
        return

    with open(newfilename, "wb") as newfile:
        data = get_conn().get_object(container, file_path)[1]
        newfile.write(data)
    if file_last_modified:
        epoch_modified = file_last_modified.timestamp()
        os.utime(newfilename, (epoch_modified, epoch_modified))
