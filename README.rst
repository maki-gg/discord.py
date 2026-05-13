discord.py
==========

.. image:: https://discord.com/api/guilds/336642139381301249/embed.png
   :target: https://discord.gg/r3sSKJJ
   :alt: Discord server invite
.. image:: https://img.shields.io/pypi/v/discord.py.svg
   :target: https://pypi.python.org/pypi/discord.py
   :alt: PyPI version info
.. image:: https://img.shields.io/pypi/pyversions/discord.py.svg
   :target: https://pypi.python.org/pypi/discord.py
   :alt: PyPI supported Python versions

A modern, easy to use, feature-rich, and async ready API wrapper for Discord written in Python.

Key Features
-------------

- Modern Pythonic API using ``async`` and ``await``.
- Proper rate limit handling.
- Optimised in both speed and memory.

Installing
----------

**Python 3.8 or higher is required**

To install the library without full voice support, you can just run the following command:

.. note::

    A `Virtual Environment <https://docs.python.org/3/library/venv.html>`__ is recommended to install
    the library, especially on Linux where the system Python is externally managed and restricts which
    packages you can install on it.


.. code:: sh

    # Linux/macOS
    python3 -m pip install -U discord.py

    # Windows
    py -3 -m pip install -U discord.py

Otherwise to get voice support you should run the following command:

.. code:: sh

    # Linux/macOS
    python3 -m pip install -U "discord.py[voice]"

    # Windows
    py -3 -m pip install -U discord.py[voice]


To install the development version, do the following:

.. code:: sh

    $ git clone https://github.com/Rapptz/discord.py
    $ cd discord.py
    $ python3 -m pip install -U .[voice]


Optional Packages
~~~~~~~~~~~~~~~~~~

* `PyNaCl <https://pypi.org/project/PyNaCl/>`__ (for voice support)
* `redis <https://pypi.org/project/redis/>`__ (for Redis guild caching)

Please note that when installing voice support on Linux, you must install the following packages via your favourite package manager (e.g. ``apt``, ``dnf``, etc) before running the above commands:

* libffi-dev (or ``libffi-devel`` on some systems)
* python-dev (e.g. ``python3.8-dev`` for Python 3.8)

Quick Example
--------------

.. code:: py

    import discord

    class MyClient(discord.Client):
        async def on_ready(self):
            print('Logged on as', self.user)

        async def on_message(self, message):
            # don't respond to ourselves
            if message.author == self.user:
                return

            if message.content == 'ping':
                await message.channel.send('pong')

    intents = discord.Intents.default()
    intents.message_content = True
    client = MyClient(intents=intents)
    client.run('token')

Bot Example
~~~~~~~~~~~~~

.. code:: py

    import discord
    from discord.ext import commands

    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix='>', intents=intents)

    @bot.command()
    async def ping(ctx):
        await ctx.send('pong')

    bot.run('token')

You can find more examples in the examples directory.

Redis Caching
--------------------

Large bots accumulate significant memory over time because discord.py holds all guild data (members,
channels, roles, threads) strongly in memory for every guild. This fork adds optional Redis-backed
caching to offload that data and keep only the most recently active guilds fully loaded in memory.

To enable it, install the extra dependency and pass a ``RedisCacheOptions`` instance to your bot:

.. code:: sh

    # Linux/macOS
    python3 -m pip install -U "discord.py[redis]"

    # Windows
    py -3 -m pip install -U discord.py[redis]

.. code:: py

    import discord
    from discord.ext import commands

    intents = discord.Intents.default()
    intents.message_content = True

    bot = commands.Bot(
        command_prefix='!',
        intents=intents,
        redis_cache=discord.RedisCacheOptions(
            uri='redis://localhost:6379',
            max_memory_guilds=500,  # keep 500 guilds fully loaded and evict the rest to Redis
        ),
    )

    bot.run('token')

``RedisCacheOptions`` accepts per-entity-type TTLs (``guild_ttl``, ``member_ttl``,
``channel_ttl``, ``role_ttl``, ``thread_ttl``, ``emoji_ttl``, ``sticker_ttl``). Each TTL
controls how long a guild's entire collection of that entity type lives in Redis, for example,
a shorter ``member_ttl`` means that when a guild goes completely quiet, its member data is
evicted from Redis sooner than its channel or role data. TTLs apply to the whole collection per
guild, not to individual inactive members within an active guild. All values default to sensible
values for bots running ~1000 guilds per shard.

When a guild is evicted from memory its sub-entity collections (members, channels, roles, threads)
are cleared and the guild object becomes a thin shell. The library automatically schedules a
``guild.load()`` the moment the next gateway event for that guild arrives, so the guild
self-heals within the same event loop tick. The first event after eviction may still observe empty
collections, all subsequent events will see the fully restored guild.

``guild.load()`` tries Redis first. If the Redis TTL has expired (e.g. on a long-running bot that
hasn't reconnected in days), it falls back to the Discord REST API, fetches the guild's channels
and roles, re-warms the Redis cache, and populates memory, all transparently. Members are not
fetched via REST since paginating through large member lists on every cache miss would be
prohibitive; they re-populate naturally via gateway events as users interact.

You can also call ``await guild.load()`` proactively wherever you need guaranteed access to guild
data. Use ``guild.is_loaded()`` to check whether a guild currently has its data in memory.

.. note::

    Redis connection failures raise immediately at startup (before ``setup_hook`` runs) rather
    than degrading silently. Ensure your Redis instance is reachable before starting the bot.

Links
------

- `Documentation <https://discordpy.readthedocs.io/en/latest/index.html>`_
- `Official Discord Server <https://discord.gg/r3sSKJJ>`_
- `Discord API <https://discord.gg/discord-api>`_
