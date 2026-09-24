"""Live test of Link against a real Mosquitto, with a fake controller client.

Checks: game state before birth, retained state arrives, sync is sent,
commands echo, a page command reaches the handler, the heartbeat carries host
time, heartbeat loss is detected, broker restart reconnects and resyncs, and
the will fires when the game program vanishes.
"""

import asyncio
import logging
import subprocess
import sys

import aiomqtt

from sbgame.board import Board, Offline
from sbgame.link import Hw, Link

PORT = 18830
logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                    format="%(relativeCreated)6.0f %(name)-6s %(message)s")
log = logging.getLogger("test")


def broker():
    return subprocess.Popen(["mosquitto", "-p", str(PORT)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class FakeControl:
    def __init__(self):
        self.beating = True
        self.syncs = 0

    async def run(self):
        while True:
            try:
                will = aiomqtt.Will("sbgame/ctl/status", "offline", qos=1, retain=True)
                async with aiomqtt.Client("localhost", PORT, identifier="sbgame-esp32",
                                          will=will, keepalive=5) as c:
                    await c.publish("sbgame/ctl/status", "online", qos=1, retain=True)
                    await c.publish("sbgame/ctl/audio_status", "online", qos=1, retain=True)
                    await c.publish("sbgame/trunk/3/seize", "on", qos=1, retain=True)
                    await c.subscribe("sbgame/station/+/hook/set", qos=1)
                    await c.subscribe("sbgame/ctl/sync", qos=1)
                    beat = asyncio.create_task(self._beat(c))
                    try:
                        async for m in c.messages:
                            t = m.topic.value
                            if t == "sbgame/ctl/sync":
                                self.syncs += 1
                            elif t.endswith("/hook/set"):
                                await c.publish(t.removesuffix("/set"), m.payload, qos=1, retain=True)
                    finally:
                        beat.cancel()
            except aiomqtt.MqttError:
                await asyncio.sleep(0.5)

    async def _beat(self, c):
        n = 0
        while True:
            if self.beating:
                n += 1
                await c.publish("sbgame/ctl/esp_heartbeat", str(n), qos=1)
            await asyncio.sleep(1)


async def watcher(seen: list):
    """Records what the page would see of the game program, in order."""
    while True:
        try:
            async with aiomqtt.Client("localhost", PORT, identifier="watcher") as c:
                await c.subscribe("sbgame/ctl/game_status", qos=1)
                await c.subscribe("sbgame/ctl/game_heartbeat", qos=1)
                await c.subscribe("sbgame/game/run", qos=1)
                async for m in c.messages:
                    seen.append((m.topic.value, m.payload.decode()))
        except aiomqtt.MqttError:
            await asyncio.sleep(0.3)


async def main():
    p = broker()
    await asyncio.sleep(0.5)
    control = FakeControl()
    b = Board()
    seen: list = []
    commands: list = []

    async def on_birth(link):
        await link.state("game/run", "off")

    async def on_command(name, payload):
        commands.append((name, payload))
        await link.state(f"game/{name}", payload)  # the echo

    link = Link(b, "localhost", PORT, username=None, on_birth=on_birth, on_command=on_command)
    hw = Hw(link)
    wt = asyncio.create_task(watcher(seen))
    await asyncio.sleep(0.3)
    tasks = [asyncio.create_task(control.run()), asyncio.create_task(link.run())]

    await b.wait_live(5)
    print("live: control", b.control_up, "audio", b.audio_up, "| trunk/3/seize =", b.get("trunk/3/seize"))
    await asyncio.sleep(0.3)
    print("syncs received by control:", control.syncs)
    assert control.syncs >= 1

    order = [t for t, _ in seen if t != "sbgame/ctl/game_heartbeat"]
    print("page saw, in order:", order[:2])
    assert order[:2] == ["sbgame/game/run", "sbgame/ctl/game_status"], "state before birth"
    beats = [float(v) for t, v in seen if t == "sbgame/ctl/game_heartbeat"]
    import time as _t
    assert beats and abs(beats[-1] - _t.time()) < 5, beats
    print("heartbeat carries host time:", beats[-1])

    async with aiomqtt.Client("localhost", PORT, identifier="page") as page:
        await page.publish("sbgame/game/run/set", "on", qos=1)
    for _ in range(20):
        await asyncio.sleep(0.05)
        if commands: break
    print("page command reached handler:", commands)
    assert commands == [("run", "on")]
    await asyncio.sleep(0.2)
    assert b.get("game/run") == "", "game's own state stays out of Board"
    assert ("sbgame/game/run", "on") in seen, "echo published"

    await hw.hook(7, True)
    await b.wait_until(lambda b: b.on("station/7/hook"), 2)
    print("hook echo ok")

    print("-- stop control heartbeat")
    control.beating = False
    try:
        await b.wait_until(lambda b: False, 5)
    except Offline as e:
        print("wait failed with Offline:", e)
    s0 = control.syncs
    control.beating = True
    await b.wait_live(3)
    await asyncio.sleep(0.3)
    print("control back; extra syncs:", control.syncs - s0)
    assert control.syncs > s0

    print("-- kill broker")
    p.terminate(); p.wait()
    for i in range(40):
        await asyncio.sleep(0.25)
        if not b.broker_up: break
    print(f"noticed after {(i+1)*0.25:.2f}s;", "broker_up", b.broker_up, "control_up", b.control_up)
    assert not b.control_up
    p = broker()
    await b.wait_live(15)
    print("reconnected; live again; trunk/3/seize =", b.get("trunk/3/seize"))

    print("-- game program vanishes without disconnecting")
    asyncio.get_running_loop().set_exception_handler(lambda loop, ctx: None)  # noise from the cut socket
    link._client._client._sock.close()  # drop the TCP connection under it
    tasks[1].cancel()
    for _ in range(40):
        await asyncio.sleep(0.25)
        if ("sbgame/ctl/game_status", "offline") in seen: break
    print("will fired:", ("sbgame/ctl/game_status", "offline") in seen)
    assert ("sbgame/ctl/game_status", "offline") in seen

    for t in tasks + [wt]:
        t.cancel()
    p.terminate()
    print("all passed")


asyncio.run(main())
