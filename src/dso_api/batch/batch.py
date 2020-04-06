import gc
import logging
import time

log = logging.getLogger(__name__)

BATCH_SIZE = 50000


class BasicJob:
    """Interface for jobs"""

    name = None

    def tasks(self) -> list:
        pass


def execute(job: BasicJob):
    log.info("Starting job: %s [%s]", job.name, job.__class__.__name__)

    for task in job.tasks():
        _execute_task(task)

    log.info("Finished job: %s: [%s]", job.name, job.__class__.__name__)


def _execute_task(task):

    if callable(task):
        task_name = task.__name__
        execute_func = task
    else:
        execute_func = task.execute
        task_name = task.__class__.__name__

    log.debug("Starting task: %s", task_name)

    execute_func()


class BasicTask:
    """
    Abstract task that splits execution into three parts:

    * ``before``
    * ``process``
    * ``after``

    """

    name = "Basic Task"
    count = 0
    prev_time = time.time()

    def execute(self):
        self.before()
        self.process()
        self.after()
        gc.collect()

    def log_progress(self):
        self.count += 1
        now_time = time.time()
        if now_time - self.prev_time > 10.0:  # Report every 10 seconds
            self.prev_time = now_time
            log.debug(f"{self.name} processed {self.count}...")

    def before(self):
        pass

    def after(self):
        pass

    def process(self):
        pass
