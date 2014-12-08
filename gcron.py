#! /usr/bin/env python2

from __future__ import print_function
import os
import os.path
import sys
import time
import logging
import math

log = logging.getLogger("gcron-logger")
start_time = 0.0


def initLogger():
    import logging.handlers

    log.setLevel(logging.DEBUG)
    logFormat = "[%(asctime)s %(filename)s:%(lineno)s %(funcName)s] "\
        "%(levelname)s %(message)s"
    formatter = logging.Formatter(logFormat)

    sh = logging.handlers.SysLogHandler()
    sh.setLevel(logging.ERROR)
    sh.setFormatter(formatter)

    fh = logging.FileHandler("/var/log/gcron.log")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)

    log.addHandler(sh)
    log.addHandler(fh)


def takeSnap(volname=""):
    success = True
    if volname == "":
        log.debug("No volname given")
        return False

    import subprocess
    import shlex

    timeStr = time.strftime("%Y%m%d%H%M%S")
    cli = "/usr/sbin/gluster snapshot create %s-snapshot-%s %s" % \
        (volname, timeStr, volname)
    log.debug("Running command '%s'", cli)

    p = subprocess.Popen(shlex.split(cli), stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)
    out, err = p.communicate()
    rv = p.returncode

    log.debug("Command '%s' returned '%d'", cli, rv)

    if rv:
        log.error("Snapshot of %s failed", volname)
        log.error("Command output:")
        log.error(err)
        success = False
    else:
        log.info("Snapshot of %s successful", volname)

    return success


def doJob(name, lockFile, jobFunc, options):
    import fcntl

    success = True
    try:
        f = os.open(lockFile, os.O_RDWR | os.O_NONBLOCK)
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            mtime = os.path.getmtime(lockFile)
            global start_time
            log.debug("%s last modified at %s", lockFile, time.ctime(mtime))
            if mtime < start_time:
                log.debug("Processing job %s", name)
                if jobFunc(options):
                    log.info("Job %s succeeded", name)
                else:
                    log.error("Job %s failed", name)
                    success = False
                os.utime(lockFile, None)
            else:
                log.info("Job %s has been processed already", name)
            fcntl.flock(f, fcntl.LOCK_UN)
        except IOError as err:
            log.info("Job %s is being processed by another agent", name)
        os.close(f)
    except IOError as err:
        log.debug("Failed to open lock file %s : %s", lockFile, err.message)
        log.error("Failed to process job %s", name)
        success = False

    return success


def main():
    initLogger()
    global start_time

# Flooring, to round the time to seconds remove extra precision information
# Required because the extra precision could cause some jobs to be rerun.
    start_time = math.floor(time.time())

    period = os.path.basename(sys.argv[0])

    log.info("%s jobs agent started at %s", period, time.ctime(start_time))

    schedule_dir = "/mnt/shared/" + period
    log.debug("Getting scheduled jobs from %s", schedule_dir)

    jobs = [file for file in os.listdir(schedule_dir)
            if os.path.isfile(os.path.join(schedule_dir, file))]
    jobs.sort()

    log.info("Found %d jobs in %s", len(jobs), schedule_dir)

    for entry in jobs:
        log.debug("Processing job: %s", entry)
        lockFile = os.path.join(schedule_dir, entry)
        doJob("Snapshot-"+entry, lockFile, takeSnap, entry)


if __name__ == "__main__":
    main()
