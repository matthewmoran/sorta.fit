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
    else
      log_error "Response: ${body:0:200}"
    fi
    return 1
  fi

  printf '%s' "$body"
}

board_get_cards_in_status() {
  local status="$1"
  local max="${2:-10}"
  local start_at="${3:-0}"
  if [[ -z "$status" ]]; then
    log_error "No status ID configured for this runner. Check RUNNER_*_FROM in .env."
    return 1
  fi
  local response
  response=$(jira_curl -X POST \
    -H "$JIRA_AUTH_HEADER" \
    -H "Content-Type: application/json" \
    -d "{\"jql\":\"project=$BOARD_PROJECT_KEY AND status=$status ORDER BY rank ASC\",\"maxResults\":$max}" \
    "$JIRA_BASE/search/jql?startAt=$start_at") || return 1
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
          if(node.type==='hardBreak')return '\n';
          if(!node.content)return '';
          if(node.type==='doc')return node.content.map(extractText).join('\n\n');
          if(node.type==='heading'){
            var lvl=(node.attrs&&node.attrs.level)||2;
            var p='';for(var i=0;i<lvl;i++)p+='#';
            return p+' '+node.content.map(extractText).join('');
          }
          if(node.type==='bulletList'||node.type==='orderedList')return node.content.map(extractText).join('\n');
          if(node.type==='listItem')return '- '+node.content.map(extractText).join('\n');
          return node.content.map(extractText).join('');
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
            if(node.type==='hardBreak')return '\n';
            if(!node.content)return '';
            if(node.type==='doc')return node.content.map(extractText).join('\n\n');
            if(node.type==='heading'){
              var lvl=(node.attrs&&node.attrs.level)||2;
              var p='';for(var i=0;i<lvl;i++)p+='#';
              return p+' '+node.content.map(extractText).join('');
            }
            if(node.type==='bulletList'||node.type==='orderedList')return node.content.map(extractText).join('\n');
            if(node.type==='listItem')return '- '+node.content.map(extractText).join('\n');
            return node.content.map(extractText).join('');
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

  jira_curl -X PUT -H "$JIRA_AUTH_HEADER" -H "Content-Type: application/json" -d @"$payload_file" "$JIRA_BASE/issue/$issue_key" > /dev/null
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

  jira_curl -X POST -H "$JIRA_AUTH_HEADER" -H "Content-Type: application/json" -d @"$payload_file" "$JIRA_BASE/issue/$issue_key/comment" > /dev/null
  rm -f "$payload_file"
}

board_transition() {
  local issue_key="$1"
  local transition_id="$2"
  jira_curl -X POST \
    -H "$JIRA_AUTH_HEADER" \
    -H "Content-Type: application/json" \
    -d "{\"transition\":{\"id\":\"$transition_id\"}}" \
    "$JIRA_BASE/issue/$issue_key/transitions" > /dev/null
}

# Get a card's current status (name and ID)
# Output format: STATUS_NAME|STATUS_ID (e.g., "In Progress|10000", "Done|10037")
# Other adapters (Linear, GitHub Issues) must implement this for label-based dep checks.
board_get_card_status() {
  local issue_key="$1"
  local response
  response=$(jira_curl -H "$JIRA_AUTH_HEADER" "$JIRA_BASE/issue/$issue_key?fields=status") || return 1
  echo "$response" | \
    node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);const s=j.fields&&j.fields.status;if(s)console.log(s.name+'|'+s.id);});"
}

# Get a card's issue links, parent, subtasks, and dependency labels
# Output format: one pipe-delimited line per link:
#   TYPE|DIRECTION|LINKED_KEY|LINKED_STATUS_NAME|LINKED_STATUS_ID
# Where:
#   TYPE = blocks, parent, subtask, or label
#   DIRECTION = inward (blocking this card) or outward (blocked by this card)
#   LINKED_KEY = the linked issue key (e.g., TEST-5)
#   LINKED_STATUS_NAME = human-readable status (e.g., "In Progress") or empty
#   LINKED_STATUS_ID = Jira status ID (e.g., "10000") or empty
# Other adapters (Linear, GitHub Issues) must implement this with the same output format.
board_get_card_links() {
  local issue_key="$1"
  local response
  response=$(jira_curl -H "$JIRA_AUTH_HEADER" "$JIRA_BASE/issue/$issue_key?fields=issuelinks,parent,subtasks,labels") || return 1
  echo "$response" | \
    node -e "
      let d='';
      process.stdin.on('data',c=>d+=c);
      process.stdin.on('end',()=>{
        const j=JSON.parse(d);
        const f=j.fields;
        // Issue links (blocks / is-blocked-by / depends-on)
        if(f.issuelinks){
          f.issuelinks.forEach(link=>{
            const typeName=(link.type&&link.type.name)||'';
            if(!/block|depend/i.test(typeName))return;
            if(link.inwardIssue){
              const k=link.inwardIssue.key;
              const s=link.inwardIssue.fields&&link.inwardIssue.fields.status;
              console.log('blocks|inward|'+k+'|'+(s?s.name:'')+'|'+(s?s.id:''));
            }
            if(link.outwardIssue){
              const k=link.outwardIssue.key;
              const s=link.outwardIssue.fields&&link.outwardIssue.fields.status;
              console.log('blocks|outward|'+k+'|'+(s?s.name:'')+'|'+(s?s.id:''));
            }
          });
        }
        // Parent
        if(f.parent){
          const k=f.parent.key;
          const s=f.parent.fields&&f.parent.fields.status;
          console.log('parent|inward|'+k+'|'+(s?s.name:'')+'|'+(s?s.id:''));
        }
        // Subtasks
        if(f.subtasks){
          f.subtasks.forEach(sub=>{
            const k=sub.key;
            const s=sub.fields&&sub.fields.status;
            console.log('subtask|outward|'+k+'|'+(s?s.name:'')+'|'+(s?s.id:''));
          });
        }
        // Labels (depends-on:KEY or blocked)
        if(f.labels){
          f.labels.forEach(label=>{
            if(/^depends-on:/i.test(label)){
              const depKey=label.split(':')[1].trim();
              console.log('label|inward|'+depKey+'|Unknown|');
            }else if(/^blocked$/i.test(label)){
              console.log('label|inward||Unknown|');
            }
          });
        }
      });"
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
