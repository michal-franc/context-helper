# Claude Code Project Instructions

This is a Claude Code status line plugin that analyzes conversation context for instruction density and estimates accuracy degradation.

## Project Structure

```
context-helper/
├── analyze_instructions.py   # Core analysis logic (Python)
├── statusline.sh             # Shell wrapper for Claude Code status line
├── install.sh                # Installation script
├── settings-snippet.json     # Example Claude settings config
├── test_analyze_instructions.py  # Unit tests
├── README.md                 # User documentation
└── CLAUDE.md                 # This file
```

## Key Concepts

### Directive Patterns
The tool counts "directive patterns" - words that constrain LLM behavior:
- Modal obligations: must, should, shall, need to
- Prohibitions: never, don't, cannot, avoid
- Absolutes: always, every, only, exactly
- Imperatives: ensure, verify, check (at sentence start)
- Emphasis: important, critical, essential

### Accuracy Model
Accuracy is estimated using:
1. **Instruction count** - weighted by category (prohibitions harder than imperatives)
2. **Position weighting** - instructions at start/end of context weighted higher (U-curve)
3. **Context size penalty** - large contexts (>50k tokens) reduce accuracy slightly

Formula: `accuracy = floor + (base - floor) * instruction_factor * context_factor`

## Development Guidelines

### Running Tests
```bash
python3 -m unittest test_analyze_instructions -v
```

### Testing the Status Line
The statusline.sh script writes debug output to `/tmp/statusline-debug.json`. Check this file to see what Claude Code sends.

### Transcript Format
Claude Code transcripts use a nested format:
```json
{"message": {"role": "user", "content": "..."}, "type": "message", ...}
```
The analyzer handles both this nested format and flat `{"role": "...", "content": "..."}` format.

### Key Functions in analyze_instructions.py

| Function | Purpose |
|----------|---------|
| `extract_text_from_transcript()` | Parse JSONL transcript, returns segments with position info |
| `count_directives_with_position()` | Count patterns with position weighting |
| `position_weight()` | U-shaped curve: 1.0 at edges, 0.6 in middle |
| `estimate_accuracy()` | Calculate accuracy from weighted instructions + context size |
| `analyze_transcript()` | Main entry point, returns full analysis dict |

### Status Line Output
Format: `[Model] In:XXk Out:XXk (XX%) | I:XX D:X.X A:XX% | $X.XX`

- I = instruction count
- D = density (instructions per 1000 chars)
- A = estimated accuracy

### Adding New Directive Patterns
1. Add patterns to `DIRECTIVE_PATTERNS` dict in analyze_instructions.py
2. Optionally add weight to `DIRECTIVE_WEIGHTS`
3. Add tests in test_analyze_instructions.py
4. Update README.md documentation

## Common Tasks

### Debugging Status Line Issues
1. Check `/tmp/statusline-debug.json` for input data
2. Run analyzer manually: `python3 analyze_instructions.py --json /path/to/transcript.jsonl`
3. Check if transcript path exists and has content

### Adjusting Accuracy Formula
The decay rate (0.15) and floor (60%) are in `estimate_accuracy()`. Adjust these to change sensitivity:
- Higher decay_rate = faster accuracy drop
- Lower floor = allows lower minimum accuracy
- Context penalty starts at 50k tokens, caps at 5%

### Testing with Real Transcripts
```bash
# Find a transcript
find ~/.claude/projects -name "*.jsonl" | head -1

# Analyze it
python3 analyze_instructions.py --json /path/to/transcript.jsonl | jq .
```
