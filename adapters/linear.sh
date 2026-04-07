#!/usr/bin/env bash
# Sorta.Fit — Linear adapter
# Implements the board_* interface for Linear (GraphQL API)

set -euo pipefail

LINEAR_AUTH_HEADER="Authorization: Bearer $BOARD_API_TOKEN"
LINEAR_API="https://${BOARD_DOMAIN:-api.linear.app}/graphql"

# Wrapper for Linear GraphQL API calls — validates response and returns data portion
linear_graphql() {
  local query="$1"
  local variables="${2:-{}}"
  local tmpfile http_code payload_file query_file var_file
  tmpfile=$(mktemp)
  payload_file=$(mktemp)
  query_file=$(mktemp)
  var_file=$(mktemp)

  printf '%s' "$query" > "$query_file"
  printf '%s' "$variables" > "$var_file"

  node -e "
    const fs = require('fs');
    const q = fs.readFileSync(process.argv[1], 'utf8');
    const v = fs.readFileSync(process.argv[2], 'utf8');
    fs.writeFileSync(process.argv[3], JSON.stringify({ query: q, variables: JSON.parse(v) }));
  " "$query_file" "$var_file" "$payload_file"
  rm -f "$query_file" "$var_file"

  http_code=$(curl -s -w "%{http_code}" -o "$tmpfile" \
    -X POST \
    -H "$LINEAR_AUTH_HEADER" \
    -H "Content-Type: application/json" \
    -d @"$payload_file" \
    "$LINEAR_API") || {
    rm -f "$tmpfile" "$payload_file"
    log_error "Linear API request failed (network error)"
    return 1
  }
  rm -f "$payload_file"

  local body
  body=$(cat "$tmpfile")
  rm -f "$tmpfile"

  if [[ "$http_code" -ge 400 ]] || [[ "${body:0:1}" == "<" ]]; then
    log_error "Linear API error (HTTP $http_code)"
    if [[ "${body:0:1}" == "<" ]]; then
      log_error "Received HTML instead of JSON — check BOARD_API_TOKEN in .env"
    else
      log_error "Response: ${body:0:200}"
    fi
    return 1
  fi

  local has_errors
  has_errors=$(echo "$body" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);console.log(j.errors&&j.errors.length?'yes':'no');})")
  if [[ "$has_errors" == "yes" ]]; then
    local error_msg
    error_msg=$(echo "$body" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);console.log(j.errors[0].message||'Unknown error');})")
    log_error "Linear GraphQL error: $error_msg"
    return 1
  fi

  printf '%s' "$body"
}

# Helper: look up a Linear issue's internal UUID from its identifier (e.g., TEAM-123)
linear_resolve_id() {
  local issue_key="$1"
  local response
  response=$(linear_graphql "query { issueVcSearch(term: \"$issue_key\", first: 1) { nodes { id identifier } } }") 2>/dev/null || true

  # Try the search approach first, fall back to filter-based lookup
  local resolved_id
  resolved_id=$(echo "$response" | node -e "
    let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{
      try {
        const j=JSON.parse(d);
        const nodes = j.data && j.data.issueVcSearch && j.data.issueVcSearch.nodes;
        if(nodes && nodes.length > 0) { console.log(nodes[0].id); return; }
      } catch(e) {}
      console.log('');
    });" 2>/dev/null) || true

  if [[ -n "$resolved_id" ]]; then
    printf '%s' "$resolved_id"
    return 0
  fi

  # Fallback: query by identifier using issue filter
  local num
  num=$(echo "$issue_key" | sed 's/.*-//')
  response=$(linear_graphql "query { issues(filter: { team: { key: { eq: \"$BOARD_PROJECT_KEY\" } }, number: { eq: $num } }, first: 1) { nodes { id } } }") || return 1
  echo "$response" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);if(j.data.issues.nodes[0])console.log(j.data.issues.nodes[0].id);})"
}

