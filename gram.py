#!/usr/bin/env python
import argparse
import sys
import os
import copy
from random import randrange
import configparser
import json
import asyncio
import random
import string
import traceback
import time
import datetime

from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError

from telethon.tl.functions.channels import GetParticipantsRequest
from telethon.tl.types import ChannelParticipantsSearch
from telethon.tl.types import (
PeerChannel
)
from telethon import functions, types
from telethon.tl.types import InputPeerEmpty, InputPeerChannel, InputPeerUser
from telethon.errors.rpcerrorlist import FirstNameInvalidError, PeerFloodError, UserPrivacyRestrictedError, UserIdInvalidError, UserChannelsTooMuchError, ChatAdminRequiredError, UserNotMutualContactError
from telethon.tl.functions.channels import InviteToChannelRequest

sys.path.append(".")

def get_all_values(d):
    if isinstance(d, dict):
        for v in d.values():
            yield from get_all_values(v)
    elif isinstance(d, list):
        for v in d:
            yield from get_all_values(v)
    else:
        yield d 

async def telegram_client(session_name) -> TelegramClient:
    config = configparser.ConfigParser()
    config.read("config.ini")

    # Setting configuration values
    api_id = config['Telegram']['api_id']
    api_hash = config['Telegram']['api_hash']

    api_hash = str(api_hash)

    phone = config['Telegram']['phone']
    username = config['Telegram']['username']

    # Create the client and connect
    client = TelegramClient(session_name, api_id, api_hash)
    await client.start()
    print("Client Created: {}".format(client))

    # Ensure you're authorized
    if not await client.is_user_authorized():
        client.send_code_request(phone)
        try:
            client.sign_in(phone, input('Enter the code: '))
        except SessionPasswordNeededError:
            client.sign_in(password=input('Password: '))

    return client

async def telegram_forwarding_client(
    session_name,
    source_channel_name,
    destination_channel_name,
    filterpathjson=None
    ):
    print('filterpathjson: {}'.format(filterpathjson))
    config = configparser.ConfigParser()
    config.read("config.ini")

    # Setting configuration values
    api_id = config['Telegram']['api_id']
    api_hash = config['Telegram']['api_hash']

    api_hash = str(api_hash)

    phone = config['Telegram']['phone']
    username = config['Telegram']['username']

    # Create the client and connect
    client = TelegramClient(session_name, api_id, api_hash)

    @client.on(events.NewMessage(chats=(source_channel_name)))
    async def normal_handler(event):
        print(event.message.to_dict())
        print('event.message.from_id.user_id: {}'.format(event.message.from_id.user_id))
        if filterpathjson is not None:
            ## filter-out messages based on banned users
            bandict = {}
            try:
                with open(filterpathjson) as json_file:
                    bandict = json.load(json_file)
            except OSError as e:
                print(e.errno)

            if bandict.get(str(event.message.from_id.user_id)) is None:
                await client.forward_messages(destination_channel_name, messages=event.message)
            else:
                print('found spammer: {}'.format(event.message.from_id.user_id))
        else:
            print('')
            await client.forward_messages(destination_channel_name, messages=event.message)
    await client.start()

    # Ensure you're authorized
    if not await client.is_user_authorized():
        client.send_code_request(phone)
        try:
            client.sign_in(phone, input('Enter the code: '))
        except SessionPasswordNeededError:
            client.sign_in(password=input('Password: '))

    await client.run_until_disconnected()

def slug_string(length) -> str:
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for i in range(length))

class Main(object):
    def __init__(self):
        parser = argparse.ArgumentParser(
            description='tools to manage telegram groups',
            usage='''members
            group
            messages
            listener
''')
        parser.add_argument('command', help='Subcommand to run')
        # parse_args defaults to [1:] for args, but you need to
        # exclude the rest of the args too, or validation will fail
        args = parser.parse_args(sys.argv[1:2])

        print('Main {}'.format(args.command))

        if args.command == 'members':
            members = TelegramMembers()
            loop = asyncio.get_event_loop()
            coroutine = members.start(args)
            loop.run_until_complete(coroutine)
        elif args.command == 'group':
            loop = asyncio.get_event_loop()
            telegramgroup = TelegramGroup()
            coroutine = telegramgroup.start(args)
            loop.run_until_complete(coroutine)
        elif args.command == 'messages':
            loop = asyncio.get_event_loop()
            telegrammessages = TelegramMessages()
            coroutine = telegrammessages.start(args)
            loop.run_until_complete(coroutine)
        elif args.command == 'listener':
            loop = asyncio.get_event_loop()
            telegram_listener = TelegramListener()
            coroutine = telegram_listener.start(args)
            loop.run_until_complete(coroutine)
        else:
            print('Unrecognized command')
            parser.print_help()
            exit(1)

