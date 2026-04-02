#!/usr/bin/env bash
# Sorta.Fit — Jira adapter
# Implements the board_* interface for Jira Cloud

set -euo pipefail

JIRA_AUTH_HEADER="Authorization: Basic $(echo -n "$BOARD_EMAIL:$BOARD_API_TOKEN" | base64 -w 0)"
JIRA_BASE="https://$BOARD_DOMAIN/rest/api/3"

# Wrapper for Jira API calls — validates response is JSON before returning
jira_curl() {
  local tmpfile http_code
  tmpfile=$(mktemp)
  http_code=$(curl -s -w "%{http_code}" -o "$tmpfile" "$@") || {
    rm -f "$tmpfile"
    log_error "Jira API request failed (network error)"
    return 1
  }

  local body
  body=$(cat "$tmpfile")
  rm -f "$tmpfile"

  if [[ "$http_code" -ge 400 ]] || [[ "${body:0:1}" == "<" ]]; then
    log_error "Jira API error (HTTP $http_code)"
    if [[ "${body:0:1}" == "<" ]]; then
      log_error "Received HTML instead of JSON — check BOARD_DOMAIN, BOARD_EMAIL, and BOARD_API_TOKEN in .env"
    fi
    return 1
  fi

  printf '%s' "$body"
}

board_get_cards_in_status() {
  local status="$1"
  local max="${2:-10}"
  local response
  response=$(jira_curl -X POST \
    -H "$JIRA_AUTH_HEADER" \
    -H "Content-Type: application/json" \
    -d "{\"jql\":\"project=$BOARD_PROJECT_KEY AND status=$status ORDER BY rank ASC\",\"maxResults\":$max}" \
    "$JIRA_BASE/search/jql") || return 1
  echo "$response" | \
    node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);if(j.issues)j.issues.forEach(i=>console.log(i.id));})"
}

board_get_card_key() {
  local issue_id="$1"
  local response
  response=$(jira_curl -H "$JIRA_AUTH_HEADER" "$JIRA_BASE/issue/$issue_id") || return 1
  echo "$response" | \
    node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);console.log(j.key);})"
}

board_get_card_summary() {
  local issue_key="$1"
  local response
  response=$(jira_curl -H "$JIRA_AUTH_HEADER" "$JIRA_BASE/issue/$issue_key") || return 1
  echo "$response" | \
    node -e "
      let d='';
      process.stdin.on('data',c=>d+=c);
      process.stdin.on('end',()=>{
        const j=JSON.parse(d);
        console.log('Key:', j.key);
        console.log('Summary:', j.fields.summary);
        console.log('Status:', j.fields.status.name);
        console.log('Type:', j.fields.issuetype.name);
        console.log('Priority:', j.fields.priority?.name || 'None');
      });"
}

board_get_card_title() {
  local issue_key="$1"
  local response
  response=$(jira_curl -H "$JIRA_AUTH_HEADER" "$JIRA_BASE/issue/$issue_key") || return 1
  echo "$response" | \
    node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);console.log(j.fields.summary);})"
}

board_get_card_type() {
  local issue_key="$1"
  local response
  response=$(jira_curl -H "$JIRA_AUTH_HEADER" "$JIRA_BASE/issue/$issue_key") || return 1
  echo "$response" | \
    node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);console.log(j.fields.issuetype.name);})"
}

board_get_card_description() {
  local issue_key="$1"
  local response
  response=$(jira_curl -H "$JIRA_AUTH_HEADER" "$JIRA_BASE/issue/$issue_key") || return 1
  echo "$response" | \
    node -e "
      let d='';
      process.stdin.on('data',c=>d+=c);
      process.stdin.on('end',()=>{
        const j=JSON.parse(d);
        const desc=j.fields.description;
        if(!desc){console.log('');return;}
        function extractText(node){
          if(!node)return '';
          if(node.type==='text')return node.text||'';
          if(node.content)return node.content.map(extractText).join(node.type==='paragraph'?'\n':'');
          return '';
        }
        console.log(extractText(desc));
      });"
}

board_get_card_comments() {
  local issue_key="$1"
  local response
  response=$(jira_curl -H "$JIRA_AUTH_HEADER" "$JIRA_BASE/issue/$issue_key/comment") || return 1
  echo "$response" | \
    node -e "
      let d='';
      process.stdin.on('data',c=>d+=c);
      process.stdin.on('end',()=>{
        const j=JSON.parse(d);
        if(!j.comments||!j.comments.length){console.log('No comments');return;}
        j.comments.forEach(c=>{
          function extractText(node){
            if(!node)return '';
            if(node.type==='text')return node.text||'';
            if(node.content)return node.content.map(extractText).join(node.type==='paragraph'?'\n':'');
            return '';
          }
          console.log('---');
          console.log('Author:',c.author.displayName);
          console.log('Date:',c.created);
          console.log(extractText(c.body));
        });
      });"
}

