#!/bin/bash
# Description: Connect/Disconnect Bluetooth

DEVICES=(
    "38:11:67:F0:21:57"  # Alesis Multimix
    "CB:4C:49:6C:ED:04"  # CMO-3110
)
RECONNECT_INTERVAL=15

reconnect_loop() {
    while true; do
        sleep "$RECONNECT_INTERVAL"
        for mac in "${DEVICES[@]}"; do
            if ! bluetoothctl info "$mac" 2>/dev/null | grep -q "Connected: yes"; then
                bluetoothctl connect "$mac" >/dev/null 2>&1
            fi
        done
    done
}

if [[ "$1" == "--monitor" ]]; then
    rfkill unblock bluetooth
    sleep 1
    bluetoothctl power on >/dev/null 2>&1
    sleep 2
    reconnect_loop
    exit 0
fi

bluetooth_status=$(service bluetooth status | grep -o "Active: active (running)")

if [[ "$bluetooth_status" == "Active: active (running)" ]]; then
    echo "Turning off Bluetooth..."
    rfkill block bluetooth
    sleep 2
    sudo systemctl stop bluetooth
    pkill blueman
else
    echo "Turning on Bluetooth..."
    rfkill unblock bluetooth
    sleep 2
    sudo systemctl start bluetooth
    sleep 2
    bluetoothctl power on
    reconnect_loop &
    LOOP_PID=$!
    trap "kill $LOOP_PID 2>/dev/null" EXIT
    blueman-manager
fi
