import discord
from discord.ext import commands, tasks
from discord import app_commands
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
from datetime import datetime
import re
import logging
import asyncio
import os
import subprocess
import concurrent.futures

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Replace with your own values
GUILD_ID = 000000000000000000								# server ID
CHANNEL_ID = 0000000000000000000							# text channel ID
LINKS_FILE = "monitored_links.txt"  							# File to store monitored links
FILTER_FILE = "filtered_words.txt"							# File to store filters
CHROMEDRIVER_PATH = "C:/Path/To/chromedriver.exe"  					# Provide the correct path to chromedriver
CHROME_BINARY_LOCATION = "C:/Program Files/Google/Chrome/Application/chrome.exe"  	# Update path if needed
filters = []

class LinkMonitor(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.check_for_new_offer.start()
        self.bot.loop.create_task(self.set_bot_status())  # Set bot status when cog is initialized

    def cog_unload(self):
        self.check_for_new_offer.cancel()
        self.executor.shutdown(wait=False)

    @tasks.loop(minutes=6)
    async def check_for_new_offer(self):
        options = Options()
        options.add_argument('--headless')                 
        options.binary_location = CHROME_BINARY_LOCATION
        options.executable_path = CHROMEDRIVER_PATH

        guild = self.bot.get_guild(GUILD_ID)
        if guild:
            channel = guild.get_channel(CHANNEL_ID)
            if channel:
                messages = [message async for message in channel.history(limit=35)]  # Limiting to the last 35 messages for efficiency
                sent_links = {msg.content.split('\n')[1] for msg in messages if len(msg.content.split('\n')) > 1}

                monitored_links = self.read_monitored_links()
                filtered_words = self.read_filtered_words()

                for ebay_url in monitored_links:
                    await self.bot.loop.run_in_executor(self.executor, self.process_ebay_url, ebay_url, sent_links, channel, options, filtered_words)

    def process_ebay_url(self, ebay_url, sent_links, channel, options, filtered_words):
        try:
            driver = webdriver.Chrome(options=options)
            driver.get(ebay_url)

            page_source = driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')
            offer_elements = soup.select('.aditem')

            for offer_element in offer_elements:
                title_element = offer_element.select_one('h2 a')
                if title_element:
                    offer_link = f'https://www.kleinanzeigen.de{title_element["href"]}'
                    if offer_link not in sent_links and not any(word in offer_link for word in filtered_words):
                        offer_title = title_element.get_text()

                        # Visit the offer's individual page to get extra information
                        driver.get(offer_link)
                        offer_page_source = driver.page_source
                        offer_soup = BeautifulSoup(offer_page_source, 'html.parser')

                        # Extract additional information from the individual offer page
                        extra_info_element = offer_soup.select_one('#viewad-extra-info')
                        if extra_info_element:
                            date_element = extra_info_element.select_one('div > span')
                            date_posted = date_element.get_text() if date_element else "Unknown Date"

                            # Convert date_posted to a datetime object
                            try:
                                offer_date = datetime.strptime(date_posted, "%d.%m.%Y").date()
                            except ValueError:
                                logger.error(f"Error parsing date: {date_posted}")
                                continue

                            # Get today's date
                            today = datetime.today().date()

                            # Skip offers that are not posted today
                            if offer_date < today:
                                continue

                            view_count_element = extra_info_element.select_one('#viewad-cntr-num')
                            view_count = view_count_element.get_text() if view_count_element else "Unknown Views"
                        else:
                            date_posted = "Unknown Date"
                            view_count = "Unknown Views"


                        # Log and send the new offer information
                        logger.info(f'Sending new offer: {offer_title} - {offer_link}')
                        message = (f'@everyone New offer: {offer_title}\n{offer_link}\n'
                               f'Date Posted: {date_posted}\nViews: {view_count}')
                        asyncio.run_coroutine_threadsafe(channel.send(message), self.bot.loop)
        except Exception as e:
            logger.error(f"Error processing {ebay_url}: {e}")
            asyncio.run_coroutine_threadsafe(channel.send(f"Critical error encountered: {e}. Bot may need a restart."), self.bot.loop)
        finally:
            driver.quit()

    def read_monitored_links(self):
        links = []
        if os.path.exists(LINKS_FILE):
            with open(LINKS_FILE, 'r') as file:
                links = [line.strip() for line in file]
        return links
    
    def read_filtered_words(self):
        words = []
        if os.path.exists(FILTER_FILE):
            with open(FILTER_FILE, 'r') as file:
                words = [line.strip() for line in file]
        return words

    def save_monitored_links(self, links):
        with open(LINKS_FILE, 'w') as file:
            for link in links:
                file.write(link + '\n')

    def save_filtered_words(self, words):
        with open(FILTER_FILE, 'w') as file:
            for word in words:
                file.write(word + '\n')  

    async def set_bot_status(self):
        await self.bot.wait_until_ready()  # Ensure the bot is connected before setting status
        await self.bot.change_presence(activity=discord.Game(name="looking for offers.. |-> !info <-"))
        logger.info(f'Bot status set.')            

    @app_commands.command(name="viewlink", description="View monitored links")
    async def viewlink(self, interaction: discord.Interaction):
        monitored_links = self.read_monitored_links()
        if monitored_links:
            links_str = "\n".join(f"{index+1}: {link}" for index, link in enumerate(monitored_links))
            await interaction.response.send_message(f"Monitored links:\n{links_str}")
        else:
            await interaction.response.send_message("No links are currently being monitored.")

    @app_commands.command(name="viewfilter", description="View filtered words")
    async def viewfilter(self, interaction: discord.Interaction):
        filtered_words = self.read_filtered_words()
        if filtered_words:
            filter_str = "\n".join(f"{index+1}: {word}" for index, word in enumerate(filtered_words))
            await interaction.response.send_message(f"Filtered Words:\n{filter_str}")
        else:
            await interaction.response.send_message("No filter set.")

    @app_commands.command(name="editlink", description="Edit monitored links")
    async def editlink(self, interaction: discord.Interaction, action: str, index: int = None, new_link: str = None):
        current_links = self.read_monitored_links()

        if action == "add" and new_link:
            current_links.append(new_link)
            self.save_monitored_links(current_links)
            await interaction.response.send_message(f"Added link: {new_link}")

        elif action == "remove" and index is not None:
            if 0 <= index-1 < len(current_links):
                removed_link = current_links.pop(index-1)
                self.save_monitored_links(current_links)
                await interaction.response.send_message(f"Removed link: {removed_link}")
            else:
                await interaction.response.send_message("Invalid index.")

        await self.viewlink(interaction)  # Display the updated list

    @app_commands.command(name="editfilter", description="Edit filtered words")
    async def editfilter(self, interaction: discord.Interaction, action: str, index: int = None, new_word: str = None):
        current_filters = self.read_filtered_words()

        if action == "add" and new_word:
            current_filters.append(new_word)
            current_filters = list(set(current_filters))
            self.save_filtered_words(current_filters)
            await interaction.response.send_message(f"Added filter: {new_word}")

        elif action == "remove" and index is not None:
            if 0 <= index-1 < len(current_filters):
                removed_word = current_filters.pop(index-1)
                self.save_filtered_words(current_filters)
                await interaction.response.send_message(f"Removed filter: {removed_word}")
            else:
                await interaction.response.send_message("Invalid index.")

        await self.viewfilter(interaction)  # Display the updated list

async def setup(bot):
    await bot.add_cog(LinkMonitor(bot))