board_get_cards_in_status() {
  local status="$1"
  local max="${2:-10}"
  local start_at="${3:-0}"
  if [[ -z "$status" ]]; then
    log_error "No status ID configured for this runner. Check RUNNER_*_FROM in .env."
    return 1
  fi

  local cursor_arg=""
  if [[ "$start_at" -gt 0 ]]; then
    # For pagination, we need to fetch and skip; Linear uses cursor-based pagination
    # We pass start_at as a skip count by fetching start_at+max and discarding the first start_at
    local fetch_count=$((start_at + max))
    local response
    response=$(linear_graphql "query { issues(filter: { team: { key: { eq: \"$BOARD_PROJECT_KEY\" } }, state: { id: { eq: \"$status\" } } }, first: $fetch_count, orderBy: createdAt) { nodes { id } } }") || return 1
    echo "$response" | node -e "
      let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{
        const j=JSON.parse(d);
        const nodes=j.data.issues.nodes||[];
        const skip=${start_at};
        for(let i=skip;i<nodes.length;i++) console.log(nodes[i].id);
      });"
    return 0
  fi

  local response
  response=$(linear_graphql "query { issues(filter: { team: { key: { eq: \"$BOARD_PROJECT_KEY\" } }, state: { id: { eq: \"$status\" } } }, first: $max, orderBy: createdAt) { nodes { id } } }") || return 1
  echo "$response" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);(j.data.issues.nodes||[]).forEach(i=>console.log(i.id));})"
}

board_get_card_key() {
  local issue_id="$1"
  local response
  response=$(linear_graphql "query { issue(id: \"$issue_id\") { identifier } }") || return 1
  echo "$response" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);console.log(j.data.issue.identifier);})"
}

board_get_card_summary() {
  local issue_key="$1"
  local num
  num=$(echo "$issue_key" | sed 's/.*-//')
  local response
  response=$(linear_graphql "query { issues(filter: { team: { key: { eq: \"$BOARD_PROJECT_KEY\" } }, number: { eq: $num } }, first: 1) { nodes { identifier title state { name } priority priorityLabel labels { nodes { name } } } } }") || return 1
  echo "$response" | node -e "
    let d='';
    process.stdin.on('data',c=>d+=c);
    process.stdin.on('end',()=>{
      const j=JSON.parse(d);
      const i=j.data.issues.nodes[0];
      if(!i){console.log('Issue not found');return;}
      const type=(i.labels&&i.labels.nodes&&i.labels.nodes[0])?i.labels.nodes[0].name:'Issue';
      console.log('Key:', i.identifier);
      console.log('Summary:', i.title);
      console.log('Status:', i.state.name);
      console.log('Type:', type);
      console.log('Priority:', i.priorityLabel||'None');
    });"
}

board_get_card_title() {
  local issue_key="$1"
  local num
  num=$(echo "$issue_key" | sed 's/.*-//')
  local response
  response=$(linear_graphql "query { issues(filter: { team: { key: { eq: \"$BOARD_PROJECT_KEY\" } }, number: { eq: $num } }, first: 1) { nodes { title } } }") || return 1
  echo "$response" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);const i=j.data.issues.nodes[0];console.log(i?i.title:'');})"
}

board_get_card_type() {
  local issue_key="$1"
  local num
  num=$(echo "$issue_key" | sed 's/.*-//')
  local response
  response=$(linear_graphql "query { issues(filter: { team: { key: { eq: \"$BOARD_PROJECT_KEY\" } }, number: { eq: $num } }, first: 1) { nodes { labels { nodes { name } } } } }") || return 1
  echo "$response" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);const i=j.data.issues.nodes[0];const l=(i&&i.labels&&i.labels.nodes&&i.labels.nodes[0]);console.log(l?l.name:'Issue');})"
}

board_get_card_description() {
  local issue_key="$1"
  local num
  num=$(echo "$issue_key" | sed 's/.*-//')
  local response
  response=$(linear_graphql "query { issues(filter: { team: { key: { eq: \"$BOARD_PROJECT_KEY\" } }, number: { eq: $num } }, first: 1) { nodes { description } } }") || return 1
  echo "$response" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);const i=j.data.issues.nodes[0];console.log(i&&i.description?i.description:'');})"
}

