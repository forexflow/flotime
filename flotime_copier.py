from telethon import TelegramClient, events, Button, types, utils
from telethon.tl.patched import Message
from telethon.tl.custom.messagebutton import MessageButton
from telethon.tl.types.messages import BotCallbackAnswer
from telethon.tl.functions.account import UpdateStatusRequest

import asyncio
import logging
import tracemalloc
import os
import sqlite3
import re

loop = asyncio.get_event_loop()
scriptName = str(os.path.basename(__file__).split(".")[0])
print("Starting", scriptName)
api_id = 6
api_hash = "eb06d4abfb49dc3eeb1aeb98ae0f581e"
app_version = '5.11.0 (1709)'
device_model = 'SM-M205FN'
system_version = 'SDK 29'

tracemalloc.start()
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.WARN)
logger = logging.getLogger(__name__)

client_1 = TelegramClient("client_1_" + scriptName, api_id, api_hash, app_version=app_version,
                          device_model=device_model, system_version=system_version)
dbConnection = sqlite3.connect(f"data_{scriptName}.db", isolation_level=None, check_same_thread=False)

ignore_entities = []

# from_to = {-1001389557656: [-1001409636268, -1001412033708], -1001190739025: [-1001409636268, -1001412033708],
#            -1001277274378: [-1001409636268, -1001412033708]}
from_to = {-1001389557656: [-1001409636268], -1001190739025: [-1001409636268],
           -1001277274378_1: [-1001409636268], -1001223414088: [-1001454406502],
           -1001454800574: [-1001409636268]}
replaces = {'technicalpipsfx':'forexflow_admin'}
anti_anti_bot = False
replace_username = ""
single_client_mode = True
delete_messages = True


async def read_one_sqlite(sql, *args):
    data = await loop.run_in_executor(None, lambda: dbConnection.cursor().execute(sql, args).fetchone())
    return data


async def read_all_sqlite(sql, *args):
    data = await loop.run_in_executor(None, lambda: dbConnection.cursor().execute(sql, args).fetchall())
    return data
client_1.get_messages()
async def exec_sqlite(sql, *args):
    return await loop.run_in_executor(None, lambda: dbConnection.cursor().execute(sql, args))


class BotMessageBind:
    def __init__(self, in_db_id, from_chat_id, from_chat_msg_id, to_chat_id, to_chat_msg_id):
        self.in_db_id: int = in_db_id
        self.from_chat_id: int = from_chat_id
        self.from_chat_msg_id: int = from_chat_msg_id
        self.to_chat_id: int = to_chat_id
        self.to_chat_msg_id: int = to_chat_msg_id

    async def push_changes(self):
        await exec_sqlite(
            f"UPDATE {scriptName}_messagebind SET `from_chat_id` = ?, `from_chat_msg_id` = ?, `to_chat_id` = ?, "
            "`to_chat_msg_id` = ? WHERE in_db_id = ?",
            self.from_chat_id, self.from_chat_msg_id, self.to_chat_id, self.to_chat_msg_id, self.in_db_id)


async def get_message_bind(in_db_id: int):
    res = await read_one_sqlite(f"SELECT * FROM {scriptName}_messagebind WHERE in_db_id = ?", in_db_id)
    if res is None:
        return None
    else:
        return BotMessageBind(*res)


async def get_message_bind_msg_id(from_chat_id: int, from_chat_msg_id: int, to_chat_id: int) -> [int, None]:
    res = await read_one_sqlite(
        f"SELECT to_chat_msg_id FROM {scriptName}_messagebind WHERE from_chat_id = ? and "
        f"from_chat_msg_id = ? and to_chat_id = ?", from_chat_id, from_chat_msg_id, to_chat_id)
    if res is None:
        return None
    else:
        return res[0]


async def create_message_bind(from_chat_id: int, from_chat_msg_id: int, to_chat_id: int, to_chat_msg_id: int):
    await exec_sqlite(
        f"INSERT INTO {scriptName}_messagebind (from_chat_id, from_chat_msg_id, to_chat_id, to_chat_msg_id) VALUES "
        f"(?, ?, ?, ?)", from_chat_id, from_chat_msg_id, to_chat_id, to_chat_msg_id)


class ProcessedMessage:
    def __init__(self, text, media):
        self.text = text
        self.media = media


