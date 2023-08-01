import asyncio
import traceback
from uuid import uuid4

from aiogram import types
from aiogram.dispatcher.filters import ChatTypeFilter, CommandStart
from aiogram.utils.exceptions import (BadRequest, BotBlocked, BotKicked, CantInitiateConversation, InvalidQueryID,
                                      MigrateToChat, RetryAfter, TelegramAPIError, Unauthorized)

from .donation import send_donate_invoice
from .. import GlobalState, bot, dp, pool
from ..constants import ADMIN_GROUP_ID, GameState, OFFICIAL_GROUP_ID, VIP
from ..models import GAME_MODES
from ..utils import ADD_TO_GROUP_KEYBOARD, amt_donated, is_word, send_admin_group
from ..words import Words


@dp.message_handler(CommandStart(), ChatTypeFilter([types.ChatType.PRIVATE]))
async def cmd_start(message: types.Message) -> None:
    await message.reply(
        (
            "CHÀO! Tôi tổ chức các trò chơi chuỗi từ trong các nhóm Telegram.\n"
            "Thêm tôi vào một nhóm để bắt đầu chơi trò chơi!"
        ),
        disable_web_page_preview=True, allow_sending_without_reply=True,
        reply_markup=ADD_TO_GROUP_KEYBOARD
    )


@dp.message_handler(commands="feedback")
async def cmd_feedback(message: types.Message) -> None:
    rmsg = message.reply_to_message
    if (
        message.chat.id < 0
        and not message.get_command().partition("@")[2]
        and (not rmsg or rmsg.from_user.id != bot.id)
        or message.forward_from
    ):  # Prevent receiving feedback for other bots
        return

    arg = message.get_full_command()[1]
    if not arg:
        await message.reply(
            (
                "Chức năng: Gửi phản hồi cho chủ sở hữu của tôi.\n"
                f"Cách sử dụng: `/feedback@{(await bot.me).username} nhận xét`"
            ),
            allow_sending_without_reply=True
        )
        return

    asyncio.create_task(message.forward(ADMIN_GROUP_ID))
    asyncio.create_task(message.reply("Đã gửi phản hồi thành công.", allow_sending_without_reply=True))


@dp.message_handler(is_owner=True, commands="maintmode")
async def cmd_maintmode(message: types.Message) -> None:
    GlobalState.maint_mode = not GlobalState.maint_mode
    await message.reply(
        f"Chế độ bảo trì đã được chuyển đổi {'on' if GlobalState.maint_mode else 'off'}.",
        allow_sending_without_reply=True
    )


@dp.message_handler(
    ChatTypeFilter([types.ChatType.GROUP, types.ChatType.SUPERGROUP]), is_owner=True, commands="leave"
)
async def cmd_leave(message: types.Message) -> None:
    await message.chat.leave()


@dp.message_handler(is_owner=True, commands="sql")
async def cmd_sql(message: types.Message) -> None:
    try:
        async with pool.acquire() as conn:
            res = await conn.fetch(message.get_full_command()[1])
    except Exception as e:
        await message.reply(f"`{e.__class__.__name__}: {str(e)}`", allow_sending_without_reply=True)
        return

    if not res:
        await message.reply("Không có kết quả trả về.", allow_sending_without_reply=True)
        return

    text = ["*" + " - ".join(res[0].keys()) + "*"]
    for r in res:
        text.append("`" + " - ".join(str(i) for i in r.values()) + "`")
    await message.reply("\n".join(text), allow_sending_without_reply=True)


@dp.message_handler(content_types=types.ContentTypes.NEW_CHAT_MEMBERS)
async def new_member(message: types.Message) -> None:
    if any(user.id == bot.id for user in message.new_chat_members):  # self added to group
        await message.reply(
            "Cảm ơn vì đã thêm tôi. Bắt đầu một trò chơi cổ điển với /startclassic!",
            reply=False
        )
    elif message.chat.id == OFFICIAL_GROUP_ID:
        await message.reply(
            (
                "Chào mừng bạn đến với nhóm On9 Word Chain chính thức!\n"
                "Bắt đầu một trò chơi cổ điển với /startclassic!"
            ),
            allow_sending_without_reply=True
        )


