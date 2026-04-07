#!/usr/bin/env bash
# Sorta.Fit — GitHub Issues adapter
# Implements the board_* interface for GitHub Issues (gh CLI with REST fallback)
# Uses labels for lane mapping (e.g., status:todo, status:refined)

set -euo pipefail

GH_REPO="$BOARD_PROJECT_KEY"
GH_CMD=$(find_gh)
GH_USE_CLI=false
GH_API_BASE="https://api.github.com"

# Determine auth method: prefer gh CLI if authenticated, fall back to token + curl
if "$GH_CMD" auth status >/dev/null 2>&1; then
  GH_USE_CLI=true
fi

# Wrapper for GitHub API calls — uses gh api or falls back to curl with token
github_api() {
  local method="$1"
  local endpoint="$2"
  local data="${3:-}"

  local tmpfile http_code
  tmpfile=$(mktemp)

  if [[ "$GH_USE_CLI" == "true" ]]; then
    local gh_args=("api" "$endpoint" "--method" "$method")
    if [[ -n "$data" ]]; then
      gh_args+=("--input" "-")
    fi
    if printf '%s' "$data" | "$GH_CMD" "${gh_args[@]}" > "$tmpfile" 2>/dev/null; then
      cat "$tmpfile"
      rm -f "$tmpfile"
      return 0
    else
      local body
      body=$(cat "$tmpfile")
      rm -f "$tmpfile"
      log_error "GitHub API error via gh CLI: ${body:0:200}"
      return 1
    fi
  fi

  # Fallback: curl with token
  local curl_args=(-s -w "%{http_code}" -o "$tmpfile" -X "$method"
    -H "Authorization: token $BOARD_API_TOKEN"
    -H "Accept: application/vnd.github+json"
    -H "X-GitHub-Api-Version: 2022-11-28")
  if [[ -n "$data" ]]; then
    curl_args+=(-H "Content-Type: application/json" -d "$data")
  fi
  curl_args+=("${GH_API_BASE}${endpoint}")

  http_code=$(curl "${curl_args[@]}") || {
    rm -f "$tmpfile"
    log_error "GitHub API request failed (network error)"
    return 1
  }

  local body
  body=$(cat "$tmpfile")
  rm -f "$tmpfile"

  if [[ "$http_code" -ge 400 ]] || [[ "${body:0:1}" == "<" ]]; then
    log_error "GitHub API error (HTTP $http_code)"
    if [[ "${body:0:1}" == "<" ]]; then
      log_error "Received HTML instead of JSON — check BOARD_API_TOKEN in .env"
    else
      log_error "Response: ${body:0:200}"
    fi
    return 1
  fi

  printf '%s' "$body"
}

# Helper to strip # prefix from issue keys
gh_issue_number() {
  local key="$1"
  echo "${key#\#}"
}

board_get_cards_in_status() {
  local status="$1"
  local max="${2:-10}"
  local start_at="${3:-0}"
  if [[ -z "$status" ]]; then
    log_error "No status ID configured for this runner. Check RUNNER_*_FROM in .env."
    return 1
  fi

  local page=1
  if [[ "$start_at" -gt 0 ]] && [[ "$max" -gt 0 ]]; then
    page=$(( (start_at / max) + 1 ))
  fi

  local response
  response=$(github_api "GET" "/repos/${GH_REPO}/issues?labels=${status}&state=open&per_page=${max}&page=${page}&sort=created&direction=asc") || return 1
  echo "$response" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);if(Array.isArray(j))j.forEach(i=>{if(!i.pull_request)console.log(i.number)});})"
}

board_get_card_key() {
  local issue_id="$1"
  # GitHub issue numbers are the key; return with # prefix
  local response
  response=$(github_api "GET" "/repos/${GH_REPO}/issues/${issue_id}") || return 1
  echo "$response" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);console.log('#'+j.number);})"
}

board_get_card_summary() {
  local issue_key="$1"
  local num
  num=$(gh_issue_number "$issue_key")
  local response
  response=$(github_api "GET" "/repos/${GH_REPO}/issues/${num}") || return 1
  echo "$response" | node -e "
    let d='';
    process.stdin.on('data',c=>d+=c);
    process.stdin.on('end',()=>{
      const j=JSON.parse(d);
      const labels=j.labels||[];
      const statusLabel=labels.find(l=>l.name.startsWith('status:'));
      const statusName=statusLabel?statusLabel.name.replace('status:',''):'open';
      const typeLabels=['bug','feature','task','enhancement'];
      const typeLabel=labels.find(l=>typeLabels.includes(l.name.toLowerCase()));
      const type=typeLabel?typeLabel.name:'Issue';
      const priorityLabels=labels.filter(l=>l.name.startsWith('priority:'));
      const priority=priorityLabels.length?priorityLabels[0].name.replace('priority:',''):'None';
      console.log('Key:', '#'+j.number);
      console.log('Summary:', j.title);
      console.log('Status:', statusName);
      console.log('Type:', type);
      console.log('Priority:', priority);
    });"
}

board_get_card_title() {
  local issue_key="$1"
  local num
  num=$(gh_issue_number "$issue_key")
  local response
  response=$(github_api "GET" "/repos/${GH_REPO}/issues/${num}") || return 1
  echo "$response" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);console.log(j.title);})"
}

