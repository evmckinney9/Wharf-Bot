import discord
from discord.ext import commands
from datetime import timedelta
import requests
import json
import random  # Import random instead of numpy
from io import BytesIO
from PIL import Image
import aiohttp

class Movies(commands.Cog, name="movies"):
    def __init__(self, bot) -> None:
        self.bot = bot

    async def combine_images(self, url1, url2):
        async with aiohttp.ClientSession() as session:
            async with session.get(url1) as resp1, session.get(url2) as resp2:
                img1_data = await resp1.read()
                img2_data = await resp2.read()

                img1 = Image.open(BytesIO(img1_data))
                img2 = Image.open(BytesIO(img2_data))

                # Resize both images to have the same height
                img1 = img1.resize((300, 450))
                img2 = img2.resize((300, 450))

                # Combine the two images side by side
                total_width = img1.width + img2.width
                max_height = max(img1.height, img2.height)
                combined_img = Image.new('RGB', (total_width, max_height))

                combined_img.paste(img1, (0, 0))
                combined_img.paste(img2, (img1.width, 0))

                # Save the combined image to BytesIO
                img_byte_array = BytesIO()
                combined_img.save(img_byte_array, format='PNG')
                img_byte_array.seek(0)
                return img_byte_array

    @commands.hybrid_command(
        name="movie_poll",
        description="Create a poll to choose between two random movies with posters.",
    )
    async def movie_poll(self, context: commands.Context) -> None:
        # Example TMDB API call to retrieve movie posters
        list_id = "8426901"
        url = f"https://api.themoviedb.org/3/list/{list_id}?language=en-US"

        tmdb_api_key = self.bot.config["tmdb_api_key"]
        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {tmdb_api_key}"
        }

        response = requests.get(url, headers=headers)
        data = json.loads(response.text)
        num_pages = data["total_pages"] - 1

        # Pick two random pages and two random movie indices
        rand_page = random.sample(range(1, num_pages + 1), 2)
        rand_entry = random.sample(range(20), 2)

        # Fetch movie details from random pages
        entry0 = json.loads(requests.get(f"{url}&page={rand_page[0]}", headers=headers).text)
        entry0 = entry0["items"][rand_entry[0] % len(entry0["items"])]
        
        entry1 = json.loads(requests.get(f"{url}&page={rand_page[1]}", headers=headers).text)
        entry1 = entry1["items"][rand_entry[1] % len(entry1["items"])]

        # Movie poster URLs
        poster_prefix = "https://image.tmdb.org/t/p/original"
        poster0 = poster_prefix + entry0["poster_path"]
        poster1 = poster_prefix + entry1["poster_path"]

        # Movie titles and overviews
        movie_title0 = entry0['title']
        movie_title1 = entry1['title']
        movie_overview0 = entry0['overview']
        movie_overview1 = entry1['overview']

        # Combine the two posters into one image
        combined_image = await self.combine_images(poster0, poster1)

        # Create an embed for both movies
        embed = discord.Embed()
        embed.add_field(name=movie_title0, value=movie_overview0, inline=False)
        embed.add_field(name=movie_title1, value=movie_overview1, inline=False)

        # Attach the combined image
        file = discord.File(combined_image, filename="combined.png")
        embed.set_image(url="attachment://combined.png")

        # Send the embed with movie details and combined image
        await context.send(embed=embed, file=file)

        # Create and send the poll
        poll = discord.Poll(
            question="Which movie would you like to watch?",
            duration=timedelta(minutes=3),
            multiple=False  # Only allow one vote
        )
        
        poll.add_answer(text=f"{movie_title0}")
        poll.add_answer(text=f"{movie_title1}")
        await context.send(poll=poll)


# Setup the cog
async def setup(bot) -> None:
    await bot.add_cog(Movies(bot))