class TelegramListener(object):
    def __init__(self):
        print('TelegramListener init')

    async def start(self, args):
        print('TelegramListener.start args {}'.format(args))
        parser = argparse.ArgumentParser(
            description='members command description')
        # prefixing the argument with -- means it's optional
        # parser.add_argument('dir')
        # parser.add_argument('dirs', nargs='+')#, help='<Required> Set flag', required=True)
        parser.add_argument('--dry-run', dest='dry_run', action='store_true')
        parser.add_argument('--source-channel-url', dest='source_channel_url', help='URL of Telegram source channel')
        parser.add_argument('--destination-channel-url', dest='destination_channel_url', help='URL of Telegram destination channel')
        parser.set_defaults(dry_run=False)
        args = parser.parse_args(sys.argv[2:])
        
        print('Running TelegramListener.start, args: {}'.format(repr(args)))

        if args.source_channel_url is None:
            print("--channel-url is not specified")
            exit()

        if args.source_channel_url is not None:
            await self.forward_to_channel(args.source_channel_url, args.destination_channel_url)

    async def forward_to_channel(self, source_channel_url, destination_channel_url):
        print('source_channel_url {}'.format(source_channel_url))
        print('destination_channel_url {}'.format(destination_channel_url))

        # get channel info with standard(non-listener) client
        client = await telegram_client('session_forward')
        print('client {}'.format(client))

        source_channel = await client.get_entity(source_channel_url)
        print('source_channel {}'.format(source_channel.to_dict()))

        destination_channel = await client.get_entity(destination_channel_url)
        print('destination_channel {}'.format(destination_channel.to_dict()))

        # initiate listening
        listening_client = await telegram_forwarding_client('session_listener-{}'.format(source_channel.username), source_channel.username, 'objaaron', 'bandict.json')

class TelegramMessages(object):
    def __init__(self):
        print('TelegramMessages init')

    async def start(self, args):
        print('TelegramMessages.start args {}'.format(args))
        parser = argparse.ArgumentParser(
            description='members command description')
        # prefixing the argument with -- means it's optional
        # parser.add_argument('dir')
        # parser.add_argument('dirs', nargs='+')#, help='<Required> Set flag', required=True)
        parser.add_argument('--dry-run', dest='dry_run', action='store_true')
        parser.add_argument('--channel-url', dest='channel_url', help='URL of Telegram channel')
        parser.add_argument('--json-output', dest='json_output', action='store_true', help='save members to json file')
        parser.add_argument('--add-messages-to-channel-url', dest='add_messages_to_channel_url', help='add messages to this channel')
        parser.set_defaults(dry_run=False)
        args = parser.parse_args(sys.argv[2:])
        print('Running TelegramMessages.start, args: {}'.format(repr(args)))
        if args.channel_url is None:
            print("--channel-url is not specified")
            exit()

        if args.json_output is True:
            members = await self.channel_members(args.channel_url)
            await self.json_out_participants(members, args.channel_url)

        if args.add_messages_to_channel_url is not None:
            await self.add_messages_to_channel(args.channel_url, args.add_messages_to_channel_url)

    # FIXME: not complete, this just prints-out the entire message history of source_channel_url
    async def add_messages_to_channel(self, source_channel_url, add_to_channel_url):
        print('add_messages_to_channel {}'.format(add_to_channel_url))
        client = await telegram_client('session_gamma')

        source_channel = await client.get_entity(source_channel_url)
        print('source_channel {}'.format(source_channel))

        # ## filter banned users
        bandict = {}
        try:
            with open('bandict.json') as json_file:
                bandict = json.load(json_file)
        except OSError as e:
            print(e.errno)

        # FIXME: currently just copy all message ids of a channel to a json file
        # TODO: add messages to other channel
        # TODO: filter by banned users before doing any adding

        channel_name = source_channel_url.split('/')[-1]
        all_messages = {}
        try:
            with open('{}-messages.json'.format(channel_name)) as json_file:
                all_messages = json.load(json_file)
        except OSError as e:
            print(e.errno)

        # Filter by sender
        async for message in client.iter_messages(source_channel, reverse=True):
            ## add to all_messages
            print(message)
            all_messages['{}'.format(message.id)] = {'id': message.id, 'from_id': message.from_id}
            try:
                with open('{}}-messages.json'.format(channel_name), 'w+') as json_file:
                    json.dump(all_messages, json_file, indent=4, sort_keys=True, default=str)
            except OSError as e:
                print(e.errno)

