#!/bin/bash

SOURCE_DIR=`dirname $(readlink -f "$0")`
TARGET_DIR="/opt/splunk/etc/deployment-apps"

cp -R ${SOURCE_DIR}/* ${TARGET_DIR}
rm "${TARGET_DIR}/README.md"
rm "${TARGET_DIR}/promote.sh"
chown -R splunk.splunk "${TARGET_DIR}/*"


