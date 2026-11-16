#!/usr/bin/env python3
"""Read-only: ask every ECU for its diagnostic index (22 F1 50) and list who answers."""
import socket
import struct
import sys
import time

local, gateway = sys.argv[1], sys.argv[2]
answers = {}
with socket.create_connection((gateway, 6801), timeout=3, source_address=(local, 0)) as conn:
    request = bytes((0x22, 0xF1, 0x50))
    conn.sendall(struct.pack(">IHBB", len(request) + 2, 1, 0xF4, 0xDF) + request)
    deadline = time.monotonic() + 4
    buffer = b""
    while time.monotonic() < deadline:
        conn.settimeout(max(0.05, deadline - time.monotonic()))
        try:
            part = conn.recv(4096)
        except TimeoutError:
            break
        if not part:
            break
        buffer += part
        while len(buffer) >= 6:
            length, control = struct.unpack(">IH", buffer[:6])
            if len(buffer) < 6 + length:
                break
            payload, buffer = buffer[6:6 + length], buffer[6 + length:]
            if control == 1 and len(payload) > 2 and payload[1] == 0xF4:
                answers[payload[0]] = payload[2:].hex(" ")
for address in sorted(answers):
    print(f"{address:02X}: {answers[address]}")
print(len(answers), "ECUs answered")