class TelegramMembers(object):
    def __init__(self):
        print('TelegramMembers init')

    async def start(self, args):
        print('TelegramMembers.start args {}'.format(args))
        parser = argparse.ArgumentParser(
            description='members command description')
        # prefixing the argument with -- means it's optional
        # parser.add_argument('dir')
        # parser.add_argument('dirs', nargs='+')#, help='<Required> Set flag', required=True)
        parser.add_argument('--dry-run', dest='dry_run', action='store_true')
        parser.add_argument('--channel-url', dest='channel_url', help='URL of Telegram channel')
        parser.add_argument('--ban-from-channel', dest='ban_from_channel', help='permanently ban this id from channel')
        parser.add_argument('--json-output', dest='json_output', action='store_true', help='save members to json file')
        parser.add_argument('--add-to-channel-url', dest='add_to_channel_url', help='add members to this channel')
        parser.add_argument('--ban-filter-user-id', dest='ban_filter_user_id', help='add telegram user id to local banlist filter')
        parser.set_defaults(dry_run=False)
        args = parser.parse_args(sys.argv[2:])
        print('Running TelegramMembers.start, args: {}'.format(repr(args)))

        if args.json_output is True:
            members = await self.channel_members(args.channel_url)
            await self.json_out_participants(members, args.channel_url)

        if args.ban_filter_user_id is not None:
            await self.add_to_banlist(args.ban_filter_user_id)
        else:
            if args.channel_url is None:
                print("--channel-url is not specified")
                exit()

            if args.channel_url is not None and args.ban_from_channel is not None:
                await self.ban_from_channel(args.channel_url, args.ban_from_channel)

            if args.channel_url is not None and args.add_to_channel_url is None:
                await self.channel_members(args.channel_url)

            if args.channel_url is not None and args.add_to_channel_url is not None:
                await self.add_to_channel(args.channel_url, args.add_to_channel_url)

    async def channel_members(self, channel_url):
        print('channel_url {}'.format(channel_url))

        client = await telegram_client('session_beta')
        my_channel = await client.get_entity(channel_url)
        print('my_channel: {}'.format(my_channel))

        offset = 0
        limit = 100
        all_participants = []
        index = 0

        while True:
            participants = await client(GetParticipantsRequest(
                my_channel, ChannelParticipantsSearch(''), offset, limit,
                hash=0
            ))

            if not participants.users:
                break
            
            print('participants: {}'.format(participants))
            all_participants.extend(participants.users)
            print('user len: {}'.format(len(participants.users)))
            offset += len(participants.users)
            index += 1

        return all_participants

    async def json_out_participants(self, participants, channel_url):
        channel_name = channel_url.split('/')[-1]
        print('channel_name: {}'.format(channel_name))

        all_user_details = []
        for participant in participants:
            all_user_details.append(
                {"id": participant.id, "first_name": participant.first_name, "last_name": participant.last_name,
                "username": participant.username, "phone": participant.phone, "is_bot": participant.bot, "access_hash": participant.access_hash})

            print('participant: {}'.format(participant))

        with open('{}-users.json'.format(channel_name), 'w') as outfile:
            json.dump(all_user_details, outfile, indent=4, sort_keys=True, default=str)

    async def add_to_banlist(self, telegram_user_id):
        print('add_to_banlist {}'.format(telegram_user_id))

        ## open bandict
        bandict = {}
        try:
            with open('bandict.json') as json_file:
                bandict = json.load(json_file)
        except OSError as e:
            print(e.errno)

        ## add to bandict
        bandict['{}'.format(telegram_user_id)] = {'id': telegram_user_id}
        try:
            with open('bandict.json', 'w+') as bandict_json:
                json.dump(bandict, bandict_json, indent=4, sort_keys=True, default=str)
        except OSError as e:
            print(e.errno)

    async def add_to_channel(self, source_channel_url, add_to_channel_url):
        print('add_to_channel_url {}'.format(add_to_channel_url))
        members = await self.channel_members(source_channel_url)
        # chunked = self.chunks(members, 50)

        # for i in chunked:
        #     print('chunked: {}'.format(i))

        client = await telegram_client('session_gamma')
        # loop.run_until_complete(client)

        print('client {}'.format(client))

        # loop = asyncio.get_event_loop()
        destination_channel = await client.get_entity(add_to_channel_url)
        print('destination_channel {}'.format(destination_channel))

        ## filter previously added users
        added_users = {}
        try:
            with open('{}-added_users.json'.format(destination_channel.username)) as json_file:
                added_users = json.load(json_file)
        except OSError as e:
            print(e.errno)

        ## filter banned users
        bandict = {}
        try:
            with open('bandict.json') as json_file:
                bandict = json.load(json_file)
        except OSError as e:
            print(e.errno)

        print('added_users: {}'.format(added_users))
        for num, member in enumerate(members):
            # print('member {}'.format(member))
            print('member.id {}'.format(member.id))
            print('member.access_hash {}'.format(member.access_hash))
            print('member.username {}'.format(member.username))
            print('-----')
            try:
                if added_users.get(member.username) is None and bandict.get(member.username) is None:
                    if member.username is not None:
                        print('not banned and did not find. Adding: {} {} ({})'.format(member.first_name, member.last_name, member.username))

                        member_to_add = InputPeerUser(member.id, member.access_hash)
                        await client(InviteToChannelRequest(destination_channel,[member_to_add]))
                        added_users['{}'.format(member.username)] = {'access_hash': member.access_hash, 'first_name': member.first_name, 'id': member.id, 'last_name': member.last_name, 'phone': member.phone, 'username': member.username}
                        try:
                            with open('{}-added_users.json'.format(destination_channel.username), 'w+') as added_users_json:
                                json.dump(added_users, added_users_json, indent=4, sort_keys=True, default=str)
                        except OSError as e:
                            print(e.errno)

                        if num % 50 == 0:
                            print("Every 50th user waiting 15 minutes")
                            time.sleep(60*15)
                        else:
                            print("Waiting 60 Seconds...")
                            time.sleep(60)
            except PeerFloodError:
                print("Getting Flood Error from telegram. Script is stopping now. Please try again after some time.")
            except UserPrivacyRestrictedError:
                print("The member's privacy settings do not allow you to do this. Skipping.")
            except UserIdInvalidError:
                print("User is no longer valid. Skipping.")
            except UserChannelsTooMuchError:
                print("User is in too many channels. Skipping.")
            except ChatAdminRequiredError:
                print("Chat admin required to do that. Skipping.")
            except UserNotMutualContactError:
                print("User is not mutual contact. Skipping.")
            except:
                traceback.print_exc()
                print("Unexpected Error")
                continue

    def chunks(self, lst, n):
        """Yield successive n-sized chunks from lst."""
        for i in range(0, len(lst), n):
            yield lst[i:i + n]

