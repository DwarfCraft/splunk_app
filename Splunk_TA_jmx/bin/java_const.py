import os
import sys

JAVA_MAIN_CLASS = 'com.splunk.jmx.JMXModularInputV3'
JAVA_SERVER_VALIDATION_CLASS = 'com.splunk.jmx.ServerConfigValidator'
PARENT = os.path.sep + os.path.pardir
MODINPUT_PATH = os.path.abspath(__file__ + PARENT + PARENT)
MODINPUT_NAME = os.path.basename(MODINPUT_PATH)  # 'Splunk_TA_jmx'

# Set to True to use the MX4J JMX implementation
# USE_MX4J = True

# Set to True to test SSL
TEST_SSL = True
# TEST_SSL=False

# Adjust these variables to boost/shrink JVM heap size
MIN_HEAP = "64m"
MAX_HEAP = "128m"

# Create Java Args
sep = os.path.sep
psep = os.pathsep
if 'JAVA_HOME' not in os.environ:
    JAVA_EXECUTABLE = 'java'
else:
    JAVA_EXECUTABLE = sep.join([os.environ['JAVA_HOME'], 'bin', 'java'])

SPLUNK_HOME = os.environ['SPLUNK_HOME']
MODINPUT_HOME = sep.join([SPLUNK_HOME, 'etc', 'apps', MODINPUT_NAME])
CONFIG_HOME = sep.join([MODINPUT_HOME, 'local', 'config'])
CLASSPATH = sep.join([MODINPUT_HOME, 'bin', 'lib', '*'])

if not os.path.exists(CONFIG_HOME):
    os.makedirs(CONFIG_HOME)

if sys.platform == 'win32':
    CLASSPATH += psep + sep.join([MODINPUT_HOME, 'bin', 'lib', 'win', '*'])
else:
    CLASSPATH += psep + sep.join([MODINPUT_HOME, 'bin', 'lib', 'lin', '*'])


JAVA_COMMON_ARGS = [JAVA_EXECUTABLE, "-classpath", CLASSPATH, "-Dconfighome=" + CONFIG_HOME,
                    "-Dsplunkhome=" + SPLUNK_HOME]
JAVA_MAIN_ARGS = JAVA_COMMON_ARGS + [JAVA_MAIN_CLASS]
JAVA_SERVER_VALIDATION_ARGS = JAVA_COMMON_ARGS + [JAVA_SERVER_VALIDATION_CLASS]

if TEST_SSL:
    TEST_SSL_ARGS = "-Djavax.net.ssl.trustStore=" + SPLUNK_HOME + "/etc/apps/Splunk_TA_jmx/bin/mx4j.ks"
    JAVA_MAIN_ARGS.insert(-1, TEST_SSL_ARGS)
    JAVA_SERVER_VALIDATION_ARGS.insert(-1, TEST_SSL_ARGS)

PID_FILE_PATH = MODINPUT_HOME + os.path.sep + MODINPUT_NAME + ".pid"