board_get_card_type() {
  local issue_key="$1"
  local num
  num=$(gh_issue_number "$issue_key")
  local response
  response=$(github_api "GET" "/repos/${GH_REPO}/issues/${num}") || return 1
  echo "$response" | node -e "
    let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{
      const j=JSON.parse(d);
      const labels=j.labels||[];
      const typeLabels=['bug','feature','task','enhancement'];
      const match=labels.find(l=>typeLabels.includes(l.name.toLowerCase()));
      console.log(match?match.name:'Issue');
    });"
}

board_get_card_description() {
  local issue_key="$1"
  local num
  num=$(gh_issue_number "$issue_key")
  local response
  response=$(github_api "GET" "/repos/${GH_REPO}/issues/${num}") || return 1
  echo "$response" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);console.log(j.body||'');})"
}

board_get_card_comments() {
  local issue_key="$1"
  local num
  num=$(gh_issue_number "$issue_key")
  local response
  response=$(github_api "GET" "/repos/${GH_REPO}/issues/${num}/comments?per_page=100") || return 1
  echo "$response" | node -e "
    let d='';
    process.stdin.on('data',c=>d+=c);
    process.stdin.on('end',()=>{
      const j=JSON.parse(d);
      if(!Array.isArray(j)||!j.length){console.log('No comments');return;}
      j.forEach(c=>{
        console.log('---');
        console.log('Author:', c.user?c.user.login:'Unknown');
        console.log('Date:', c.created_at);
        console.log(c.body||'');
      });
    });"
}

board_update_description() {
  local issue_key="$1"
  local markdown="${2:-$(cat)}"
  local num
  num=$(gh_issue_number "$issue_key")

  local tmpfile
  tmpfile=$(mktemp)
  printf '%s' "$markdown" > "$tmpfile"

  local payload
  payload=$(node -e "const fs=require('fs');const md=fs.readFileSync(process.argv[1],'utf8');console.log(JSON.stringify({body:md}));" "$tmpfile")
  rm -f "$tmpfile"

  github_api "PATCH" "/repos/${GH_REPO}/issues/${num}" "$payload" > /dev/null
}

board_add_comment() {
  local issue_key="$1"
  local comment="${2:-$(cat)}"
  local num
  num=$(gh_issue_number "$issue_key")

  local tmpfile
  tmpfile=$(mktemp)
  printf '%s' "$comment" > "$tmpfile"

  local payload
  payload=$(node -e "const fs=require('fs');const c=fs.readFileSync(process.argv[1],'utf8');console.log(JSON.stringify({body:c}));" "$tmpfile")
  rm -f "$tmpfile"

  github_api "POST" "/repos/${GH_REPO}/issues/${num}/comments" "$payload" > /dev/null
}

board_transition() {
  local issue_key="$1"
  local transition_id="$2"
  local num
  num=$(gh_issue_number "$issue_key")

  # Get current labels and remove any existing status: labels, then add the target
  local response
  response=$(github_api "GET" "/repos/${GH_REPO}/issues/${num}") || return 1

  local tid_file
  tid_file=$(mktemp)
  printf '%s' "$transition_id" > "$tid_file"

  local current_labels
  current_labels=$(echo "$response" | node -e "
    const fs=require('fs');
    const tid=fs.readFileSync(process.argv[1],'utf8');
    let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{
      const j=JSON.parse(d);
      const labels=(j.labels||[]).map(l=>l.name).filter(n=>!n.startsWith('status:'));
      labels.push(tid);
      console.log(JSON.stringify(labels));
    });" "$tid_file")
  rm -f "$tid_file"

  # Set the new label set (removes old status labels, adds new one)
  local payload
  payload=$(node -e "console.log(JSON.stringify({labels:JSON.parse(process.argv[1])}));" "$current_labels")
  github_api "PATCH" "/repos/${GH_REPO}/issues/${num}" "$payload" > /dev/null
}

board_discover() {
  echo "=== Statuses (Labels) ==="
  local response
  response=$(github_api "GET" "/repos/${GH_REPO}/labels?per_page=100") || return 1
  echo "$response" | node -e "
    let d='';
    process.stdin.on('data',c=>d+=c);
    process.stdin.on('end',()=>{
      const j=JSON.parse(d);
      if(!Array.isArray(j)){console.log('Could not fetch labels. Check BOARD_PROJECT_KEY (should be owner/repo).');return;}
      const statusLabels=j.filter(l=>l.name.startsWith('status:'));
      if(!statusLabels.length){
        console.log('No status: labels found.');
        console.log('Create labels with a \"status:\" prefix (e.g., status:todo, status:refined, status:in-progress, status:done).');
        console.log('');
        console.log('All labels in this repo:');
        j.forEach(l=>console.log(' ',l.name,'-',l.description||'(no description)'));
        return;
      }
      statusLabels.forEach(l=>{
        const safe=l.name.replace(/[^a-zA-Z0-9_]/g,'_');
        const display=l.description||l.name.replace('status:','');
        console.log(l.name,'-',display);
        console.log('  Config key: STATUS_'+safe+'=\"'+display+'\"');
        console.log('  Transition: TRANSITION_TO_'+safe+'='+l.name);
      });
    });"

  echo ""
  echo "=== Transitions ==="
  echo "GitHub Issues uses label swaps for transitions."
  echo "Config keys use underscores (bash-safe). Config values use real label names."
  echo "RUNNER_*_FROM and RUNNER_*_TO in .env use the real label names (e.g., status:todo)."
}
