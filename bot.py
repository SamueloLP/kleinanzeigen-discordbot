import discord
from discord.ext import commands
import subprocess
import asyncio

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True  # Enable the message content intent

class MyBot(commands.Bot):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def setup_hook(self):
        await self.load_extension('link_monitor')
        await bot.tree.sync()  # Synchronize the commands with Discord

bot = MyBot(command_prefix=commands.when_mentioned_or(''), intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}!')
    print(f'Bot is ready and commands are synchronized.')

async def main():
    async with bot:
        await bot.start('token')	# Discord Token

if __name__ == "__main__":
    asyncio.run(main())
