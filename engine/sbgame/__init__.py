"""The 551 switchboard simulator's game program.

game_control.md is the specification; mqtt.md owns the topics. The pieces:

    board    the state of the switchboard and the audio program, from MQTT
    link     the connection: reconnect, birth and will, heartbeat, page commands
    scenes   call flows, one coroutine per scene shape
"""
