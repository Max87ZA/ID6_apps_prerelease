#!/usr/bin/env python3
"""Parked test of the exhaust flap override on the engine ECU (address 12).

ACTIVE COMMAND: unlike the probe tools this drives an actuator. It sends only the three fixed
requests below (input/output control on identifier 60 FD) and always ends by returning control
to the ECU ("auto"), even if an earlier step fails.

Usage: flap_test.py <local ENET ip> <gateway ip> [seconds between steps]
"""
import socket
import struct
import sys
import time

STEPS = (
    ("open", bytes.fromhex("2f60fd0314fe")),
    ("close", bytes.fromhex("2f60fd032328")),
    ("auto", bytes.fromhex("2f60fd00")),
)
ECU = 0x12
NRC = {0x11: "service not supported", 0x12: "sub-function not supported", 0x13: "wrong length",
       0x22: "conditions not correct", 0x31: "request out of range", 0x33: "security access denied",
       0x7E: "sub-function not supported in this session", 0x7F: "service not supported in this session"}


def recv_exact(conn, length, deadline):
    data = bytearray()
    while len(data) < length:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError
        conn.settimeout(remaining)
        part = conn.recv(length - len(data))
        if not part:
            raise ConnectionError("gateway closed the connection")
        data.extend(part)
    return bytes(data)


def send(local, gateway, request):
    with socket.create_connection((gateway, 6801), timeout=3, source_address=(local, 0)) as conn:
        conn.sendall(struct.pack(">IHBB", len(request) + 2, 1, 0xF4, ECU) + request)
        deadline = time.monotonic() + 2
        while True:
            length, control = struct.unpack(">IH", recv_exact(conn, 6, deadline))
            payload = recv_exact(conn, length, deadline)
            if control == 0x12:
                conn.sendall(struct.pack(">IHBB", 2, 0x13, 0, 0xF4))
                continue
            if control != 1 or payload[:2] != bytes((ECU, 0xF4)):
                continue
            reply = payload[2:]
            if reply[:1] == bytes((request[0] + 0x40,)):
                return "accepted", reply.hex(" ")
            if len(reply) == 3 and reply[0] == 0x7F and reply[1] == request[0]:
                if reply[2] == 0x78:
                    deadline = time.monotonic() + 3
                    continue
                return "refused", f"NRC {reply[2]:02X} ({NRC.get(reply[2], 'unknown')})"


def main():
    local, gateway = sys.argv[1], sys.argv[2]
    pause = float(sys.argv[3]) if len(sys.argv) > 3 else 4
    only = sys.argv[4:]  # optionally just some steps, e.g. "auto"
    steps = [s for s in STEPS if not only or s[0] in only]
    try:
        for name, request in steps:
            try:
                outcome, detail = send(local, gateway, request)
            except (TimeoutError, OSError) as error:
                outcome, detail = "no reply", type(error).__name__
            print(f"{name:5s} {request.hex(' '):20s} -> {outcome}: {detail}", flush=True)
            if name != "auto":
                time.sleep(pause)
    finally:
        if not any(name == "auto" for name, _ in steps):
            try:
                print("auto  (safety)            ->", *send(local, gateway, STEPS[2][1]))
            except (TimeoutError, OSError) as error:
                print("auto (safety) failed:", type(error).__name__)


if __name__ == "__main__":
    main()
