import asyncio
import time
from datetime import datetime

from aiogram import types
from aiogram.dispatcher.filters import ChatTypeFilter, CommandHelp, CommandStart
from aiogram.utils.deep_linking import get_start_link
from aiogram.utils.markdown import quote_html

from .. import GlobalState, bot, dp
from ..constants import GameState
from ..utils import inline_keyboard_from_button, send_private_only_message
from ..words import Words


@dp.message_handler(CommandStart("help"), ChatTypeFilter([types.ChatType.PRIVATE]))
@dp.message_handler(CommandHelp())
async def cmd_help(message: types.Message) -> None:
    if message.chat.id < 0:
        await message.reply(
            "Please use this command in private.",
            allow_sending_without_reply=True,
            reply_markup=inline_keyboard_from_button(
                types.InlineKeyboardButton("Help message", url=await get_start_link("help"))
            )
        )
        return

    await message.reply(
        (
            "/gameinfo - Mô tả chế độ trò chơi\n"
            "/troubleshoot - Giải quyết các vấn đề chung\n"
            "/reqaddword - Yêu cầu thêm từ\n"
            "/feedback - Gửi phản hồi cho chủ sở hữu bot\n\n"
            "Bạn có thể nhắn tin [Còi](https://t.me/coihaycoc) "
            "Bằng tiếng người * nếu bạn gặp sự cố với bot.\n"
            "Official Group: @nguhanh69 & @xemshownguhanh69"
            "Bổ sung từ CHỦ SỞ HỮU: @coihaycoc\n"
            "Mã nguồn: [Hỏi chủ nhân của tôi](https://t.me/coihaycoc)\n"
            "Biểu tượng sử thi được thiết kế bởi[joker tg 🇮🇳](https://t.me/IAM_A_JOKER)"
        ),
        disable_web_page_preview=True,
        allow_sending_without_reply=True
    )


@dp.message_handler(commands="gameinfo")
@send_private_only_message
async def cmd_gameinfo(message: types.Message) -> None:
    await message.reply(
        (
            "/startclassic - trò chơi cổ điển\n"
            "Người chơi lần lượt gửi các từ bắt đầu bằng chữ cái cuối cùng của từ trước đó.\n\n"
            "Biến thể:\n"
            "/starthard - Trò chơi chế độ khó\n"
            "/startchaos - Trò chơi hỗn loạn (thứ tự lần lượt ngẫu nhiên)\n"
            "/startcfl - Trò chơi chữ cái đầu tiên được chọn\n"
            "/startrfl - Trò chơi chữ cái đầu tiên ngẫu nhiên\n"
            "/startbl - Trò chơi chữ cái bị cấm\n"
            "/startrl - Trò chơi thư bắt buộc\n\n"
            "/startelim - trò chơi loại bỏ\n"
            "Điểm của mỗi người chơi là độ dài từ tích lũy của họ. "
            "Những người chơi ghi điểm thấp nhất bị loại sau mỗi vòng.\n\n"
            "/startmelim - Trò chơi loại bỏ hỗn hợp (phần thưởng quyên góp)\n"
            "Trò chơi loại bỏ với các chế độ khác nhau. Hãy thử tại."
        ),
        allow_sending_without_reply=True
    )