@dp.inline_handler()
async def inline_handler(inline_query: types.InlineQuery):
    text = inline_query.query.lower()
    if not text or inline_query.from_user.id not in VIP and (await amt_donated(inline_query.from_user.id)) < 10:
        results = []
        for mode in GAME_MODES:
            command = f"/{mode.command}@{(await bot.me).username}"
            results.append(
                types.InlineQueryResultArticle(
                    id=str(uuid4()),
                    title="Start " + mode.name,
                    description=command,
                    input_message_content=types.InputTextMessageContent(command)
                )
            )
        await inline_query.answer(results, is_personal=not text)
        return

    if not is_word(text):
        await inline_query.answer(
            [
                types.InlineQueryResultArticle(
                    id=str(uuid4()),
                    title="Một truy vấn chỉ có thể bao gồm các bảng chữ cái",
                    description="Hãy thử một truy vấn khác",
                    input_message_content=types.InputTextMessageContent(r"¯\\_(ツ)\_/¯")
                )
            ],
            is_personal=True
        )
        return

    res = []
    for word in Words.dawg.iterkeys(text):
        word = word.capitalize()
        res.append(
            types.InlineQueryResultArticle(
                id=str(uuid4()),
                title=word,
                input_message_content=types.InputTextMessageContent(word)
            )
        )
        if len(res) == 50:  # Max 50 results
            break

    if not res:  # No results
        res.append(
            types.InlineQueryResultArticle(
                id=str(uuid4()),
                title="không có kết quả nào được tìm thấy",
                description="Hãy thử một truy vấn khác",
                input_message_content=types.InputTextMessageContent(r"¯\\_(ツ)\_/¯")
            )
        )

    await inline_query.answer(res, is_personal=True)


@dp.callback_query_handler()
async def callback_query_handler(callback_query: types.CallbackQuery) -> None:
    text = callback_query.data
    if text.startswith("donate"):
        await send_donate_invoice(callback_query.from_user.id, int(text.partition(":")[2]) * 100)
    await callback_query.answer()


@dp.errors_handler(exception=Exception)
async def error_handler(update: types.Update, error: TelegramAPIError) -> None:
    if update.message and update.message.chat:
        group_id = update.message.chat.id
        if group_id in GlobalState.games:
            asyncio.create_task(GlobalState.games[group_id].scan_for_stale_timer())

    # Unimportant errors
    if isinstance(error, (BotKicked, BotBlocked, CantInitiateConversation, InvalidQueryID)):
        return
    if isinstance(error, BadRequest) and str(error) in (
        "Không có quyền gửi tin nhắn",
        "Không đủ quyền để gửi tin nhắn văn bản đến cuộc trò chuyện",
        "Trò chuyện nhóm đã bị vô hiệu hóa",
        "Chat_write_forbidden",
        "Channel_private"
    ):
        return
    if isinstance(error, Unauthorized):
        if str(error).startswith("Bị cấm: bot không phải là thành viên"):
            return
        if str(error).startswith("Bị cấm: bot đã bị kick"):
            return
    if str(error).startswith("Lỗi máy chủ nội bộ: tin nhắn đã gửi bị xóa ngay lập tức"):
        return

    if isinstance(error, MigrateToChat):  # TODO: Test
        # Migrate group running game and statistics
        if group_id in GlobalState.games:
            GlobalState.games[error.migrate_to_chat_id] = GlobalState.games.pop(group_id)
            GlobalState.games[error.migrate_to_chat_id].group_id = error.migrate_to_chat_id
            asyncio.create_task(
                send_admin_group(f"Trò chơi chuyển từ {group_id} to {error.migrate_to_chat_id}.")
            )
        async with pool.acquire() as conn:
            await conn.execute(
                "CẬP NHẬT BỘ game group_id = $1 Tại group_id = $2;",
                error.migrate_to_chat_id, group_id
            )
            await conn.execute(
                "CẬP NHẬT bộ người chơi group_id = $1 Tại group_id = $2;",
                error.migrate_to_chat_id, group_id
            )
            await conn.execute("XÓA TỪ trò chơi Ở Tại group_id = $1;", group_id)
            await conn.execute("XÓA TỪ người chơi ở Tại group_id = $1;", group_id)
        await send_admin_group(f"Thống kê nhóm đã di chuyển từ {group_id} to {error.migrate_to_chat_id}.")
        return

    send_admin_msg = await send_admin_group(
        (
            f"<code>{error.__class__.__name__} @ "
            f"{group_id if update.message and update.message.chat else 'idk'}</code>:\n"
            f"<pre>{str(error)}</pre>"
        ) if isinstance(error, RetryAfter) else (
            "<pre>"
            + "".join(traceback.format_exception(etype=type(error), value=error, tb=error.__traceback__))
            + f"@ {group_id if update.message and update.message.chat else 'idk'}</pre>"
        ),
        parse_mode=types.ParseMode.HTML
    )
    if not update.message or not update.message.chat:
        return

    asyncio.create_task(
        update.message.reply(
            f"Xảy ra lỗi (`{error.__class__.__name__}`). Chủ sở hữu của tôi đã được thông báo.",
            allow_sending_without_reply=True
        )
    )

    if group_id in GlobalState.games:
        asyncio.create_task(
            send_admin_msg.reply(
                f"Do đó, trò chơi loại người trong {group_id}.",
                allow_sending_without_reply=True
            )
        )
        GlobalState.games[group_id].state = GameState.KILLGAME
        await asyncio.sleep(2)

        # If game is still not terminated
        if group_id in GlobalState.games:
            del GlobalState.games[group_id]
            await update.message.reply("Trò chơi kết thúc bất ngờ.", allow_sending_without_reply=True)
