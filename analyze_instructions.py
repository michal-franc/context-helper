#!/usr/bin/env python3
"""
Instruction Counter for Claude Code Context Analysis

Analyzes conversation transcripts to count directive patterns that may
affect LLM accuracy based on research showing accuracy degradation with
instruction count.

Directive patterns counted:
- Modal verbs: must, should, shall, will, need to, have to
- Prohibitions: never, don't, do not, cannot, must not, shouldn't
- Absolutes: always, every, all, none, only
- Imperatives: verbs at sentence start (ensure, make, use, avoid, etc.)
- Conditionals with requirements: if...must, when...should
"""

import json
import re
import sys
import math
from pathlib import Path
from typing import Dict, List, Tuple

# Directive pattern definitions
DIRECTIVE_PATTERNS = {
    'modal_obligation': [
        r'\bmust\b',
        r'\bshould\b',
        r'\bshall\b',
        r'\bneed to\b',
        r'\bhave to\b',
        r'\brequired to\b',
        r'\bhas to\b',
    ],
    'prohibition': [
        r'\bnever\b',
        r"\bdon'?t\b",
        r'\bdo not\b',
        r'\bcannot\b',
        r"\bcan'?t\b",
        r'\bmust not\b',
        r"\bmustn'?t\b",
        r"\bshouldn'?t\b",
        r'\bshould not\b',
        r'\bprohibited\b',
        r'\bforbidden\b',
        r'\bavoid\b',
    ],
    'absolute': [
        r'\balways\b',
        r'\bevery\b',
        r'\ball\b(?!\s+of\s+the\s+above)',  # exclude "all of the above"
        r'\bnone\b',
        r'\bonly\b',
        r'\bexactly\b',
        r'\bprecisely\b',
    ],
    'imperative': [
        r'(?:^|\.\s+)ensure\b',
        r'(?:^|\.\s+)make sure\b',
        r'(?:^|\.\s+)use\b',
        r'(?:^|\.\s+)do\b',
        r'(?:^|\.\s+)check\b',
        r'(?:^|\.\s+)verify\b',
        r'(?:^|\.\s+)confirm\b',
        r'(?:^|\.\s+)add\b',
        r'(?:^|\.\s+)remove\b',
        r'(?:^|\.\s+)create\b',
        r'(?:^|\.\s+)delete\b',
        r'(?:^|\.\s+)update\b',
        r'(?:^|\.\s+)include\b',
        r'(?:^|\.\s+)exclude\b',
        r'(?:^|\.\s+)follow\b',
        r'(?:^|\.\s+)apply\b',
    ],
    'emphasis': [
        r'\bimportant\b',
        r'\bcritical\b',
        r'\bessential\b',
        r'\bcrucial\b',
        r'\bvital\b',
        r'\bmandatory\b',
        r'\bcompulsory\b',
    ],
}

# Weights for different directive types (some are more "heavy" instructions)
DIRECTIVE_WEIGHTS = {
    'modal_obligation': 1.0,
    'prohibition': 1.2,      # Prohibitions are harder to follow
    'absolute': 0.8,
    'imperative': 0.6,       # Common, less cognitive load
    'emphasis': 1.5,         # Emphasized instructions add pressure
}


