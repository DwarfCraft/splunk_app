'''
Wrapper Script for the JMX Modular Input

Copyright (C) 2012 Splunk, Inc.
All Rights Reserved

Because Splunk can't directly invoke Java , we use this python wrapper script that
simply proxys through to the Java program
'''
from __future__ import print_function

import import_declare_test
import java_const
import os
import signal
import sys
from subprocess import Popen, PIPE

try:
    from task_monitor import update_inputs
except:
    pass
import xml.etree.ElementTree as ET

from solnlib import utils


def checkForRunningProcess():
    if os.path.isfile(java_const.PID_FILE_PATH):
        with open(java_const.PID_FILE_PATH, "r") as f:
            old_pid = f.read()
        try:
            os.kill(int(old_pid), signal.SIGKILL)
        except:
            pass
        os.remove(java_const.PID_FILE_PATH)


def removePidFile():
    os.remove(java_const.PID_FILE_PATH)


def createPidFile(process):
    with open(java_const.PID_FILE_PATH, 'w') as f:
        f.write(str(process.pid))


def usage():
    print("usage: %s [--scheme|--validate-arguments]")
    sys.exit(2)


def loadXML():
    xml_str = sys.stdin.read()
    sys.argv.append(xml_str)
    return xml_str


def monitor_tasks(process, token):
    import time

    while process.poll() is None:
        if update_inputs:
            update_inputs(java_const.CONFIG_HOME[len(java_const.SPLUNK_HOME) + 1:], token)
        time.sleep(60)


def setup_signal_handler(process):
    """
    Setup signal handlers
    @jmx_op_invoker: jmx_op_invoker.JMXOpInvoker instance
    @timer_queue: ta_util2.timer_queue.TimerQueue
    """

    def _handle_exit(signum, frame):
        process.kill()

    utils.handle_teardown_signals(_handle_exit)


if __name__ == '__main__':

    if len(sys.argv) > 1:
        if sys.argv[1] == "--scheme":
            pass
        elif sys.argv[1] == "--validate-arguments":
            loadXML()
        else:
            usage()

        java_const.JAVA_MAIN_ARGS.extend(sys.argv[1:])
        process = Popen(java_const.JAVA_MAIN_ARGS)
        process.wait()
        sys.exit(process.returncode)
    else:
        # checkForRunningProcess()
        xml_str = loadXML()
        token = ET.fromstring(xml_str).find('session_key').text
        # JAVA_MAIN_ARGS.extend(sys.argv[1:])
        if sys.version_info > (3,):
            process = Popen(java_const.JAVA_MAIN_ARGS, stdin=PIPE, text=True)
        else:
            process = Popen(java_const.JAVA_MAIN_ARGS, stdin=PIPE)
        setup_signal_handler(process)

        process.stdin.write((xml_str.replace('\n', '').replace('\r', '') + '\n'))
        process.stdin.flush()

        # createPidFile(process)
        monitor_tasks(process, token)
        # removePidFile()
