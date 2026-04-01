#!/usr/bin/env bash
# Sorta.Fit — Jira adapter
# Implements the board_* interface for Jira Cloud

set -euo pipefail

JIRA_AUTH="$BOARD_EMAIL:$BOARD_API_TOKEN"
JIRA_BASE="https://$BOARD_DOMAIN/rest/api/3"

board_get_cards_in_status() {
  local status="$1"
  local max="${2:-10}"
  curl -s -X POST \
    -u "$JIRA_AUTH" \
    -H "Content-Type: application/json" \
    -d "{\"jql\":\"project=$BOARD_PROJECT_KEY AND status=$status ORDER BY rank ASC\",\"maxResults\":$max}" \
    "$JIRA_BASE/search/jql" | \
    node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);if(j.issues)j.issues.forEach(i=>console.log(i.id));})"
}

board_get_card_key() {
  local issue_id="$1"
  curl -s -u "$JIRA_AUTH" "$JIRA_BASE/issue/$issue_id" | \
    node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);console.log(j.key);})"
}

board_get_card_summary() {
  local issue_key="$1"
  curl -s -u "$JIRA_AUTH" "$JIRA_BASE/issue/$issue_key" | \
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
  curl -s -u "$JIRA_AUTH" "$JIRA_BASE/issue/$issue_key" | \
    node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);console.log(j.fields.summary);})"
}

board_get_card_description() {
  local issue_key="$1"
  curl -s -u "$JIRA_AUTH" "$JIRA_BASE/issue/$issue_key" | \
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
  curl -s -u "$JIRA_AUTH" "$JIRA_BASE/issue/$issue_key/comment" | \
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

  curl -s -X PUT -u "$JIRA_AUTH" -H "Content-Type: application/json" -d @"$payload_file" "$JIRA_BASE/issue/$issue_key"
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

  curl -s -X POST -u "$JIRA_AUTH" -H "Content-Type: application/json" -d @"$payload_file" "$JIRA_BASE/issue/$issue_key/comment"
  rm -f "$payload_file"
}

board_transition() {
  local issue_key="$1"
  local transition_id="$2"
  curl -s -X POST \
    -u "$JIRA_AUTH" \
    -H "Content-Type: application/json" \
    -d "{\"transition\":{\"id\":\"$transition_id\"}}" \
    "$JIRA_BASE/issue/$issue_key/transitions"
}

board_discover() {
  echo "=== Statuses ==="
  curl -s -u "$JIRA_AUTH" "$JIRA_BASE/project/$BOARD_PROJECT_KEY/statuses" | \
    node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);const seen=new Set();j.forEach(t=>t.statuses.forEach(s=>{if(!seen.has(s.id)){seen.add(s.id);console.log(s.id,'-',s.name)}}));})"

  echo ""
  echo "=== Transitions (from first issue) ==="
  local first_id
  first_id=$(curl -s -X POST -u "$JIRA_AUTH" -H "Content-Type: application/json" \
    -d "{\"jql\":\"project=$BOARD_PROJECT_KEY ORDER BY rank ASC\",\"maxResults\":1}" \
    "$JIRA_BASE/search/jql" | \
    node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);if(j.issues&&j.issues[0])console.log(j.issues[0].id);})")
  local first_key=""
  if [[ -n "$first_id" ]]; then
    first_key=$(board_get_card_key "$first_id")
  fi

  if [[ -n "$first_key" ]]; then
    curl -s -u "$JIRA_AUTH" "$JIRA_BASE/issue/$first_key/transitions" | \
      node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);j.transitions.forEach(t=>console.log(t.id,'-',t.name,'->',t.to.name,'(id:',t.to.id,')'));})"
  else
    echo "No issues found. Create an issue first, then run discover again."
  fi
}