def extract_text_from_transcript(transcript_path: str) -> Tuple[List[Dict], Dict]:
    """Extract all text content from a JSONL transcript file with position info."""
    text_segments = []  # List of {text, position, role} dicts
    stats = {
        'total_messages': 0,
        'system_messages': 0,
        'user_messages': 0,
        'assistant_messages': 0,
        'tool_results': 0,
        'total_chars': 0,
    }

    try:
        with open(transcript_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            total_lines = len(lines)

            for line_idx, line in enumerate(lines):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    stats['total_messages'] += 1

                    # Calculate relative position (0.0 = start, 1.0 = end)
                    position = line_idx / max(total_lines - 1, 1) if total_lines > 1 else 0.0

                    # Handle nested message format (Claude Code transcript format)
                    msg = entry.get('message', entry)
                    role = msg.get('role', '')
                    content = msg.get('content', '')

                    def add_segment(text, role, pos):
                        if text:
                            text_segments.append({'text': text, 'position': pos, 'role': role})
                            stats['total_chars'] += len(text)

                    if role == 'system':
                        stats['system_messages'] += 1
                        if isinstance(content, str):
                            add_segment(content, 'system', position)
                        elif isinstance(content, list):
                            for item in content:
                                if isinstance(item, dict) and 'text' in item:
                                    add_segment(item['text'], 'system', position)

                    elif role == 'user':
                        stats['user_messages'] += 1
                        if isinstance(content, str):
                            add_segment(content, 'user', position)
                        elif isinstance(content, list):
                            for item in content:
                                if isinstance(item, dict):
                                    if 'text' in item:
                                        add_segment(item['text'], 'user', position)
                                    # Tool results often contain instructions
                                    if item.get('type') == 'tool_result':
                                        stats['tool_results'] += 1
                                        if 'content' in item:
                                            if isinstance(item['content'], str):
                                                add_segment(item['content'], 'user', position)

                    elif role == 'assistant':
                        stats['assistant_messages'] += 1
                        # We don't count assistant messages as instructions

                except json.JSONDecodeError:
                    continue

    except FileNotFoundError:
        return [], stats
    except Exception as e:
        return [], stats

    return text_segments, stats


def position_weight(position: float) -> float:
    """
    Calculate position weight using U-shaped curve.

    Instructions at start (position=0) and end (position=1) get higher weight.
    Instructions in the middle (position=0.5) get lower weight.

    Based on "Lost in the Middle" research showing models attend more to
    beginning and end of context.

    Returns weight between 0.6 (middle) and 1.0 (edges).
    """
    # U-shaped curve: weight = 0.6 + 0.4 * (2*|pos - 0.5|)^2
    distance_from_middle = abs(position - 0.5) * 2  # 0 at middle, 1 at edges
    return 0.6 + 0.4 * (distance_from_middle ** 2)


def count_directives(text: str) -> Dict[str, int]:
    """Count directive patterns in text."""
    counts = {}
    text_lower = text.lower()

    for category, patterns in DIRECTIVE_PATTERNS.items():
        count = 0
        for pattern in patterns:
            matches = re.findall(pattern, text_lower, re.IGNORECASE | re.MULTILINE)
            count += len(matches)
        counts[category] = count

    return counts


def count_directives_with_position(text_segments: List[Dict]) -> Tuple[Dict[str, int], float]:
    """
    Count directive patterns with position weighting.

    Returns:
        - counts: raw counts per category
        - position_weighted_total: total weighted by position (higher for start/end)
    """
    counts = {cat: 0 for cat in DIRECTIVE_PATTERNS.keys()}
    position_weighted_total = 0.0

    for segment in text_segments:
        text_lower = segment['text'].lower()
        pos = segment['position']
        pos_weight = position_weight(pos)

        for category, patterns in DIRECTIVE_PATTERNS.items():
            for pattern in patterns:
                matches = re.findall(pattern, text_lower, re.IGNORECASE | re.MULTILINE)
                match_count = len(matches)
                counts[category] += match_count
                # Apply both category weight and position weight
                cat_weight = DIRECTIVE_WEIGHTS.get(category, 1.0)
                position_weighted_total += match_count * cat_weight * pos_weight

    return counts, position_weighted_total


def calculate_weighted_instructions(counts: Dict[str, int]) -> float:
    """Calculate weighted instruction count (without position weighting)."""
    weighted = 0.0
    for category, count in counts.items():
        weight = DIRECTIVE_WEIGHTS.get(category, 1.0)
        weighted += count * weight
    return weighted


def estimate_accuracy(weighted_instructions: float,
                      context_tokens: int = 0,
                      base_accuracy: float = 98.0,
                      decay_rate: float = 0.15,
                      floor: float = 60.0) -> Tuple[float, Dict]:
    """
    Estimate accuracy degradation based on instruction count and context size.

    Formula: accuracy = floor + (base - floor) * exp(-decay_rate * sqrt(instructions)) * context_penalty

    This models:
    - High accuracy (~98%) with few instructions
    - Gradual degradation as instructions accumulate
    - Diminishing returns (sqrt) - doubling instructions doesn't halve accuracy
    - Floor accuracy (~60%) even with many instructions
    - Additional penalty for large contexts (even with few instructions)

    Based on research suggesting:
    - LLMs handle 10-20 clear instructions well
    - Performance degrades with conflicting/numerous constraints
    - Complex instruction sets cause more errors in edge cases
    - Large contexts reduce attention to any single instruction
    """
    factors = {
        'instruction_penalty': 0.0,
        'context_penalty': 0.0,
    }

    if weighted_instructions <= 0 and context_tokens <= 0:
        return base_accuracy, factors

    # Instruction-based degradation
    if weighted_instructions > 0:
        instruction_factor = math.exp(-decay_rate * math.sqrt(weighted_instructions / 10))
    else:
        instruction_factor = 1.0
    factors['instruction_penalty'] = round((1 - instruction_factor) * 100, 1)

    # Context size penalty: slight degradation for large contexts
    # Starts affecting at 50k tokens, maxes out at ~5% penalty at 200k
    if context_tokens > 50000:
        # Logarithmic penalty: grows slowly
        context_factor = 1 - 0.05 * math.log10(context_tokens / 50000)
        context_factor = max(0.95, context_factor)  # Cap at 5% penalty
    else:
        context_factor = 1.0
    factors['context_penalty'] = round((1 - context_factor) * 100, 1)

    # Combined accuracy
    accuracy = floor + (base_accuracy - floor) * instruction_factor * context_factor

    return max(floor, min(base_accuracy, accuracy)), factors


def get_accuracy_rating(accuracy: float) -> str:
    """Get a text rating for the accuracy level."""
    if accuracy >= 95:
        return "excellent"
    elif accuracy >= 85:
        return "good"
    elif accuracy >= 75:
        return "moderate"
    elif accuracy >= 65:
        return "degraded"
    else:
        return "poor"


def analyze_transcript(transcript_path: str, context_tokens: int = 0) -> Dict:
    """Main analysis function."""
    text_segments, stats = extract_text_from_transcript(transcript_path)

    if not text_segments:
        return {
            'instruction_count': 0,
            'weighted_count': 0.0,
            'position_weighted_count': 0.0,
            'density': 0.0,
            'estimated_accuracy': 98.0,
            'rating': 'excellent',
            'breakdown': {},
            'factors': {'instruction_penalty': 0.0, 'context_penalty': 0.0},
            'stats': stats,
        }

    # Count with position weighting
    counts, position_weighted = count_directives_with_position(text_segments)
    total = sum(counts.values())
    weighted = calculate_weighted_instructions(counts)

    # Calculate instruction density (instructions per 1000 chars)
    total_chars = stats.get('total_chars', 1)
    density = (total / total_chars) * 1000 if total_chars > 0 else 0

    # Estimate accuracy using position-weighted count and context size
    accuracy, factors = estimate_accuracy(position_weighted, context_tokens)

    return {
        'instruction_count': total,
        'weighted_count': round(weighted, 1),
        'position_weighted_count': round(position_weighted, 1),
        'density': round(density, 2),  # instructions per 1000 chars
        'estimated_accuracy': round(accuracy, 1),
        'rating': get_accuracy_rating(accuracy),
        'breakdown': counts,
        'factors': factors,
        'stats': stats,
    }


def format_status_line(analysis: Dict, compact: bool = True) -> str:
    """Format analysis for status line display."""
    count = analysis['instruction_count']
    accuracy = analysis['estimated_accuracy']
    rating = analysis['rating']

    # Color codes based on accuracy
    if accuracy >= 90:
        color = '\033[32m'  # Green
    elif accuracy >= 75:
        color = '\033[33m'  # Yellow
    else:
        color = '\033[31m'  # Red

    reset = '\033[0m'

    if compact:
        return f"{color}Inst:{count} Acc:{accuracy:.0f}%{reset}"
    else:
        return f"{color}Instructions: {count} | Estimated Accuracy: {accuracy:.1f}% ({rating}){reset}"


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='Analyze Claude Code transcript for instruction count')
    parser.add_argument('transcript', nargs='?', help='Path to transcript JSONL file (or reads from stdin)')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    parser.add_argument('--compact', action='store_true', help='Compact status line format')
    parser.add_argument('--status-line', action='store_true', help='Read transcript path from stdin JSON')

    args = parser.parse_args()

    transcript_path = None
    context_tokens = 0

    if args.status_line:
        # Read from stdin JSON (status line mode)
        try:
            stdin_data = sys.stdin.read()
            data = json.loads(stdin_data)
            transcript_path = data.get('transcript_path')
            # Get context tokens for context size penalty
            context_tokens = data.get('context_window', {}).get('total_input_tokens', 0)
        except:
            transcript_path = None
    elif args.transcript:
        transcript_path = args.transcript
    else:
        # Try reading path from stdin
        transcript_path = sys.stdin.read().strip()

    if not transcript_path or not Path(transcript_path).exists():
        if args.json:
            print(json.dumps({'error': 'No transcript found', 'instruction_count': 0, 'estimated_accuracy': 98.0}))
        else:
            print("Inst:0 Acc:98%")
        return

    analysis = analyze_transcript(transcript_path, context_tokens)

    if args.json:
        print(json.dumps(analysis, indent=2))
    else:
        print(format_status_line(analysis, compact=args.compact))


if __name__ == '__main__':
    main()
