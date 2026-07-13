from pathlib import Path

for p in Path(".").rglob("*.md"):
    raw = p.read_bytes()
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        p.write_bytes(raw.decode("cp1252").encode("utf-8"))
        print("fixed:", p)
print("done")