async def process_message(message: Message, to_chat: int):
    if ignore_entities and message.entities:
        for entity in message.entities:
            if isinstance(entity, tuple(ignore_entities)):
                return
    if single_client_mode:
        media = message.media if not isinstance(message.media,
                                                (types.MessageMediaWebPage, types.MessageMediaPoll)) else None
    else:
        f_name = await message.download_media()
        media = f_name
    text_to_send = message.text
    if text_to_send:
        for key, value in zip(replaces.keys(), replaces.values()):
            text_to_send = re.sub(key, value, text_to_send, flags=re.IGNORECASE)
    completed = False

    if anti_anti_bot:
        if message.text and len(message.text) < 30 and message.buttons:
            for button_list in message.buttons:
                if completed:
                    break
                for button in button_list:
                    button: MessageButton
                    if isinstance(button.button, types.KeyboardButtonCallback):
                        res: BotCallbackAnswer = await button.click()
                        text_to_send = res.message
                        completed = True
                        break
    lower = text_to_send.lower()
    if any(x in lower for x in ['succes ratio']):
        return False
    if replace_username:
        all_usernames = re.findall(r'@\w+', text_to_send)
        if all_usernames:
            for uname in all_usernames:
                text_to_send = text_to_send.replace(uname, replace_username)
    return ProcessedMessage(text_to_send, media)


@client_1.on(events.MessageDeleted())
async def delete_message_handler(event: events.MessageDeleted.Event):
    if delete_messages:
        if event.chat_id not in from_to:
            return
        for to in from_to[event.chat_id]:
            for deleted_id in event.deleted_ids:
                bound = await get_message_bind_msg_id(event.chat_id, deleted_id, to)
                if bound:
                    await client_1.delete_messages(to, [bound])


@client_1.on(events.MessageEdited())
async def edit_message_handler(event: events.MessageEdited.Event):
    if event.chat_id not in from_to:
        return
    message: Message = event.message
    for to in from_to[event.chat_id]:
        processed = await process_message(message, to)
        if not processed:
            raise events.StopPropagation
        ent = await client_1.get_input_entity(to)
        bound = await get_message_bind_msg_id(message.chat_id, message.id, to)
        if bound:
            await client_1.edit_message(ent, bound, processed.text, file=processed.media)
        if processed.media and not single_client_mode:
            os.remove(processed.media)


@client_1.on(events.Album())
async def album_handler(event: events.Album.Event):
    if event.chat_id not in from_to:
        raise events.StopPropagation
    text = None
    for to in from_to[event.chat_id]:
        files = []
        for i, message in enumerate(event.messages):
            processed = await process_message(message, to)
            if not processed:
                raise events.StopPropagation
            if i == 0:
                text = processed.text
            files.append(processed.media)
        message = event.messages[0]
        ent = await client_1.get_input_entity(to)
        reply_to = None
        if message.reply_to_msg_id:
            reply_to = await get_message_bind_msg_id(event.chat_id, message.reply_to_msg_id, to)
            if not reply_to:
                return
        sent = await client_1.send_file(ent, file=files, caption=text, reply_to=reply_to)
        await create_message_bind(event.chat_id, message.id, to, sent[0].id)
        if not single_client_mode:
            for file in files:
                os.remove(file)
    raise events.StopPropagation


@client_1.on(events.NewMessage(outgoing=True, incoming=True))
async def message_handler(event: events.NewMessage.Event):
    message: Message = event.message
    if not event.is_private:
        print(message.chat_id, message.text.replace("\n", "\\n") if message.text else None)
    if event.chat_id not in from_to:
        return

    if message.grouped_id:
        raise events.StopPropagation
    for to in from_to[event.chat_id]:
        processed = await process_message(message, to)
        if not processed:
            raise events.StopPropagation
        ent = await client_1.get_input_entity(to)
        reply_to = None

        if message.reply_to_msg_id:
            reply_to = await get_message_bind_msg_id(event.chat_id, message.reply_to_msg_id, to)
            if not reply_to:
                return
        await client_1(UpdateStatusRequest(False))

        sent: Message = await client_1.send_message(ent, processed.text, file=processed.media, reply_to=reply_to)
        await client_1(UpdateStatusRequest(True))
        await create_message_bind(event.chat_id, message.id, to, sent.id)
        if processed.media and not single_client_mode:
            os.remove(processed.media)


async def main():
    print('Preparing database...')
    await exec_sqlite(
        f"CREATE TABLE IF NOT EXISTS {scriptName}_messagebind (`in_db_id` INTEGER DEFAULT 0 PRIMARY KEY ,"
        f" `from_chat_id` INTEGER DEFAULT 0, `from_chat_msg_id` INTEGER DEFAULT 0, "
        f"`to_chat_id` INTEGER DEFAULT 0, `to_chat_msg_id` INTEGER DEFAULT 0)")
    print('Starting client_1 (receiver)...')
    await client_1.start()
    client_1_me = await client_1.get_me()
    await client_1.get_dialogs()
    print(f"Authorized client_1 as @{client_1_me.username} ({utils.get_display_name(client_1_me)})")
    print('Started')
    await asyncio.gather(client_1.run_until_disconnected())


loop.run_until_complete(main())
