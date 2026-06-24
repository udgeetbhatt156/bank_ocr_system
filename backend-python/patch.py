import re

with open("app/services/statement_templates.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add to BANK_KEY_MAP
new_bank_key = '    "stellar":           ["stellar_bank_v1"],\n}'
content = re.sub(r'\}', new_bank_key, content, count=1, flags=re.MULTILINE)  # Find the end of BANK_KEY_MAP

# Let's do it safer:
with open("app/services/statement_templates.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

out = []
in_templates = False
in_bank_map = False

for line in lines:
    if line.strip() == "BANK_KEY_MAP: Dict[str, List[str]] = {":
        in_bank_map = True
        
    if in_bank_map and line.startswith("}"):
        out.append('    "stellar":           ["stellar_bank_v1"],\n')
        in_bank_map = False
        
    if line.strip() == "# Generic fallback templates":
        out.append('    StatementTemplate(\n')
        out.append('        template_id="stellar_bank_v1",\n')
        out.append('        bank_name="Stellar Bank",\n')
        out.append('        layout_family="sectioned_deposits_withdrawals",\n')
        out.append('        parser_format="stellar_bank",\n')
        out.append('        bank_patterns=[\n')
        out.append('            "stellar bank",\n')
        out.append('            "stellar",\n')
        out.append('        ],\n')
        out.append('        header_keywords=[\n')
        out.append('            "statement dates",\n')
        out.append('            "previous balance",\n')
        out.append('            "total deposits",\n')
        out.append('            "total withdrawals",\n')
        out.append('            "current balance",\n')
        out.append('        ],\n')
        out.append('        amount_rules={},\n')
        out.append('        stop_keywords=[],\n')
        out.append('        sample_files=["Stellar Bank.pdf"],\n')
        out.append('    ),\n')
        
    out.append(line)

with open("app/services/statement_templates.py", "w", encoding="utf-8") as f:
    f.writelines(out)
