"""The 551 switchboard simulator's game program.

game_control.md is the specification; mqtt.md owns the topics. engine/README.md
lists the modules; the spine of the program is

    main     start-up and shutdown
    link     the connection: reconnect, birth and will, heartbeat, page commands
    board    the state of the switchboard and the audio program, from MQTT
    game     the game: dealing, pacing, tallies, page commands
    flows    one coroutine per scene shape, built on scenes' say() and hear()

The Stream Deck (streamdeck), the simulator (simulate), the board test
(boardtest) and the public address check (netcheck) are programs of their own.
"""
