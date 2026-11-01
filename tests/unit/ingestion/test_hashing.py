"""002 T6: content_hash is the lowercase hex SHA-256 of the raw snapshot bytes (E6)."""

import codecs

from plant_monitor.ingestion.hashing import content_hash

ABC_SHA256 = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_e6_known_sha256_of_abc() -> None:
    assert content_hash(b"abc") == ABC_SHA256


def test_e6_one_byte_changed_gives_a_different_hash() -> None:
    assert content_hash(b"abd") != content_hash(b"abc")


def test_e6_bom_prefixed_bytes_give_a_different_hash() -> None:
    bom_abc = codecs.BOM_UTF8 + b"abc"
    assert bom_abc == b"\xef\xbb\xbfabc"
    assert content_hash(bom_abc) != content_hash(b"abc")
    assert content_hash(bom_abc) != content_hash(b"abd")


def test_hash_is_64_lowercase_hex_characters() -> None:
    digest = content_hash(b"Sed\xc3\xa1n")
    assert len(digest) == 64
    assert digest == digest.lower()
    assert set(digest) <= set("0123456789abcdef")


def test_empty_bytes_hash_to_the_known_empty_digest() -> None:
    assert content_hash(b"") == EMPTY_SHA256
