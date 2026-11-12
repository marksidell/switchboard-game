"""Hold stations off-hook with a game heartbeat; log state; release on SIGTERM."""
import asyncio, signal, sys, time
from pathlib import Path
import aiomqtt
ST = [int(x) for x in sys.argv[1:]] or [1, 24]
P = "sbgame/"
async def main():
    pw = Path("/etc/sbgame/mqtt-audio.pass").read_text().strip()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for s in (signal.SIGTERM, signal.SIGINT): loop.add_signal_handler(s, stop.set)
    async with aiomqtt.Client("localhost", username="sbgame-audio", password=pw, identifier="claude-hold") as c:
        for n in ST:
            for t in ("hook", "peer", "op", "lifted", "play"):
                await c.subscribe(f"{P}station/{n}/{t}")
        await c.subscribe(P + "ctl/+")
        async def beat():
            while not stop.is_set():
                await c.publish(P + "ctl/game_heartbeat", f"{time.time():.1f}")
                for n in ST: await c.publish(f"{P}station/{n}/hook/set", "on") if beat.first else None
                beat.first = False
                await asyncio.sleep(1)
        beat.first = True
        async def rx():
            async for m in c.messages:
                if "heartbeat" in str(m.topic): continue
                print(f"{time.strftime('%H:%M:%S')} {m.topic} {m.payload.decode()}", flush=True)
        tb, tr = asyncio.create_task(beat()), asyncio.create_task(rx())
        await stop.wait()
        tb.cancel()
        for n in ST: await c.publish(f"{P}station/{n}/hook/set", "off")
        await asyncio.sleep(1.5)
        tr.cancel()
asyncio.run(main())