board_update_description() {
  local issue_key="$1"
  local markdown="${2:-$(cat)}"

  local tmpfile payload_file
  tmpfile=$(mktemp)
  payload_file=$(mktemp)
  printf '%s' "$markdown" > "$tmpfile"

  node -e "
    const fs = require('fs');
    const md = fs.readFileSync(process.argv[1], 'utf8');
    const lines = md.split('\n');
    const content = [];
    let listItems = [];

    function flushList() {
      if (listItems.length > 0) {
        content.push({
          type: 'bulletList',
          content: listItems.map(text => ({
            type: 'listItem',
            content: [{ type: 'paragraph', content: [{ type: 'text', text }] }]
          }))
        });
        listItems = [];
      }
    }

    for (const line of lines) {
      if (line.startsWith('## ')) {
        flushList();
        content.push({ type: 'heading', attrs: { level: 2 }, content: [{ type: 'text', text: line.slice(3) }] });
      } else if (line.startsWith('### ')) {
        flushList();
        content.push({ type: 'heading', attrs: { level: 3 }, content: [{ type: 'text', text: line.slice(4) }] });
      } else if (line.match(/^- \[[ x]\] /)) {
        listItems.push(line.replace(/^- \[[ x]\] /, ''));
      } else if (line.startsWith('- ')) {
        listItems.push(line.slice(2));
      } else if (line.trim() === '') {
        flushList();
      } else {
        flushList();
        content.push({ type: 'paragraph', content: [{ type: 'text', text: line }] });
      }
    }
    flushList();
    if (content.length === 0) {
      content.push({ type: 'paragraph', content: [{ type: 'text', text: ' ' }] });
    }
    fs.writeFileSync(process.argv[2], JSON.stringify({ fields: { description: { type: 'doc', version: 1, content } } }));
  " "$tmpfile" "$payload_file"

  jira_curl -X PUT -H "$JIRA_AUTH_HEADER" -H "Content-Type: application/json" -d @"$payload_file" "$JIRA_BASE/issue/$issue_key"
  rm -f "$tmpfile" "$payload_file"
}

board_add_comment() {
  local issue_key="$1"
  local comment="${2:-$(cat)}"

  local payload_file
  payload_file=$(mktemp)
  node -e "
    const fs = require('fs');
    const text = process.argv[1];
    fs.writeFileSync(process.argv[2], JSON.stringify({
      body: { type: 'doc', version: 1, content: [{ type: 'paragraph', content: [{ type: 'text', text }] }] }
    }));
  " "$comment" "$payload_file"

  jira_curl -X POST -H "$JIRA_AUTH_HEADER" -H "Content-Type: application/json" -d @"$payload_file" "$JIRA_BASE/issue/$issue_key/comment"
  rm -f "$payload_file"
}

board_transition() {
  local issue_key="$1"
  local transition_id="$2"
  jira_curl -X POST \
    -H "$JIRA_AUTH_HEADER" \
    -H "Content-Type: application/json" \
    -d "{\"transition\":{\"id\":\"$transition_id\"}}" \
    "$JIRA_BASE/issue/$issue_key/transitions"
}

board_discover() {
  local response

  echo "=== Statuses ==="
  response=$(jira_curl -H "$JIRA_AUTH_HEADER" "$JIRA_BASE/project/$BOARD_PROJECT_KEY/statuses") || return 1
  echo "$response" | \
    node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);const seen=new Set();j.forEach(t=>t.statuses.forEach(s=>{if(!seen.has(s.id)){seen.add(s.id);console.log(s.id,'-',s.name)}}));})"

  echo ""
  echo "=== Transitions (from first issue) ==="
  local first_id
  response=$(jira_curl -X POST -H "$JIRA_AUTH_HEADER" -H "Content-Type: application/json" \
    -d "{\"jql\":\"project=$BOARD_PROJECT_KEY ORDER BY rank ASC\",\"maxResults\":1}" \
    "$JIRA_BASE/search/jql") || return 1
  first_id=$(echo "$response" | \
    node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);if(j.issues&&j.issues[0])console.log(j.issues[0].id);})")
  local first_key=""
  if [[ -n "$first_id" ]]; then
    first_key=$(board_get_card_key "$first_id")
  fi

  if [[ -n "$first_key" ]]; then
    response=$(jira_curl -H "$JIRA_AUTH_HEADER" "$JIRA_BASE/issue/$first_key/transitions") || return 1
    echo "$response" | \
      node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);j.transitions.forEach(t=>console.log(t.id,'-',t.name,'->',t.to.name,'(id:',t.to.id,')'));})"
  else
    echo "No issues found. Create an issue first, then run discover again."
  fi
}
