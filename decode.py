import base64
with open('encoded.txt', 'r') as f:
    encoded = f.read().strip()
    if encoded.startswith('"') and encoded.endswith('"'):
        encoded = encoded[1:-1]
    decoded = base64.b64decode(encoded).decode('utf-8')
    with open('devices_inventory.md', 'w', encoding='utf-8') as out:
        out.write(decoded)
print('Decoded successfully')