board_get_card_comments() {
  local issue_key="$1"
  local num
  num=$(echo "$issue_key" | sed 's/.*-//')
  local response
  response=$(linear_graphql "query { issues(filter: { team: { key: { eq: \"$BOARD_PROJECT_KEY\" } }, number: { eq: $num } }, first: 1) { nodes { comments { nodes { body user { displayName } createdAt } } } } }") || return 1
  echo "$response" | node -e "
    let d='';
    process.stdin.on('data',c=>d+=c);
    process.stdin.on('end',()=>{
      const j=JSON.parse(d);
      const i=j.data.issues.nodes[0];
      if(!i||!i.comments||!i.comments.nodes||!i.comments.nodes.length){console.log('No comments');return;}
      i.comments.nodes.forEach(c=>{
        console.log('---');
        console.log('Author:', c.user?c.user.displayName:'Unknown');
        console.log('Date:', c.createdAt);
        console.log(c.body||'');
      });
    });"
}

board_update_description() {
  local issue_key="$1"
  local markdown="${2:-$(cat)}"
  local issue_id
  issue_id=$(linear_resolve_id "$issue_key") || return 1

  if [[ -z "$issue_id" ]]; then
    log_error "Could not resolve Linear issue ID for $issue_key"
    return 1
  fi

  local tmpfile
  tmpfile=$(mktemp)
  printf '%s' "$markdown" > "$tmpfile"

  local escaped_md
  escaped_md=$(node -e "const fs=require('fs');const md=fs.readFileSync(process.argv[1],'utf8');process.stdout.write(JSON.stringify(md));" "$tmpfile")
  rm -f "$tmpfile"

  linear_graphql "mutation { issueUpdate(id: \"$issue_id\", input: { description: $escaped_md }) { success } }" > /dev/null
}

board_add_comment() {
  local issue_key="$1"
  local comment="${2:-$(cat)}"
  local issue_id
  issue_id=$(linear_resolve_id "$issue_key") || return 1

  if [[ -z "$issue_id" ]]; then
    log_error "Could not resolve Linear issue ID for $issue_key"
    return 1
  fi

  local tmpfile
  tmpfile=$(mktemp)
  printf '%s' "$comment" > "$tmpfile"

  local escaped_comment
  escaped_comment=$(node -e "const fs=require('fs');const c=fs.readFileSync(process.argv[1],'utf8');process.stdout.write(JSON.stringify(c));" "$tmpfile")
  rm -f "$tmpfile"

  linear_graphql "mutation { commentCreate(input: { issueId: \"$issue_id\", body: $escaped_comment }) { success } }" > /dev/null
}

board_transition() {
  local issue_key="$1"
  local transition_id="$2"
  local issue_id
  issue_id=$(linear_resolve_id "$issue_key") || return 1

  if [[ -z "$issue_id" ]]; then
    log_error "Could not resolve Linear issue ID for $issue_key"
    return 1
  fi

  # In Linear, transition_id is the target workflow state UUID
  linear_graphql "mutation { issueUpdate(id: \"$issue_id\", input: { stateId: \"$transition_id\" }) { success } }" > /dev/null
}

board_discover() {
  echo "=== Statuses (Workflow States) ==="
  local response
  response=$(linear_graphql "query { teams(filter: { key: { eq: \"$BOARD_PROJECT_KEY\" } }) { nodes { states { nodes { id name type } } } } }") || return 1
  echo "$response" | node -e "
    let d='';
    process.stdin.on('data',c=>d+=c);
    process.stdin.on('end',()=>{
      const j=JSON.parse(d);
      const teams=j.data.teams.nodes||[];
      if(!teams.length){console.log('Team not found. Check BOARD_PROJECT_KEY.');return;}
      const states=teams[0].states.nodes||[];
      states.forEach(s=>console.log(s.id,'-',s.name,'('+s.type+')'));
    });"

  echo ""
  echo "=== Transitions ==="
  echo "Linear allows direct state-to-state transitions."
  echo "Set TRANSITION_TO_<stateId>=<stateId> (the transition ID is the target state ID itself)."
}
