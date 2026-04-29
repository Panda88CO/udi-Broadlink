#!/usr/bin/env python3
"""
Comprehensive demo of repeated code detection logic.
Shows three scenarios: high-confidence, low-confidence, and edge cases.
"""

from code_helpers import (
    extract_hex_codes, 
    detect_and_clean_repeated_code,
    generate_rf_string
)
import json

print("=" * 90)
print("REPEATED CODE DETECTION & CLEANING - COMPREHENSIVE DEMO")
print("=" * 90)

# SCENARIO 1: Low-confidence decode (real payload from log)
print("\n" + "=" * 90)
print("SCENARIO 1: Real RF payload from log (single button press)")
print("=" * 90)

REAL_PAYLOAD_1 = "b1c00c01a69e0c1e0c0c0c2222222222220c0c0c2222220c220c0c0c0c220c0c22220c220c220c220c0c220c220c220c220c220c0c0c0c0c220c220c220c2222220c220c0c0c0c220c220c2222220c0c0c0c220c0c220c0c220c0c0c220c220c0c0c220c0c0c0c0c0c220c0c0c220c0c220c220c220c0c0c220c0c0c0c220c220c220c0c220c0c0c0c220c0c0c0c0c0c0c220c0c220c0c0c0c0c220c220c0c0c220c220c220c220c0c220c0c0c220c0c0c0c0c0c220c0c0c220c0c0c0c220c0c0c0c0c220c0c0c0c220c220c0c220c220c0c0c0c0c0c0c0c0c220c0005dc"

packets = extract_hex_codes(REAL_PAYLOAD_1)
print(f"Extracted codes: {packets}")
print(f"Dominant code found: {list(packets.keys())[0] if packets else 'None'}")
print(f"Occurrence count: {list(packets.values())[0] if packets else 0}")

final_code, was_cleaned, dominant = detect_and_clean_repeated_code(REAL_PAYLOAD_1, packets, threshold=3)
print(f"\nDecision: was_cleaned={was_cleaned} (count ≤ 3, so using original)")
print(f"Action: Original code preserved, entry saved to unrecognized_codes.log")
print(f"Reason: Low-confidence decode for future analysis")

# SCENARIO 2: Hypothetical high-confidence decode
print("\n" + "=" * 90)
print("SCENARIO 2: Hypothetical payload with repeated code pattern")
print("=" * 90)

# Simulate a payload that would decode to repeated codes
hypothetical_packets = {
    'E55F62': 6,      # Dominant code appears 6 times
    '1E55F62': 1,     # Noise: 1 occurrence
}

print(f"Hypothetical decoded codes: {hypothetical_packets}")
print(f"Dominant code: E55F62 with count={hypothetical_packets['E55F62']}")

# Simulate what would happen (using dummy payload - in real scenario would come from extract_hex_codes)
final_code, was_cleaned, dominant = detect_and_clean_repeated_code(
    "dummy_original_code_hex", 
    hypothetical_packets, 
    threshold=3
)

print(f"\nDecision: was_cleaned={was_cleaned} (count > 3, high confidence)")
print(f"Action: Using generate_rf_string to create clean transmission code")
print(f"Dominant code used: {dominant}")

# Show what generate_rf_string produces
if was_cleaned:
    print(f"\nCleaned code structure:")
    print(f"  - Length: {len(final_code)} characters")
    print(f"  - Format: SYNC_HEADER + packet_data (repeated 5 times)")
    print(f"  - Prefix: {final_code[:24]}...")  # Shows first sync header
    print(f"  - Storage: This clean code will be stored for future transmissions")

# SCENARIO 3: Edge cases
print("\n" + "=" * 90)
print("SCENARIO 3: Edge cases and boundary conditions")
print("=" * 90)

test_cases = [
    ("Empty decode", {}, "No codes found"),
    ("Count exactly 3", {'ABCD': 3}, "Boundary: 3 is NOT > 3, so NOT cleaned"),
    ("Count exactly 4", {'ABCD': 4}, "Boundary: 4 IS > 3, so WILL be cleaned"),
    ("Multiple codes", {'AAA': 5, 'BBB': 2}, "Picks dominant (AAA×5), cleans it"),
    ("Single-char noise filtered", {'A': 10, 'BB': 2}, "Single-char codes ignored (A), uses BB if >3"),
]

for label, test_dict, expected in test_cases:
    _, was_cleaned, dominant = detect_and_clean_repeated_code("dummy", test_dict, threshold=3)
    status = "✓ CLEANED" if was_cleaned else "✗ NOT CLEANED"
    print(f"{label:25} | {status:15} | Reason: {expected}")

# SCENARIO 4: Integration with learning flow
print("\n" + "=" * 90)
print("SCENARIO 4: Integration with nodes.py learning flow")
print("=" * 90)

print("""
In nodes.py._do_learn() method:

1. Receive RF packet from hub
   packet = hub_client.learn_rf(...)

2. Convert to hex
   code_hex = packet.hex()

3. Decode the payload
   packets_found = extract_hex_codes(code_hex)
   e.g., {'E1FF8BCF...': 1}

4. Detect and clean
   final_code_hex, was_cleaned, dominant = detect_and_clean_repeated_code(code_hex, packets_found)

5. If was_cleaned=True:
   - final_code_hex is a clean generated packet
   - Smaller, consistent format
   - Better for transmission

6. If was_cleaned=False:
   - final_code_hex is the original raw packet
   - Saved to unrecognized_codes.log with decode info
   - Preserves forensic data for future improvements

7. Store in metadata:
   metadata['rf_code_was_cleaned'] = was_cleaned
   metadata['rf_dominant_code'] = dominant
   metadata['code_hex'] = final_code_hex

8. Result: Duplicate detection uses final_code_hex
   - Same button learned twice with different wrappers still matches
   - Because extract_hex_codes finds the same dominant code
   - Or if can't decode, uses multi-signature matching on raw bytes
""")

# SCENARIO 5: File persistence
print("\n" + "=" * 90)
print("SCENARIO 5: Unrecognized codes log file")
print("=" * 90)

print("""
Location: <workspace_root>/unrecognized_codes.log

Format (appended to file):
[2026-04-29T14:46:21.123456] Reason: insufficient_repetition_count=1 | Raw Hex: b1c00c01a69e... | Decoded: E1FF8BCF...(×1)
[2026-04-29T14:47:15.456789] Reason: insufficient_repetition_count=1 | Raw Hex: b1c03c01889e... | Decoded: AAAA...(×1)
[2026-04-29T14:49:49.789012] Reason: generate_rf_string_failed | Raw Hex: b1c06e01c49e... | Decoded: BBBB...(×5)

Benefits:
✓ Preserves original payload for analysis
✓ Tracks decode results for pattern discovery
✓ Enables future improvements to decode logic
✓ Non-disruptive (logged silently, doesn't block learning)
✓ Easy to audit and investigate

Analysis:
- Monitor for common patterns in decoded codes
- If same code appears frequently, lower threshold or improve decode
- If generate_rf_string failures appear, debug encode logic
""")

print("\n" + "=" * 90)
print("SUMMARY")
print("=" * 90)
print("""
✓ High-confidence decodes (>3 repeats) → Cleaned via generate_rf_string
✓ Low-confidence decodes (≤3 repeats) → Preserved + logged for analysis
✓ Seamlessly integrated into nodes.py learning flow
✓ Fallback preserves original codes if decode/clean fails
✓ Metadata tracks decode info for debugging
✓ Duplicate detection uses final_code_hex (cleaned or original)
✓ Result: Same RF button learned multiple times = single node (no duplicates)
""")
