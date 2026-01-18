# Context Helper - Claude Code Instruction Counter

A Claude Code status line plugin that tracks the number of directive instructions in your context and estimates potential accuracy degradation.

![Status Line Example](example.jpg)

| Component | Meaning |
|-----------|---------|
| `Opus 4.5` | Current model |
| `context-doctor` | Project directory |
| `In:250.7k` | Input tokens (context sent to model) |
| `Out:33.6k` | Output tokens (generated this session) |
| `[45%]` | Context window usage |
| `I:277` | Instruction count (277 directives detected) |
| `D:1.9` | Density (directives per 1000 chars) |
| `A:79%` | Estimated accuracy |

**Accuracy colors:** 🟢 Green (≥90%) | 🟡 Yellow (75-90%) | 🔴 Red (<75%)

**Context colors:** 🟢 Green (<50%) | 🟡 Yellow (50-80%) | 🔴 Red (≥80%)

## Requirements

- Python 3.6+
- `jq` (for JSON parsing in shell script)
- `bc` (for floating point math in shell script)

## Installation

1. Copy files to your Claude plugins directory:
```bash
mkdir -p ~/.claude/plugins/context-helper
cp analyze_instructions.py statusline.sh ~/.claude/plugins/context-helper/
chmod +x ~/.claude/plugins/context-helper/*.sh ~/.claude/plugins/context-helper/*.py
```

2. Add to `~/.claude/settings.json`:
```json
{
  "statusLine": {
    "type": "command",
    "command": "~/.claude/plugins/context-helper/statusline.sh",
    "padding": 0
  }
}
```

3. Restart Claude Code

## What It Tracks

The plugin counts **directive patterns** - instructions that constrain LLM behavior:

| Category | Examples | Weight |
|----------|----------|--------|
| Modal obligations | must, should, shall, need to, have to | 1.0 |
| Prohibitions | never, don't, cannot, must not, avoid | 1.2 |
| Absolutes | always, every, all, none, only, exactly | 0.8 |
| Imperatives | ensure, make sure, use, check, verify | 0.6 |
| Emphasis | important, critical, essential, mandatory | 1.5 |

## Accuracy Degradation Formula

The estimated accuracy is calculated using an exponential decay model with multiple factors:

```
accuracy = floor + (base - floor) * instruction_factor * context_factor
```

Where:
- `base` = 98% (accuracy with minimal instructions)
- `floor` = 60% (minimum accuracy even with many instructions)
- `instruction_factor` = exp(-0.15 * sqrt(position_weighted_instructions / 10))
- `context_factor` = penalty for large contexts (up to 5% at 200k tokens)

### Position Weighting

Instructions are weighted by their position in the context using a U-shaped curve:

```
position_weight = 0.6 + 0.4 * (distance_from_middle)²
```

- Instructions at the **start** (system prompt) → weight 1.0
- Instructions at the **end** (recent messages) → weight 1.0
- Instructions in the **middle** → weight 0.6

This models the "Lost in the Middle" phenomenon where LLMs pay more attention to the beginning and end of their context window.

### Context Size Penalty

Large contexts reduce accuracy even with few instructions:

- Under 50k tokens: no penalty
- 50k-200k tokens: up to 5% penalty (logarithmic scale)

### Instruction Density

Density measures how "instruction-heavy" the context is:

```
density = instruction_count / total_chars * 1000
```

- Low density (<1.0): Mostly code/data, few constraints
- Medium density (1-3): Normal instructional content
- High density (>3): Very constraint-heavy, may cause conflicts

### Rationale

Research on LLM instruction following suggests:

1. **Baseline performance** (~98%): With few clear instructions, models perform near their maximum capability
2. **Logarithmic degradation**: Performance doesn't drop linearly. The first 50 instructions cause more relative degradation than the next 50. The `sqrt()` models this diminishing effect.
3. **Floor effect** (~60%): Even with overwhelming instructions, models maintain some base competence. They don't fail completely.
4. **Position effects**: Instructions at start/end get more attention than those in the middle
5. **Context size matters**: Even "clean" tokens add noise and reduce focus on any single instruction
6. **Weighted categories**: Some directive types are harder to follow:
   - Prohibitions (1.2x) - "never do X" is harder than "do X"
   - Emphasis (1.5x) - critical instructions add cognitive load
   - Imperatives (0.6x) - common patterns, less confusing

### Accuracy Bands

| Accuracy | Rating | Interpretation |
|----------|--------|----------------|
| 95-100%  | Excellent | Low instruction load, high reliability |
| 85-95%   | Good | Moderate load, occasional edge case issues |
| 75-85%   | Moderate | Heavy load, expect some instruction conflicts |
| 65-75%   | Degraded | Very heavy load, consider context compaction |
| <65%     | Poor | Extremely loaded context, reliability issues likely |

## Token Details

**Input tokens** represent the total context sent to the model on each turn:
- System prompt and tools (~20k tokens typically)
- Conversation history (grows as you chat)
- File contents, tool results, and other context

**Output tokens** represent what Claude has generated:
- All responses in the current session
- Tool calls and their parameters

The percentage shows how much of the model's context window (200k for Opus) is being used. As this grows, older context may be summarized to make room.

## CLI Usage

You can also run the analyzer directly:

```bash
# Analyze a transcript file
./analyze_instructions.py /path/to/transcript.jsonl

# Get JSON output
./analyze_instructions.py --json /path/to/transcript.jsonl

# Detailed breakdown
./analyze_instructions.py --json /path/to/transcript.jsonl | jq '.breakdown'
```

### JSON Output Format

```json
{
  "instruction_count": 127,
  "weighted_count": 134.2,
  "position_weighted_count": 98.5,
  "density": 2.1,
  "estimated_accuracy": 82.3,
  "rating": "moderate",
  "breakdown": {
    "modal_obligation": 45,
    "prohibition": 28,
    "absolute": 22,
    "imperative": 19,
    "emphasis": 13
  },
  "factors": {
    "instruction_penalty": 15.2,
    "context_penalty": 2.5
  },
  "stats": {
    "total_messages": 42,
    "system_messages": 1,
    "user_messages": 20,
    "assistant_messages": 21,
    "tool_results": 15,
    "total_chars": 60476
  }
}
```

| Field | Description |
|-------|-------------|
| `instruction_count` | Raw count of directive patterns |
| `weighted_count` | Count weighted by category (prohibitions 1.2x, etc.) |
| `position_weighted_count` | Count weighted by both category and position |
| `density` | Instructions per 1000 characters |
| `estimated_accuracy` | Predicted accuracy percentage |
| `factors.instruction_penalty` | Accuracy loss from instructions (%) |
| `factors.context_penalty` | Accuracy loss from context size (%) |

## Testing

Run the unit tests:

```bash
python3 -m unittest test_analyze_instructions -v
```

The test suite covers:
- Position weighting (U-shaped curve)
- Directive pattern counting
- Category weight calculations
- Accuracy estimation with context penalties
- Transcript parsing (both flat and nested formats)
- Integration tests for full pipeline

## Limitations

- The accuracy formula is a heuristic, not a precise measurement
- Instruction quality matters more than quantity (not captured)
- Conflicting instructions cause more degradation than additive ones
- The tool counts patterns, not semantic understanding

## References

Research basis for this approach:
- "Lost in the Middle" - Liu et al. (2023) - position effects in long contexts
- Instruction following benchmarks showing degradation with constraint count
- Empirical observations of LLM behavior with complex system prompts
