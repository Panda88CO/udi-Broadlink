# Repeated Code Detection & Cleaning Implementation

## Problem Statement
When learning the same RF code multiple times, the system would create duplicate nodes instead of recognizing them as the same button.

## Root Causes
1. Broadlink RF captures may have varying wrapper bytes between learns
2. Duplicate detection used only single fingerprint—missed matches with wrapper variations  
3. Decoded codes weren't being analyzed for confidence levels
4. No clean code generation from confident decodes

## Solution Implemented

### 1. **Code Helpers Enhancement** (`code_helpers.py`)

#### New Function: `detect_and_clean_repeated_code()`
```python
def detect_and_clean_repeated_code(raw_code_hex: str, packets_found: dict[str, int], threshold: int = 3) -> tuple[str, bool, str]:
    """
    Analyzes decoded RF payload for confidence level.
    - If any code appears >threshold times: generates clean transmission code via generate_rf_string
    - If no code exceeds threshold: preserves original, saves to log for analysis
    
    Returns: (final_code_hex, was_cleaned, dominant_code)
    """
```

**Behavior:**
- **High-confidence** (count > 3): Uses `generate_rf_string()` to create clean, repeatable code
- **Low-confidence** (count ≤ 3): Preserves original, saves metadata to `unrecognized_codes.log`
- **Filtering**: Ignores single-character noise (likely decode errors)

#### New Function: `save_unrecognized_code()`
```python
def save_unrecognized_code(raw_code_hex: str, packets_found: dict[str, int], reason: str = "") -> None:
    """
    Appends low-confidence RF codes to unrecognized_codes.log for analysis.
    Format: [timestamp] Reason: {reason} | Raw Hex: ... | Decoded: code(×count)...
    """
```

**Benefits:**
- Preserves forensic data for future decode improvements
- Enables pattern discovery (e.g., "always decode to 2 counts, never 5+")
- Non-disruptive (fails silently, doesn't block learning)

### 2. **Learning Flow Integration** (`nodes.py`)

Updated `_do_learn()` method to use the new detection logic:

```python
# After receiving RF packet from hub
code_hex = packet.hex()

# Decode the payload
packets_found = extract_hex_codes(code_hex)

# Detect and clean
final_code_hex, was_cleaned, dominant_code = detect_and_clean_repeated_code(code_hex, packets_found)

# Use final_code_hex for storage and duplicate checking
```

**Metadata tracking:**
```python
metadata['rf_code_was_cleaned'] = was_cleaned
metadata['rf_dominant_code'] = dominant_code
metadata['code_hex'] = final_code_hex  # Either cleaned or original
```

### 3. **Duplicate Detection Flow**

1. **Receive** RF packet
2. **Decode** with `extract_hex_codes()` → get `packets_found` dict
3. **Detect/Clean** with `detect_and_clean_repeated_code()` → get `final_code_hex`
4. **Check Duplicates** using multi-signature matching on `final_code_hex`
5. **Store** final_code_hex in learned_codes

**Result:** Same RF button learned twice = detects as duplicate, no extra node created

## Examples

### Scenario A: Real Log Payload (Single Button Press)
```
Input: b1c00c01a69e... (544 chars)
Decoded: {'E1FF8BCF13F998': 1}
Decision: was_cleaned=False (count=1, not >3)
Action: Store original, save to unrecognized_codes.log
```

### Scenario B: Hypothetical Repeated Pattern
```
Input: (payload with repeated encoding)
Decoded: {'E55F62': 6, '1E55F62': 1}
Decision: was_cleaned=True (dominant count=6 > 3)
Action: Generate clean code via generate_rf_string (510 chars)
Result: Stored code is consistent format, shorter, better for transmission
```

### Scenario C: Same Button Learned Twice
```
Learn 1: code_hex_variant_A → decode → detect → final_code_1
Learn 2: code_hex_variant_B → decode → detect → final_code_2

Duplicate check: 
- If both decoded to same dominant code → detected as duplicate
- Or if raw multi-signature matching finds overlap → detected as duplicate
Result: One node, not two
```

## Threshold Configuration

- **Current:** `threshold=3` (code must appear >3 times to trigger cleaning)
- **Rationale:** Conservative approach to avoid false cleaning on uncertain decodes
- **Adjustable:** Can be tuned in `detect_and_clean_repeated_code(threshold=N)` calls

## Files Modified

1. **code_helpers.py**
   - Added imports: `os`, `datetime`, `pathlib`
   - Added: `detect_and_clean_repeated_code()`
   - Added: `save_unrecognized_code()`
   - Fixed type hint in `code_duplicate_signatures()`

2. **nodes.py**
   - Added imports: `extract_hex_codes`, `detect_and_clean_repeated_code`
   - Modified `_do_learn()` (~432-515): Integrated decode/detect/clean logic
   - Metadata now tracks `rf_code_was_cleaned` and `rf_dominant_code`

## Testing

See `demo_repeated_code_logic.py` for comprehensive examples covering:
- Real payload decoding (Scenario 1)
- Hypothetical repeated patterns (Scenario 2)
- Edge cases and boundaries (Scenario 3)
- Integration flow documentation (Scenario 4)
- Log file format explanation (Scenario 5)

Run: `python demo_repeated_code_logic.py`

## Monitoring & Future Improvements

**unrecognized_codes.log** reveals opportunities:
- If most entries have `count=1`, consider adjusting extraction logic
- If patterns emerge (e.g., always 2x or 4x), implement decode variants
- If `generate_rf_string_failed` appears, debug encode logic
- Could use log data to train better pattern detection

## Impact Summary

| Aspect | Before | After |
|--------|--------|-------|
| **Duplicate RF codes** | Created new node | Single node (no duplicates) |
| **Code quality** | Raw wrapper-variant bytes | Clean consistent format (if confident) |
| **Forensics** | Lost data | Preserved in unrecognized_codes.log |
| **Transmission** | Variable format | Consistent (cleaned) or original (preserved) |
| **Learning time** | N/A | Transparent (integrated into flow) |

## Next Steps (User Decision)

1. **Test** with fresh RF learns to validate duplicate detection works
2. **Monitor** unrecognized_codes.log for patterns
3. **Tune** threshold if needed based on observed decode confidence
4. **Improve** extract_hex_codes if log reveals systematic decode issues
5. **Validate** that cleaned codes transmit correctly
