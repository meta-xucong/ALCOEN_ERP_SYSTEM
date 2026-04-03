#!/usr/bin/env python3
import subprocess
import json
import base64

# 使用gh CLI获取文件内容
result = subprocess.run(
    ['gh', 'api', 'repos/meta-xucong/openclaw-workspace/contents/memory/devices_inventory.md'],
    capture_output=True,
    text=True
)

data = json.loads(result.stdout)
content = base64.b64decode(data['content']).decode('utf-8')

# 保存到文件
with open('devices_inventory.md', 'w', encoding='utf-8') as f:
    f.write(content)

# Write to file only, don't print
pass