@dp.message_handler(commands="troubleshoot")
@send_private_only_message
async def cmd_troubleshoot(message: types.Message) -> None:
    await message.reply(
        (
            "Các bước này giả sử bạn có quyền quản trị viên. "
            "Nếu không, vui lòng yêu cầu quản trị viên nhóm kiểm tra thay.\n\n"
            "<b>Nếu bot không phản hồi <code>/start[mode]</code></b>, kiểm tra nếu:\n"
            "1. Bot vắng mặt/tắt tiếng trong nhóm của bạn "
            "\u27a1\ufe0f Thêm bot vào nhóm của bạn / Bật tiếng bot\n"
            "2. Chế độ chậm được bật \u27a1\ufe0f Tắt chế độ chậm\n"
            "3. Gần đây ai đó đã spam các lệnh trong nhóm của bạn "
            "\u27a1\ufe0f Bot bị giới hạn tốc độ trong nhóm của bạn, hãy kiên nhẫn chờ đợi\n"
            "4. Bot không phản hồi<code>/ping</code> "
            "\u27a1\ufe0f Có khả năng bot đang ngoại tuyến, hãy kiểm tra @coihaycoc để cập nhật trạng thái\n\n"
            "<b>If bot không thể được thêm vào nhóm của bạn</b>:\n"
            "1. Có thể có tối đa 20 bot trong một nhóm. Kiểm tra xem đã đạt đến giới hạn này chưa.\n\n"
            "Nếu bạn gặp các vấn đề khác, vui lòng liên hệ <a href='tg://user?id=463998526'>chủ nhân của tôi</a>."
        ),
        parse_mode=types.ParseMode.HTML,
        allow_sending_without_reply=True
    )


@dp.message_handler(commands="ping")
async def cmd_ping(message: types.Message) -> None:
    t = time.time()
    msg = await message.reply("Pong!", allow_sending_without_reply=True)
    await msg.edit_text(f"Pong! `{time.time() - t:.3f}s`")


@dp.message_handler(commands="chatid")
async def cmd_chatid(message: types.Message) -> None:
    await message.reply(f"`{message.chat.id}`", allow_sending_without_reply=True)


@dp.message_handler(commands="runinfo")
async def cmd_runinfo(message: types.Message) -> None:
    build_time_str = (
        "{0.day}/{0.month}/{0.year}".format(GlobalState.build_time)
        + " "
        + str(GlobalState.build_time.time())
        + " HKT"
    )
    uptime = datetime.now().replace(microsecond=0) - GlobalState.build_time
    await message.reply(
        (
            f"Build time: `{build_time_str}`\n"
            f"Uptime: `{uptime.days}.{str(uptime).rsplit(maxsplit=1)[-1]}`\n"
            f"Words in dictionary: `{Words.count}`\n"
            f"Total games: `{len(GlobalState.games)}`\n"
            f"Running games: `{len([g for g in GlobalState.games.values() if g.state == GameState.RUNNING])}`\n"
            f"Players: `{sum(len(g.players) for g in GlobalState.games.values())}`"
        ),
        allow_sending_without_reply=True
    )


@dp.message_handler(is_owner=True, commands="playinggroups")
async def cmd_playinggroups(message: types.Message) -> None:
    if not GlobalState.games:
        await message.reply("Không có nhóm nào đang chơi trò chơi.", allow_sending_without_reply=True)
        return

    groups = []

    async def append_group(group_id: int) -> None:
        try:
            group = await bot.get_chat(group_id)
            url = await group.get_url()
            # TODO: weakref exception is aiogram bug, wait fix
        except TypeError as e:
            if str(e) == "không thể tạo tham chiếu yếu đến đối tượng 'NoneType'":
                text = "???"
            else:
                text = f"(<code>{e.__class__.__name__}: {e}</code>)"
        except Exception as e:
            text = f"(<code>{e.__class__.__name__}: {e}</code>)"
        else:
            if url:
                text = f"<a href='{url}'>{quote_html(group.title)}</a>"
            else:
                text = f"<b>{group.title}</b>"

        if group_id not in GlobalState.games:  # In case the game ended during API calls
            return

        groups.append(
            text + (
                f" <code>{group_id}</code> "
                f"{len(GlobalState.games[group_id].players_in_game)}/{len(GlobalState.games[group_id].players)}P "
                f"{GlobalState.games[group_id].turns}W "
                f"{GlobalState.games[group_id].time_left}s"
            )
        )

    await asyncio.gather(*[append_group(gid) for gid in GlobalState.games])
    await message.reply(
        "\n".join(groups), parse_mode=types.ParseMode.HTML,
        disable_web_page_preview=True, allow_sending_without_reply=True
    )
