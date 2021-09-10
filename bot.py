import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import os
import re
import time
from types import SimpleNamespace

import discord
from discord.ext import tasks
from selenium.common.exceptions import TimeoutException

from jackbox_scraper import ContentLoader

client = discord.Client(max_messages=1000000)
pattern = re.compile(r"^https?://games\.jackbox\.tv/artifact/.+/[0-9a-f]+/$")
EMOJI = SimpleNamespace(**{
    "RERUN": "🔄",
    "DELETE": "🗑",
    "LETTER": "💌"
})
TEXT_NUM_ARTIFACTS = "Number of artifacts"
TEXT_NO_ARTIFACTS = "No artifacts found!"
TEXT_NO_ARTIFACTS_VALUE = ":("
TEXT_REQUESTER = "Requested by"
TEXT_GAME_LINK = "Game id"


BIRTHDAY_RAN = False


@tasks.loop(seconds=5)
async def send_birthday_message():
    now = datetime.utcnow()
    global BIRTHDAY_RAN
    if not BIRTHDAY_RAN and now.minute == 0 and now.hour == 22 and now.day == 10 and now.month == 9:
        channel = await client.fetch_channel(774005317083332680)
        await channel.send("Happy birthday <@131498471080460288> :partying_face: <:gaybill:837775959658201098>")
        await channel.send("https://giphy.com/gifs/reaction-cute-party-4QFdKexMLIA2okeecG")
        await channel.send("<:janiuff:880910588790849596> <:invjani:840199254362423366> <:janiowo:840546727324549130>")
        await client.change_presence(
            activity=discord.Activity(type=discord.ActivityType.playing, name="Happy birthday Jani!")
        )
        print("executed", now)
        BIRTHDAY_RAN = True


async def asyncify(func):
    return await asyncio.get_event_loop().run_in_executor(
        ThreadPoolExecutor(), func)


@client.event
async def on_ready():
    print('We have logged in as {0.user} - birthday edition'.format(client))
    await client.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="Jackbox results"))
    send_birthday_message.start()


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return

    if not pattern.match(message.content):
        return
    await load_and_send(message.content, message.channel, message.author.id)


@client.event
async def on_raw_reaction_add(payload: discord.raw_models.RawReactionActionEvent):

    if payload.user_id == client.user.id:
        return
    channel: discord.TextChannel = await client.fetch_channel(payload.channel_id)
    message = await channel.fetch_message(payload.message_id)
    if message.author.id != client.user.id:
        return
    if not isinstance(payload.emoji, discord.PartialEmoji):
        return
    emoji: discord.PartialEmoji = payload.emoji
    existing_reaction = [x for x in message.reactions if x.emoji == emoji.name]
    if len(existing_reaction) != 1 or not existing_reaction[0].me:
        return
    # permission check
    if emoji.name in (EMOJI.DELETE, EMOJI.RERUN) and not await check_message_perms(message, payload.user_id):
        return
    user = await client.fetch_user(payload.user_id)
    # check if it's an embed message
    if len(message.embeds) != 1:
        return
    embed = message.embeds[0]
    if not embed.fields:
        return
    field_artifacts = [x for x in embed.fields if x.name in (TEXT_NUM_ARTIFACTS, TEXT_NO_ARTIFACTS)]
    field_requester = [x for x in embed.fields if x.name == TEXT_REQUESTER]
    field_link = [x for x in embed.fields if x.name == TEXT_GAME_LINK]
    if any([len(x) != 1 for x in (field_artifacts, field_requester, field_link)]):
        return
    field_artifacts = field_artifacts[0]
    field_requester = field_requester[0]
    field_link = field_link[0]
    num_artifacts = 0
    if field_artifacts.value != TEXT_NO_ARTIFACTS_VALUE:
        num_artifacts += int(field_artifacts.value)
    if emoji.name == EMOJI.DELETE:
        await delete_result(message, num_artifacts)
    elif emoji.name == EMOJI.RERUN:
        url = field_link.value.split("](")[1][:-1]
        await delete_result(message, num_artifacts)
        await load_and_send(url, message.channel, payload.user_id)
    elif emoji.name == EMOJI.LETTER:
        if user.dm_channel is None:
            await user.create_dm()
        await message.channel.send(f"{EMOJI.LETTER} hey <@{user.id}>, check your DMs!", reference=message, delete_after=10)
        dm_msg = None
        for msg in await get_result_messages(message, num_artifacts):
            dm_msg = await user.dm_channel.send(content=msg.content, embed=msg.embeds[0] if msg.embeds else None)
        if dm_msg:
            await add_reaction_controls(dm_msg)
    # TODO lock emoji
    else:
        print("warning: unknown reaction")


async def add_reaction_controls(message):
    for reaction in (EMOJI.RERUN, EMOJI.DELETE, EMOJI.LETTER):
        await message.add_reaction(reaction)


async def check_message_perms(message: discord.Message, user_id):
    if isinstance(message.channel, discord.DMChannel):
        return True
    member = await message.channel.guild.fetch_member(user_id)
    perms: discord.Permissions = member.permissions_in(message.channel)
    return perms.manage_messages or perms.administrator


async def load_and_send(url, channel, author_id):
    start_time = time.time()
    summary = discord.Embed()
    summary.add_field(name=TEXT_NO_ARTIFACTS, value=TEXT_NO_ARTIFACTS_VALUE, inline=True)
    summary.add_field(name=TEXT_REQUESTER, value=f"<@{author_id}>", inline=True)
    summary.add_field(
        name=TEXT_GAME_LINK,
        value=f"[{url.split('/artifact/')[1][:-1]}]({url})",
        inline=False)
    # noinspection PyBroadException
    wait_msg = await channel.send("downloading game data, hang on!")
    try:
        loader = await asyncify(lambda: ContentLoader(url))
        embeds = await asyncify(loader.get_messages)
        await asyncify(loader.driver.quit)
        await wait_msg.delete()
        for embed in embeds:
            await channel.send(**embed)
            await asyncio.sleep(0.5)
        summary.set_field_at(0, name=TEXT_NUM_ARTIFACTS, value=str(len(embeds)), inline=True)
        summary.title = "Success!"
        summary.description = f"Detected a game of {loader.title}."
        summary.set_thumbnail(url=loader.title_image)
    except Exception as e:
        await wait_msg.delete()
        summary.title = "Error!"
        summary.description = f"```\n{str(e)}```"
        summary.set_thumbnail(url="https://www.freeiconspng.com/uploads/sign-red-error-icon-1.png")
        raise

        # return
    finally:
        summary.set_footer(text=f"Query time: {str(round(time.time() - start_time, 3))} seconds")
        summary_msg = await channel.send(embed=summary)
        await add_reaction_controls(summary_msg)


async def delete_result(message: discord.Message, num_messages):
    for msg in await get_result_messages(message, num_messages):
        await msg.delete()


async def get_result_messages(message: discord.Message, num_messages):
    for limit in range(100, 1000, 100):
        messages = [x for x in await message.channel.history(limit=100, before=message).flatten() if
                    x.author.id == client.user.id]
        if len(messages) >= num_messages:
            break
    else:
        # TODO messages not found -> error message?
        return []
    return messages[:num_messages] + [message]


client.run(os.environ["DISCORD_TOKEN"])

# https://s3.amazonaws.com/jbg-blobcast-artifacts/TeeKOGame/b0571f298d767fc9c8523d5696b303a9/anim_0.gif?junk=128
# https://s3.amazonaws.com/jbg-blobcast-artifacts/TeeKOGame/b0571f298d767fc9c8523d5696b303a9/shirtimage-0.png
