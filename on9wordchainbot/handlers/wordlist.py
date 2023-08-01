
import asyncio
import time

from aiogram import types

from .. import bot, dp, pool
from ..constants import WORD_ADDITION_CHANNEL_ID
from ..utils import check_word_existence, has_star, is_word, send_admin_group
from ..words import Words


@dp.message_handler(commands=["exist", "exists"])
async def cmd_exists(message: types.Message) -> None:
    word = message.text.partition(" ")[2].lower()
    if not word or not is_word(word):  # No proper argument given
        rmsg = message.reply_to_message
        if not rmsg or not rmsg.text or not is_word(rmsg.text.lower()):
            await message.reply(
                (
                    "Chức năng: Kiểm tra xem một từ có trong từ điển của tôi không. "
                    "Dùng /reqaddword nếu bạn muốn yêu cầu thêm từ mới.\n"
                    "Cách sử dụng: `/exists từ`"
                ),
                allow_sending_without_reply=True
            )
            return
        word = rmsg.text.lower()

    await message.reply(
        f"_{word.capitalize()}_ là *{'' if check_word_existence(word) else 'not '}trong* từ điển của tôi.",
        allow_sending_without_reply=True
    )


@dp.message_handler(commands=["reqaddword", "reqaddwords"])
async def cmd_reqaddword(message: types.Message) -> None:
    if message.forward_from:
        return

    words_to_add = [w for w in set(message.get_args().lower().split()) if is_word(w)]
    if not words_to_add:
        await message.reply(
            (
                "Chức năng: Yêu cầu từ mới. Kiểm tra @coihaycoc để cập nhật danh sách từ.\n"
                "Trước khi yêu cầu một từ mới, vui lòng kiểm tra xem:\n"
                "- Nó là một từ Tiếng Việt (\u274c những ngôn ngữ khác)\n"
                "- Nó được viết đúng chính tả\n"
                "- Nó không phải là [danh từ riêng](https://simple.wikipedia.org/wiki/Proper_noun) "
                "(\u274c tên)\n"
                "  (danh từ riêng hiện có trong danh sách từ và quốc tịch được miễn)\n"
                "Cách sử dụng: `/reqaddword từ1 từ2 ...`"
            ),
            disable_web_page_preview=True,
            allow_sending_without_reply=True
        )
        return

    existing = []
    rejected = []
    rejected_with_reason = []
    for w in words_to_add[:]:  # Iterate through a copy so removal of elements is possible
        if check_word_existence(w):
            existing.append("_" + w.capitalize() + "_")
            words_to_add.remove(w)

    async with pool.acquire() as conn:
        rej = await conn.fetch("CHỌN từ, lý do TỪ danh sách từ KHÔNG được chấp nhận;")
    for word, reason in rej:
        if word not in words_to_add:
            continue
        words_to_add.remove(word)
        word = "_" + word.capitalize() + "_"
        if reason:
            rejected_with_reason.append((word, reason))
        else:
            rejected.append(word)

    text = ""
    if words_to_add:
        text += f"Đã gửi {', '.join(['_' + w.capitalize() + '_' for w in words_to_add])} phê duyệt.\n"
        asyncio.create_task(
            send_admin_group(
                message.from_user.get_mention(
                    name=message.from_user.full_name
                         + (" \u2b50\ufe0f" if await has_star(message.from_user.id) else ""),
                    as_html=True
                )
                + " đang yêu cầu bổ sung "
                + ", ".join(["<i>" + w.capitalize() + "</i>" for w in words_to_add])
                + " vào danh sách từ. #reqaddword",
                parse_mode=types.ParseMode.HTML
            )
        )
    if existing:
        text += f"{', '.join(existing)} {'is' if len(existing) == 1 else 'are'} đã có trong danh sách từ.\n"
    if rejected:
        text += f"{', '.join(rejected)} {'was' if len(rejected) == 1 else 'were'} vật bị loại bỏ.\n"
    for word, reason in rejected_with_reason:
        text += f"{word} đã bị từ chối. Lý do: {reason}.\n"
    await message.reply(text, allow_sending_without_reply=True)


@dp.message_handler(is_owner=True, commands=["addword", "addwords"])
async def cmd_addwords(message: types.Message) -> None:
    words_to_add = [w for w in set(message.get_args().lower().split()) if is_word(w)]
    if not words_to_add:
        await message.reply("tại từ", allow_sending_without_reply=True)
        return

    existing = []
    rejected = []
    rejected_with_reason = []
    for w in words_to_add[:]:  # Cannot iterate while deleting
        if check_word_existence(w):
            existing.append("_" + w.capitalize() + "_")
            words_to_add.remove(w)

    async with pool.acquire() as conn:
        rej = await conn.fetch("CHỌN từ, lý do TỪ danh sách từ KHÔNG được chấp nhận;")
    for word, reason in rej:
        if word not in words_to_add:
            continue
        words_to_add.remove(word)
        word = "_" + word.capitalize() + "_"
        if reason:
            rejected_with_reason.append((word, reason))
        else:
            rejected.append(word)

    text = ""
    if words_to_add:
        async with pool.acquire() as conn:
            await conn.copy_records_to_table("wordlist", records=[(w, True, None) for w in words_to_add])
        text += f"Đã thêm {', '.join(['_' + w.capitalize() + '_' for w in words_to_add])} vào danh sách từ.\n"
    if existing:
        text += f"{', '.join(existing)} {'is' if len(existing) == 1 else 'are'} đã có trong danh sách từ.\n"
    if rejected:
        text += f"{', '.join(rejected)} {'was' if len(rejected) == 1 else 'were'} vật bị loại bỏ.\n"
    for word, reason in rejected_with_reason:
        text += f"{word} đã bị từ chối. Lý do: {reason}.\n"
    msg = await message.reply(text, allow_sending_without_reply=True)

    if not words_to_add:
        return

    t = time.time()
    await Words.update()
    asyncio.create_task(
        msg.edit_text(msg.md_text + f"\n\nDanh sách từ được cập nhật. Mất thời gian: `{time.time() - t:.3f}s`")
    )
    asyncio.create_task(
        bot.send_message(
            WORD_ADDITION_CHANNEL_ID,
            f"Đã thêm {', '.join(['_' + w.capitalize() + '_' for w in words_to_add])} vào danh sách từ.",
            disable_notification=True
        )
    )


@dp.message_handler(is_owner=True, commands="rejword")
async def cmd_rejword(message: types.Message) -> None:
    arg = message.get_args()
    word, _, reason = arg.partition(" ")
    if not word:
        return

    word = word.lower()
    async with pool.acquire() as conn:
        r = await conn.fetchrow("CHỌN được chấp nhận, lý do TỪ danh sách từ NƠI từ = $1;", word)
        if r is None:
            await conn.execute(
                "CHÈN VÀO danh sách từ (từ, chấp nhận, lý do) GIÁ TRỊ ($1, false, $2)",
                word,
                reason.strip() or None
            )

    word = word.capitalize()
    if r is None:
        await message.reply(f"_{word}_ vật bị loại bỏ.", allow_sending_without_reply=True)
    elif r["accepted"]:
        await message.reply(f"_{word}_ đã được chấp nhận.", allow_sending_without_reply=True)
    elif not r["reason"]:
        await message.reply(f"_{word}_ đã bị từ chối.", allow_sending_without_reply=True)
    else:
        await message.reply(
            f"_{word}_ đã bị từ chối. Lý do: {r['reason']}.",
            allow_sending_without_reply=True
        )
