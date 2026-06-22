"""Export checksum determinism tests (F-007).

The 'deterministic asset pack' contract rests on per-file SHA-256 via
cli.hash_file. These tests pin two invariants:

  (1) hash_file over a fixed byte sequence equals the known hashlib.sha256
      digest, and is stable across repeated calls;
  (2) identical bytes in two different files produce the SAME checksum.

DOCUMENTED SCOPE: the export manifest as a whole is NOT byte-reproducible — it
embeds exported_at (now_iso wall-clock) and foundry_version/git_hash. Only the
per-file checksums under manifest['files'] are deterministic. We therefore
assert ONLY the per-file checksum stability, never whole-manifest equality.
"""

import hashlib

from foundry import cli


def test_hash_file_matches_known_sha256(tmp_path):
    data = b"sprite-foundry deterministic bytes \x00\x01\x02" * 100
    expected = hashlib.sha256(data).hexdigest()
    p = tmp_path / "a.bin"
    p.write_bytes(data)
    assert cli.hash_file(p) == expected


def test_hash_file_is_stable_across_calls(tmp_path):
    p = tmp_path / "b.bin"
    p.write_bytes(b"x" * 50000)  # spans multiple 8192-byte chunks
    first = cli.hash_file(p)
    second = cli.hash_file(p)
    assert first == second


def test_identical_bytes_yield_identical_checksums(tmp_path):
    data = b"identical payload across two files"
    p1 = tmp_path / "one.png"
    p2 = tmp_path / "two.png"
    p1.write_bytes(data)
    p2.write_bytes(data)
    assert cli.hash_file(p1) == cli.hash_file(p2)


def test_different_bytes_yield_different_checksums(tmp_path):
    p1 = tmp_path / "one.bin"
    p2 = tmp_path / "two.bin"
    p1.write_bytes(b"alpha")
    p2.write_bytes(b"beta")
    assert cli.hash_file(p1) != cli.hash_file(p2)


def test_empty_file_hashes_to_sha256_of_empty(tmp_path):
    p = tmp_path / "empty.bin"
    p.write_bytes(b"")
    assert cli.hash_file(p) == hashlib.sha256(b"").hexdigest()
