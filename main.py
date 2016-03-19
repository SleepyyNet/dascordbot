#!/usr/bin/env python3

import asyncio
import json
import logging
import random
import string
import threading

import discord


log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class TimerClass(threading.Thread):
    def __init__(self, bot):
        threading.Thread.__init__(self)
        self.daemon = True
        self.event = threading.Event()
        self.count = 10
        self.bot = bot

    def run(self):
        while True:
            while not self.event.is_set():
                self.event.wait(45)
                cmd = self.bot.aidsfest_next_in_line()
                asyncio.ensure_future(cmd)
            log.info('Restarting timer')
            self.event.clear()

    def stop(self):
        self.event.set()


def id_generator(size=6, chars=string.ascii_uppercase + string.digits):
    return ''.join(random.SystemRandom().choice(chars) for _ in range(size))


class DiscordBot(discord.Client):
    def __init__(self):
        super().__init__()
        self.quitting = False

        self.server_name = 'NymN'

        self.sub_role_name = 'Twitch Subscriber'
        self.current_speaker_role_name = 'Current Speaker'
        self.moderator_role_names = ['Moderator', 'Roleplayer']

        self.aidsfest_text_channel_name = 'chemotherapy'

        self.queue_path = '/tmp/aidsfest_queue_nymn'

        self.aidsfest_queue = []
        self.load_queue()

    async def quit(self):
        self.quitting = True
        await self.close()

    def get_server(self, server_name):
        return discord.utils.find(lambda server: server.name == server_name, self.servers)

    def get_role(self, role_name):
        return discord.utils.find(lambda role: role.name == role_name, self.main_server.roles)

    def get_text_channel(self, channel_name):
        return discord.utils.find(lambda channel: channel.name == channel_name, self.main_server.channels)

    def is_member_subscriber(self, member):
        for role in member.roles:
            if role.id == self.sub_role.id:
                return True

        return False

    def get_member(self, user_id):
        return discord.utils.find(lambda m: m.id == user_id, self.main_server.members)

    async def on_message(self, message):
        log.info('{0}: {1}'.format(message.author.name, message.content))
        channel_id = message.channel.id if message.channel.is_private is False else 'private'
        # channel = message.channel

        chan = self.channels.get(channel_id, None)
        if chan is None:
            chan = self.channels.get('any', None)
        if chan:
            commands = chan.get('commands', {})
            delete_commands = chan.get('delete_commands', False)
            command = commands.get(message.content, None)
            if command is not None:
                cmd = command(message)
                asyncio.ensure_future(cmd)
                if delete_commands:
                    await self.delete_message(message)
                return True

        is_moderator = False
        try:
            for role in message.author.roles:
                if role in self.moderator_roles:
                    is_moderator = True
                    break
        except:
            pass

        if is_moderator is False:
            return False

        if message.content.startswith('!ping'):
            await self.send_message(message.channel, 'Pong!')
        elif message.content.startswith('!next'):
            await self.command_aidsfest_next(message)
        elif message.content.startswith('!chaninfo'):
            await self.send_message(message.channel, 'Current channel:\n**Name:** {0.name}\n**ID:** {0.id}'.format(message.channel))
        elif message.content.startswith('!clearchat'):
            correct_channel = discord.utils.find(lambda c: c.name == 'announcements', self.main_server.channels)
            if correct_channel:
                keep_first_message = True
                async for message in self.logs_from(correct_channel, limit=1000):
                    if keep_first_message:
                        keep_first_message = False
                        continue
                    await self.delete_message(message)
        elif message.content.startswith('!myroles'):
            roles_str = '\n'.join(['{0.name} - {0.id}'.format(role) for role in message.author.roles[1:]])
            await self.send_message(message.channel, 'You are part of the following roles:\n{0}'.format(roles_str))
        elif message.content.startswith('!serverroles'):
            roles_str = '\n'.join(['**{0.name}** - ID: **{0.id}**'.format(role) for role in self.main_server.roles[1:]])
            await self.send_message(message.channel, 'Roles on the server:\n{0}'.format(roles_str))
        elif message.content.startswith('!quit'):
            await self.send_message(message.channel, 'Quitting.. Good bye!')
            await self.quit()
        elif message.content.startswith('!info'):
            await self.send_message(message.channel, 'Your user ID is: **{0}**'.format(message.author.id))

    async def on_ready(self):
        print('Logged in as {0} (@{1})'.format(self.user.name, self.user.id))

        game = discord.Game()
        game.name = "BabyRage simulator"
        asyncio.ensure_future(self.change_status(game=game, idle=False))

        for server in self.servers:
            log.info(server)
        self.main_server = self.get_server(self.server_name)
        self.sub_role = self.get_role(self.sub_role_name)
        self.current_speaker_role = self.get_role(self.current_speaker_role_name)
        self.moderator_roles = [self.get_role(role_name) for role_name in self.moderator_role_names]

        self.aidsfest_text_channel = self.get_text_channel(self.aidsfest_text_channel_name)
        log.info(self.aidsfest_text_channel)
        log.info(self.aidsfest_text_channel.id)
        log.info(type(self.aidsfest_text_channel.id))

        self.channels = {
            self.aidsfest_text_channel.id: {
                'no_chatting': True,
                'commands': {
                    '!join': self.command_aidsfest_join_queue,
                    '!list': self.command_aidsfest_list,
                    '!unmuteall': self.command_unmute_all,
                }
            },
            'private': {
                'commands': {
                    '!join': self.command_aidsfest_join_queue,
                }
            },
            'any': {
                'commands': {
                    '!join': self.command_aidsfest_join_queue,
                }
            },
        }

        self.aidsfest_timer = TimerClass(self)
        self.aidsfest_timer.start()
        self.aidsfest_timer.stop()

    async def get_invitation(self, username, user_id=0):
        print('getting invitation for {0}'.format(username))
        invite = await self.create_invite(self.main_server)
        # invite = self.create_invite(self.main_server, max_age=10)
        if invite:
            return invite.url

    def load_queue(self):
        try:
            with open(self.queue_path, 'r') as file:
                self.aidsfest_queue = json.load(file)
        except FileNotFoundError:
            self.aidsfest_queue = []
            pass

    def save_queue(self):
        with open(self.queue_path, 'w+') as file:
            json.dump(self.aidsfest_queue, file, ensure_ascii=False)

    async def aidsfest_next_in_line(self):
        # Remove any "current speaker"
        for member in self.main_server.members:
            for role in member.roles:
                if role == self.current_speaker_role:
                    log.info('Removing {} from the current speaker role'.format(member.name))
                    await self.remove_roles(member, [self.current_speaker_role])
                    await self.server_voice_state(member, mute=True)

        if len(self.aidsfest_queue) > 0:
            user_id = self.aidsfest_queue.pop(0)
            member = self.get_member(user_id)
            if member:
                await self.add_roles(member, [self.current_speaker_role])
                await self.server_voice_state(member, mute=False)
                await self.send_message(self.aidsfest_text_channel, '{0}, you can now talk in the aidsfest channel.'.format(member.mention))

        try:
            if len(self.aidsfest_queue) > 0:
                qsize = len(self.aidsfest_queue)
                next_ppl = self.aidsfest_queue[:3]
                next_ppl_str = ', '.join(['**{0}**'.format(self.get_member(u).name) for u in next_ppl])
                await self.send_message(self.aidsfest_text_channel, 'There are currently **{0}** people in the queue. Next **{1}** in line are: {2}'.format(qsize, len(next_ppl), next_ppl_str))
        except:
            pass

        self.save_queue()

    async def command_aidsfest_join_queue(self, message):
        if message.channel.is_private:
            member = self.get_member(message.author.id)
            if member is None:
                return False
        else:
            member = message.author

        if self.is_member_subscriber(member) is False:
            return False

        if message.author.id in self.aidsfest_queue:
            await self.send_message(message.channel, '{0}, you are already in the aidsfest queue at position {1}.'.format(message.author.mention, self.aidsfest_queue.index(message.author.id) + 1))
        else:
            await self.send_message(message.channel, '{0}, you have been placed in the aidsfest queue.'.format(message.author.mention))
            self.aidsfest_queue.append(message.author.id)
            self.save_queue()

    async def command_aidsfest_next(self, message=None):
        self.aidsfest_timer.stop()

    async def command_aidsfest_list(self, message=None):
        if len(self.aidsfest_queue) > 0:
            qsize = len(self.aidsfest_queue)
            next_ppl = self.aidsfest_queue[:3]
            next_ppl_str = ', '.join(['**{0}**'.format(self.get_member(u).name) for u in next_ppl])
            await self.send_message(self.aidsfest_text_channel, 'There are currently **{0}** people in the queue. Next **{1}** in line are: {2}'.format(qsize, len(next_ppl), next_ppl_str))
        else:
            await self.send_message(self.aidsfest_text_channel, 'No one is queued up for aidsfest.')

    async def command_unmute_all(self, message):
        for member in self.main_server.members:
            if member.mute and not member.status == 'offline':
                log.info(member.status)
                await self.send_message(message.channel, 'Unmuting {}'.format(member.name))
                await self.server_voice_state(member, mute=False)
                await asyncio.sleep(5)


def run_discord_client():
    from config import DiscordConfig
    client = DiscordBot()

    try:
        client.run(DiscordConfig.EMAIL, DiscordConfig.PASSWORD)
    except KeyboardInterrupt:
        client.quit()
    except:
        log.exception('BabyRage BabyRage')

if __name__ == '__main__':
    run_discord_client()
