"""Shared helpers for Broadlink code normalization, matching, and decoding."""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path


def normalize_code_hex(candidate: str) -> str:
    """Return lowercase hex with separators removed when possible."""
    text = str(candidate or "").strip().lower()
    if text.startswith("0x"):
        text = text[2:]
    return "".join(ch for ch in text if ch in "0123456789abcdef")


def code_duplicate_fingerprint(code_hex: str) -> str:
    """Return a byte-rotation-invariant fingerprint for duplicate detection."""
    normalized = normalize_code_hex(code_hex)
    if not normalized or len(normalized) % 2 != 0:
        return normalized
    try:
        payload = bytes.fromhex(normalized)
    except ValueError:
        return normalized
    size = len(payload)
    if size <= 1:
        return normalized

    doubled = payload + payload
    best = payload
    for offset in range(1, size):
        candidate = doubled[offset:offset + size]
        if candidate < best:
            best = candidate
    return best.hex()


def code_duplicate_signatures(code_hex: str, stored_fingerprint: str = "") -> set[str]:
    """Build comparable duplicate signatures across legacy/current payload formats."""
    normalized = normalize_code_hex(code_hex)
    signatures: set[str] = set()

    def _add_candidate(candidate_hex: str) -> None:
        text = normalize_code_hex(candidate_hex)
        if not text:
            return
        signatures.add(text)
        fp = code_duplicate_fingerprint(text)
        if fp:
            signatures.add(fp)

    _add_candidate(normalized)

    # Broadlink packets can vary in wrapper/header bytes between learns.
    if len(normalized) > 8:
        _add_candidate(normalized[8:])

    # Some stored fingerprints include packet header bytes repeated at the end.
    if len(normalized) > 16 and normalized.endswith(normalized[:8]):
        _add_candidate(normalized[:-8])

    terminator = "0005dc"
    term_index = normalized.find(terminator)
    if term_index > 0:
        core = normalized[:term_index + len(terminator)]
        _add_candidate(core)
        if len(core) > 8:
            _add_candidate(core[8:])

    stored = normalize_code_hex(stored_fingerprint)
    if stored:
        signatures.add(stored)

    return signatures


def generate_rf_string(hex_code, repeats=5, bit_length=24):
    # 1. Setup Timing Constants (Clean versions of your data)
    SHORT = "0C"  # ~12 units
    LONG = "22"   # ~34 units
    SYNC_HEADER = "000163"
    
    # 2. Convert Hex Code to Binary
    # zfill ensures we keep leading zeros if the code is short
    binary_code = bin(int(hex_code, 16))[2:].zfill(bit_length)
    
    # 3. Create a single "Perfect" Packet
    packet_data = ""
    for bit in binary_code:
        if bit == '1':
            # Binary 1: Long High + Short Low
            packet_data += LONG + SHORT
        else:
            # Binary 0: Short High + Long Low
            packet_data += SHORT + LONG
            
    # 4. Assemble the full string with repeats
    # Each repeat starts with the Sync Header
    full_string = ""
    for _ in range(repeats):
        full_string += SYNC_HEADER + packet_data
        
    return full_string

def extract_hex_codes(long_raw_string: str) -> dict[str, int]:
    """Decode a raw Broadlink timing payload into detected hex codes and counts."""
    if "0005" in long_raw_string:
        long_raw_string = long_raw_string.split("0005")[0]

    raw_bytes = re.findall("..", long_raw_string)

    # Based on observed data: short pulse ~0x0A, long pulse ~0x22.
    threshold = 0x18

    packets_found: dict[str, int] = {}

    packet_chunks: list[list[str]] = []
    temp_chunk: list[str] = []

    i = 0
    while i < len(raw_bytes):
        # Packet start marker usually begins with 00 01 and a subtype byte.
        if i + 2 < len(raw_bytes) and raw_bytes[i] == "00" and raw_bytes[i + 1] == "01":
            if temp_chunk:
                packet_chunks.append(temp_chunk)
            temp_chunk = []
            i += 3
        else:
            temp_chunk.append(raw_bytes[i])
            i += 1
    if temp_chunk:
        packet_chunks.append(temp_chunk)

    for chunk in packet_chunks:
        binary_str = ""
        pulse_timings = [int(x, 16) for x in chunk]

        for j in range(0, len(pulse_timings) - 1, 2):
            high = pulse_timings[j]
            low = pulse_timings[j + 1]

            if high > threshold and low < threshold:
                binary_str += "1"
            elif high < threshold and low > threshold:
                binary_str += "0"
            else:
                continue

        if not binary_str:
            continue

        try:
            hex_code = hex(int(binary_str, 2))[2:].upper().zfill(len(binary_str) // 4)
        except ValueError:
            continue

        packets_found[hex_code] = packets_found.get(hex_code, 0) + 1

    return packets_found


def detect_and_clean_repeated_code(raw_code_hex: str, packets_found: dict[str, int], threshold: int = 3) -> tuple[str, bool, str]:
    """
    Detect if any decoded code repeats more than threshold times, indicating a reliable decode.
    If found, generate a clean transmission-ready code using generate_rf_string.
    
    Returns: (final_code_hex, was_cleaned, dominant_code)
    - final_code_hex: Clean code if repeat detected, else raw_code_hex
    - was_cleaned: True if generate_rf_string was used, False if using raw packet
    - dominant_code: The most frequently occurring decoded code (may differ from final_code_hex if using raw)
    """
    # Find the most frequently occurring decoded code
    if not packets_found or not isinstance(packets_found, dict):
        return raw_code_hex, False, ""
    
    # Sort by frequency (descending) and filter out single-char noise (likely decoding errors)
    valid_codes = {code: count for code, count in packets_found.items() if len(code) > 1}
    
    if not valid_codes:
        return raw_code_hex, False, ""
    
    dominant_code = max(valid_codes.items(), key=lambda item: item[1])[0]
    dominant_count = valid_codes[dominant_code]
    
    # If dominant code repeats more than threshold times, generate clean version
    if dominant_count > threshold:
        try:
            clean_code = generate_rf_string(dominant_code, repeats=5)
            return clean_code, True, dominant_code
        except (ValueError, TypeError):
            # If generate_rf_string fails, use original and log the issue
            save_unrecognized_code(raw_code_hex, packets_found, reason="generate_rf_string_failed")
            return raw_code_hex, False, dominant_code
    else:
        # Not enough repetition for confident decode; save for later analysis
        save_unrecognized_code(raw_code_hex, packets_found, reason=f"insufficient_repetition_count={dominant_count}")
        return raw_code_hex, False, dominant_code


def save_unrecognized_code(raw_code_hex: str, packets_found: dict[str, int], reason: str = "") -> None:
    """
    Save RF codes that could not be reliably decoded (insufficient repetition or generation failure).
    This file can be analyzed later to improve decoding logic.
    """
    try:
        # Create/append to unrecognized_codes.log in the workspace root
        log_dir = Path(__file__).parent
        log_file = log_dir / "unrecognized_codes.log"
        
        timestamp = datetime.now().isoformat()
        
        # Format packets_found nicely
        codes_str = ", ".join(f"{code}(×{count})" for code, count in sorted(packets_found.items(), key=lambda x: -x[1]))
        
        log_entry = f"[{timestamp}] Reason: {reason} | Raw Hex: {raw_code_hex[:100]}... | Decoded: {codes_str}\n"
        
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(log_entry)
    except Exception as e:
        # Fail silently to avoid disrupting learn flow
        print(f"Warning: Could not save unrecognized code to log: {e}")
