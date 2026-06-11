import sqlite3
import json
import os

db = sqlite3.connect('.code-review-graph/graph.db')
db.row_factory = sqlite3.Row

# Find the entry point
res = db.execute("SELECT qualified_name FROM nodes WHERE name='process_documents_with_duplicate_check' OR name='process_documents'").fetchall()
entry_points = [r[0] for r in res]

print(f"Entry points: {entry_points}")

visited = set()
edges_list = []

def traverse(node):
    if node in visited:
        return
    visited.add(node)
    
    # Get outgoing edges (CALLS, etc)
    res = db.execute("SELECT target_qualified, kind FROM edges WHERE source_qualified=? AND kind='CALLS'", (node,)).fetchall()
    for row in res:
        target = row['target_qualified']
        edges_list.append((node, target))
        traverse(target)

for ep in entry_points:
    traverse(ep)

# Get details about visited nodes
nodes_details = {}
for node in visited:
    res = db.execute("SELECT file_path, name, kind, line_start, line_end FROM nodes WHERE qualified_name=?", (node,)).fetchone()
    if res:
        nodes_details[node] = dict(res)

print("--- NODES ---")
for k, v in nodes_details.items():
    print(f"{v['name']} ({os.path.basename(v['file_path'])})")

print("\n--- EDGES ---")
for s, t in edges_list:
    s_name = nodes_details[s]['name'] if s in nodes_details else s
    t_name = nodes_details[t]['name'] if t in nodes_details else t
    print(f"{s_name} -> {t_name}")
