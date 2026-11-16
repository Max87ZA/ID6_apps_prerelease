#!/usr/bin/env python3
"""Read-only discovery: step through UDS ReadDataByIdentifier (service 22) on one ECU.

Sends only service 0x22 requests, paced, over a single HSFZ connection, while parked.
Records which identifiers answer. It never writes, changes sessions or clears anything.
"""
import argparse
import json
import socket
import struct
import time


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


def read_did(conn, ecu, did, timeout):
    request = bytes((0x22, did >> 8, did & 0xFF))
    conn.sendall(struct.pack(">IHBB", len(request) + 2, 1, 0xF4, ecu) + request)
    deadline = time.monotonic() + timeout
    while True:
        length, control = struct.unpack(">IH", recv_exact(conn, 6, deadline))
        if length > 8192:
            raise ConnectionError("oversized frame")
        payload = recv_exact(conn, length, deadline)
        if control == 0x12:
            conn.sendall(struct.pack(">IHBB", 2, 0x13, 0, 0xF4))
            continue
        if control != 1 or payload[:2] != bytes((ecu, 0xF4)):
            continue
        reply = payload[2:]
        if reply[:3] == bytes((0x62, did >> 8, did & 0xFF)):
            return "ok", reply[3:].hex(" ")
        if len(reply) == 3 and reply[0] == 0x7F and reply[1] == 0x22:
            if reply[2] == 0x78:
                deadline = time.monotonic() + 2
                continue
            return "nrc", f"{reply[2]:02X}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local", required=True)
    parser.add_argument("--gateway", required=True)
    parser.add_argument("--ecu", required=True, help="hex ECU address, e.g. 1a")
    parser.add_argument("--first", required=True, help="first DID, hex")
    parser.add_argument("--last", required=True, help="last DID, hex")
    parser.add_argument("--out", required=True)
    parser.add_argument("--gap-ms", type=int, default=20)
    args = parser.parse_args()
    ecu, first, last = int(args.ecu, 16), int(args.first, 16), int(args.last, 16)
    if not (0 < ecu < 0xF0) or not (0 <= first <= last <= 0xFFFF) or last - first > 0x1FFF:
        parser.error("bad ECU or range (at most 8192 identifiers per run)")
    found, other, timeouts, reconnects, silent = {}, {}, 0, 0, 0
    conn = None
    started = time.monotonic()
    did = first
    while did <= last:
        try:
            if conn is None:
                conn = socket.create_connection((args.gateway, 6801), timeout=3, source_address=(args.local, 0))
            kind, value = read_did(conn, ecu, did, 0.4)
            silent = 0
            if kind == "ok":
                found[f"{did:04X}"] = value
            elif value != "31":
                other[f"{did:04X}"] = value
        except TimeoutError:
            timeouts += 1
            silent += 1
            if silent >= 8:
                print(f"ECU {args.ecu} gave no answer to 8 requests in a row at {did:04X}; stopping.")
                break
        except OSError as error:
            reconnects += 1
            if conn is not None:
                conn.close()
            conn = None
            if reconnects > 12:
                print(f"too many connection errors ({error}); stopping at {did:04X}")
                break
            time.sleep(1.5)
            continue
        if (did - first) % 512 == 511:
            print(f"  ..{did:04X} found={len(found)} other={len(other)} timeouts={timeouts} "
                  f"reconnects={reconnects} t={time.monotonic() - started:.0f}s", flush=True)
        did += 1
        time.sleep(args.gap_ms / 1000)
    if conn is not None:
        conn.close()
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump({"ecu": args.ecu, "first": f"{first:04X}", "stopped_at": f"{min(did, last):04X}",
                   "found": found, "other_nrc": other, "timeouts": timeouts}, handle, indent=1)
    print(f"done: {len(found)} identifiers answered, {len(other)} refused for another reason, "
          f"{timeouts} timeouts, {time.monotonic() - started:.0f}s")


if __name__ == "__main__":
    main()
