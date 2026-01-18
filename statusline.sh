#!/bin/bash
# Claude Code Status Line - Instruction Counter & Accuracy Estimator
#
# This script reads Claude Code's status line input and displays:
# - Current instruction count (directive patterns in context)
# - Estimated accuracy based on instruction load
#
# Install: Add to your Claude Code settings.json:
# {
#   "statusLine": {
#     "type": "command",
#     "command": "/path/to/context-helper/statusline.sh",
#     "padding": 0
#   }
# }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ANALYZER="$SCRIPT_DIR/analyze_instructions.py"

# Read full input from stdin
input=$(cat)

# Extract fields from status line JSON
transcript_path=$(echo "$input" | jq -r '.transcript_path // empty')
model=$(echo "$input" | jq -r '.model.display_name // "?"')
cwd=$(echo "$input" | jq -r '.cwd // empty')
input_tokens=$(echo "$input" | jq -r '.context_window.total_input_tokens // 0')
output_tokens=$(echo "$input" | jq -r '.context_window.total_output_tokens // 0')
ctx_pct=$(echo "$input" | jq -r '.context_window.used_percentage // 0')

# Get folder name from cwd (last component of path)
if [ -n "$cwd" ]; then
    folder=$(basename "$cwd")
else
    folder="?"
fi

# Format token counts (e.g., 23k, 1.2k)
format_tokens() {
    local tokens=$1
    if [ "$tokens" -ge 1000 ]; then
        printf "%.1fk" "$(echo "scale=1; $tokens / 1000" | bc)"
    else
        echo "$tokens"
    fi
}

input_fmt=$(format_tokens "$input_tokens")
output_fmt=$(format_tokens "$output_tokens")
total_tokens=$((input_tokens + output_tokens))
total_fmt=$(format_tokens "$total_tokens")

# Analyze instructions if transcript exists
if [ -n "$transcript_path" ] && [ -f "$transcript_path" ] && [ -f "$ANALYZER" ]; then
    # Run analyzer and capture output
    analysis=$(echo "$input" | python3 "$ANALYZER" --status-line --json 2>/dev/null)

    if [ -n "$analysis" ]; then
        inst_count=$(echo "$analysis" | jq -r '.instruction_count // 0')
        accuracy=$(echo "$analysis" | jq -r '.estimated_accuracy // 98')
        density=$(echo "$analysis" | jq -r '.density // 0')
        inst_penalty=$(echo "$analysis" | jq -r '.factors.instruction_penalty // 0')
        ctx_penalty=$(echo "$analysis" | jq -r '.factors.context_penalty // 0')

        # Color based on accuracy
        if (( $(echo "$accuracy >= 90" | bc -l) )); then
            color='\033[32m'  # Green
        elif (( $(echo "$accuracy >= 75" | bc -l) )); then
            color='\033[33m'  # Yellow
        else
            color='\033[31m'  # Red
        fi
        reset='\033[0m'

        # Format displays
        acc_display=$(printf "%.0f%%" "$accuracy")
        inst_display="I:${inst_count}"
        density_display=$(printf "D:%.1f" "$density")
    else
        color='\033[90m'
        reset='\033[0m'
        inst_display="I:?"
        density_display="D:?"
        acc_display="?%"
    fi
else
    color='\033[90m'
    reset='\033[0m'
    inst_display="I:0"
    density_display="D:0"
    acc_display="98%"
fi

# Color for context percentage
if (( $(echo "$ctx_pct < 50" | bc -l) )); then
    ctx_color='\033[32m'  # Green
elif (( $(echo "$ctx_pct < 80" | bc -l) )); then
    ctx_color='\033[33m'  # Yellow
else
    ctx_color='\033[31m'  # Red
fi

# Build status line
# Format: [Model] folder | In:XXk Out:XXk (XX%) | I:XX D:X.X A:XX%
dim='\033[90m'
echo -e "${dim}[${reset}${model}${dim}]${reset} ${folder} ${dim}|${reset} ${dim}In:${reset}${input_fmt} ${dim}Out:${reset}${output_fmt} ${dim}[${reset}${ctx_color}${ctx_pct}%${reset}${dim}]${reset} ${dim}|${reset} ${color}${inst_display} ${density_display} A:${acc_display}${reset}"
