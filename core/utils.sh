#!/usr/bin/env bash
# Sorta.Fit — Common utilities

# Colors (disabled if not a terminal)
if [[ -t 1 ]]; then
  RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
else
  RED=''; GREEN=''; YELLOW=''; BLUE=''; NC=''
fi

log_info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }
log_step()  { echo -e "${BLUE}[STEP]${NC} $*"; }

# Check if a command exists, print install help if not
require_command() {
  local cmd="$1"
  local install_hint="${2:-}"
  if ! command -v "$cmd" &>/dev/null; then
    # Windows fallback paths
    case "$cmd" in
      gh)
        if [[ -f "/c/Program Files/GitHub CLI/gh.exe" ]]; then
          return 0
        fi
        ;;
    esac
    log_error "'$cmd' is not installed."
    [[ -n "$install_hint" ]] && echo "  Install: $install_hint"
    return 1
  fi
}

# Find gh command (handles Windows path issues)
find_gh() {
  if command -v gh &>/dev/null; then
    echo "gh"
  elif [[ -f "/c/Program Files/GitHub CLI/gh.exe" ]]; then
    echo "/c/Program Files/GitHub CLI/gh.exe"
  else
    echo "gh"
  fi
}

# Verify all dependencies
preflight_check() {
  local failed=0
  log_step "Checking dependencies..."

  require_command "claude" "https://claude.ai/code" || failed=1
  require_command "git" "https://git-scm.com/downloads" || failed=1
  require_command "node" "https://nodejs.org" || failed=1
  require_command "curl" "Included with Git Bash on Windows" || failed=1

  local gh_cmd
  gh_cmd=$(find_gh)
  if ! "$gh_cmd" --version &>/dev/null 2>&1; then
    log_error "'gh' (GitHub CLI) is not installed."
    echo "  Install: https://cli.github.com"
    failed=1
  fi

  if [[ $failed -eq 1 ]]; then
    log_error "Missing dependencies. Install them and try again."
    return 1
  fi

  log_info "All dependencies found."
}

# Convert text to branch-safe slug
slugify() {
  echo "$1" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g' | sed 's/--*/-/g' | sed 's/^-//' | sed 's/-$//' | cut -c1-40
}

# Lock file management
lock_acquire() {
  local lock_file="$1"
  if [[ -f "$lock_file" ]]; then
    local lock_pid
    lock_pid=$(cat "$lock_file" 2>/dev/null)
    if kill -0 "$lock_pid" 2>/dev/null; then
      log_warn "Previous cycle (PID $lock_pid) still running. Skipping."
      return 1
    else
      log_warn "Stale lock (PID $lock_pid). Removing."
      rm -f "$lock_file"
    fi
  fi
  echo $$ > "$lock_file"
  return 0
}

lock_release() {
  local lock_file="$1"
  rm -f "$lock_file"
}

# Check if a card matches a runner's type filter
# Usage: matches_type_filter "Bug" "Bug,Defect"
# Returns 0 if filter is empty (no filter = match all) or card type is in the filter
matches_type_filter() {
  local card_type="$1"
  local filter="$2"
  if [[ -z "$filter" ]]; then
    return 0
  fi
  IFS=',' read -ra types <<< "$filter"
  for t in "${types[@]}"; do
    t=$(echo "$t" | xargs) # trim whitespace
    if [[ "$card_type" == "$t" ]]; then
      return 0
    fi
  done
  return 1
}

# Rate limit detection
RATE_LIMIT_FILE="${SORTA_ROOT:-.}/.rate-limited"

# Run claude and detect rate limits
# Usage: run_claude <prompt_file> <result_file> [working_dir]
# Returns 0 on success, 1 on failure, 2 on rate limit
run_claude() {
  local prompt_file="$1"
  local result_file="$2"
  local work_dir="${3:-$SORTA_ROOT}"
  local stderr_file
  stderr_file=$(mktemp)

  (cd "$work_dir" && claude -p "$(cat "$prompt_file")" > "$result_file" 2>"$stderr_file") || {
    local stderr_content
    stderr_content=$(cat "$stderr_file" 2>/dev/null)
    rm -f "$stderr_file"

    # Check for rate limit indicators
    if echo "$stderr_content" | grep -qiE "rate.limit|too.many.requests|usage.limit|capacity|throttl"; then
      log_warn "Claude rate limit detected. Pausing further runs."
      date +%s > "$RATE_LIMIT_FILE"
      return 2
    fi

    return 1
  }

  rm -f "$stderr_file"
  return 0
}

# Check if we're currently rate limited
is_rate_limited() {
  if [[ ! -f "$RATE_LIMIT_FILE" ]]; then
    return 1
  fi
  # Wait at least 30 minutes before retrying after a rate limit
  local limit_time
  limit_time=$(cat "$RATE_LIMIT_FILE" 2>/dev/null || echo 0)
  local now
  now=$(date +%s)
  local wait_seconds=1800
  if (( now - limit_time < wait_seconds )); then
    local remaining=$(( wait_seconds - (now - limit_time) ))
    log_warn "Rate limited. ${remaining}s remaining before retry."
    return 0
  fi
  # Limit window passed, clear the flag
  rm -f "$RATE_LIMIT_FILE"
  return 1
}

# Render a prompt template — replaces {{KEY}} with values
# Usage: render_template "file.md" KEY1 "value1" KEY2 "value2"
render_template() {
  local template_file="$1"
  shift

  if [[ ! -f "$template_file" ]]; then
    log_error "Template not found: $template_file"
    return 1
  fi

  local content
  content=$(cat "$template_file")

  while [[ $# -ge 2 ]]; do
    local key="$1"
    local value="$2"
    shift 2
    # Use node for safe replacement (handles special chars)
    content=$(node -e "
      const content = process.argv[1];
      const key = process.argv[2];
      const value = process.argv[3];
      console.log(content.split('{{' + key + '}}').join(value));
    " "$content" "$key" "$value")
  done

  echo "$content"
}
