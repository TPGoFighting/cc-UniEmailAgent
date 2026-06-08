#!/bin/bash
# Test HermesAgent via SSH
SERVER="124.220.64.139"
KEY="/d/C_Game/123.pem"

echo "=== 1. Create task ==="
curl -s -X POST "http://$SERVER:8070/api/chat" \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"用中文回复：成功了\",\"task_id\":\"ws-final\"}"
echo ""

echo "=== 2. Create WS listener (SSH) ==="
ssh -i "$KEY" "root@$SERVER" "cd /home/ubuntu/uniemail/backend && source venv/bin/activate && timeout 45 python3 -c \"
import asyncio, json, websockets
async def t():
    async with websockets.connect('ws://127.0.0.1:8070/ws/ws-final') as ws:
        while True:
            try:
                data = await asyncio.wait_for(ws.recv(), timeout=30)
                p = json.loads(data)
                t = p.get('type','?')
                m = str(p.get('message',''))[:200]
                print(f'[{t}] {m}')
                if t in ('done','error'): break
            except asyncio.TimeoutError:
                break
asyncio.run(t())
\"" 2>&1 | tail -10
