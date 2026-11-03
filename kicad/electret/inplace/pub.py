"""Publish one MQTT message as sbgame-audio: pub.py TOPIC PAYLOAD"""
import asyncio,sys
from pathlib import Path
import aiomqtt
async def m():
    async with aiomqtt.Client("localhost",username="sbgame-audio",password=Path("/etc/sbgame/mqtt-audio.pass").read_text().strip(),identifier="claude-pub") as c:
        await c.publish(sys.argv[1],sys.argv[2])
asyncio.run(m())
