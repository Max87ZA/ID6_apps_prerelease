"""Compare the tar read back from the head unit with the local app folders."""
import hashlib
import pathlib
import sys
import tarfile

local = pathlib.Path(sys.argv[1])
expected = {p.relative_to(local).as_posix(): p.read_bytes()
            for app in ("BoostDeck", "ShiftDeck", "EngineCodes") for p in (local / app).iterdir()}
seen, bad = set(), 0
with tarfile.open(sys.argv[2]) as tar:
    for member in tar:
        name = member.name.rstrip("/")
        if member.isdir():
            print(f"dir  {name} mode={oct(member.mode)} uid={member.uid}")
            continue
        data = tar.extractfile(member).read()
        ok = expected.get(name) == data
        bad += not ok
        seen.add(name)
        print(f"{'OK ' if ok else 'BAD'}  {name} {len(data)} mode={oct(member.mode)} uid={member.uid} "
              f"{hashlib.sha256(data).hexdigest()[:16]}")
missing = sorted(set(expected) - seen)
print("missing:", missing, "| extra:", sorted(seen - set(expected)), "| mismatched:", bad)
print("RESULT:", "ALL MATCH" if not bad and not missing and seen == set(expected) else "PROBLEM")