class TelegramGroup(object):
    def __init__(self):
        print('TelegramGroup init')

    async def start(self, args):
        print('TelegramGroup.start args {}'.format(args))
        parser = argparse.ArgumentParser(
            description='members command description')
        parser.add_argument('--dry-run', dest='dry_run', action='store_true')
        parser.add_argument('--channel-url', dest='channel_url', help='URL of Telegram channel')
        parser.set_defaults(dry_run=False)
        args = parser.parse_args(sys.argv[2:])
        print('Running TelegramGroup.start, args: {}'.format(repr(args)))

        if args.channel_url is None:
            print("--channel-url is not specified")
            exit()

        await self.channel_metadata(args.channel_url)

    async def channel_metadata(self, channel_url):
        print('channel_url {}'.format(channel_url))
        client = await telegram_client('session_alpha')
        channel = await client.get_entity(channel_url)
        await self.json_out_channel(channel)
        print('channel: {}'.format(channel))

    async def json_out_channel(self, telegram_channel):
        print('telegram_channel: {}'.format(telegram_channel))
        channel_details = []
        # for participant in participants:
        channel_details.append(
            {"id": telegram_channel.id, "title": telegram_channel.title, "access_hash": telegram_channel.access_hash,
            "username": telegram_channel.username})

        print('channel_details: {}'.format(channel_details))

        with open('{}-channel.json'.format(telegram_channel.username), 'w') as outfile:
            json.dump(channel_details, outfile, indent=4, sort_keys=True, default=str)

if __name__ == '__main__':
    Main()
