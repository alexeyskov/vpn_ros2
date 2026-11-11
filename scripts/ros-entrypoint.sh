#!/bin/bash
set -eo pipefail
source /opt/ros/jazzy/setup.bash
python3 /app/scripts/configure_dds.py
if [[ $# -eq 0 ]]; then
    echo 'Specify sender.py or receiver.py' >&2
    exit 2
fi
case "$1" in
    sender.py|receiver.py) exec python3 "/app/scripts/$1" "${@:2}" ;;
    *) exec "$@" ;;
esac
