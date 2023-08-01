import asyncio
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

import aiofiles
import aiofiles.os
import matplotlib.pyplot as plt
from aiocache import cached
from aiogram import types
from aiogram.utils.markdown import quote_html
from asyncpg import Record
from matplotlib.dates import DateFormatter
from matplotlib.ticker import MaxNLocator

from .. import dp, pool
from ..utils import has_star, send_groups_only_message


@dp.message_handler(commands=["stat", "stats", "stalk"])
async def cmd_stats(message: types.Message) -> None:
    rmsg = message.reply_to_message
    user = (rmsg.forward_from or rmsg.from_user) if rmsg else message.from_user
    async with pool.acquire() as conn:
        res = await conn.fetchrow("CHỌN * TỪ người chơi Ở TẠI user_id = $1;", user.id)

    if not res:
        await message.reply(
            f"Không có số liệu thống kê cho {user.get_mention(as_html=True)}!",
            parse_mode=types.ParseMode.HTML, allow_sending_without_reply=True
        )
        return

    mention = user.get_mention(
        name=user.full_name + (" \u2b50\ufe0f" if await has_star(user.id) else ""), as_html=True
    )
    text = (
        f"\U0001f4ca Statistics for {mention}:\n"
        f"<b>{res['game_count']}</b> trò chơi đã chơi\n"
        f"<b>{res['win_count']} ({res['win_count'] / res['game_count']:.0%})</b> chiến thắng trò chơi\n"
        f"<b>{res['word_count']}</b> tổng số từ chơi\n"
        f"<b>{res['letter_count']}</b> tổng số chữ cái đã chơi"
    )
    if res["longest_word"]:
        text += f"\nTừ dài nhất: <b>{res['longest_word'].capitalize()}</b>"
    await message.reply(text, parse_mode=types.ParseMode.HTML, allow_sending_without_reply=True)


@dp.message_handler(commands="groupstats")
@send_groups_only_message
async def cmd_groupstats(message: types.Message) -> None:
    # TODO: Add top players in group (max 5) to message
    async with pool.acquire() as conn:
        player_cnt, game_cnt, word_cnt, letter_cnt = await conn.fetchrow(
            """\
            LỰA CHỌN COUNT(DISTINCT user_id), COUNT(DISTINCT game_id), SUM(word_count), SUM(letter_count)
                TỪ game thủ
                TẠI group_id = $1;""",
            message.chat.id
        )
    await message.reply(
        (
            f"\U0001f4ca Thống kê cho <b>{quote_html(message.chat.title)}</b>\n"
            f"<b>{player_cnt}</b> gười chơi\n"
            f"<b>{game_cnt}</b> trò chơi đã chơi\n"
            f"<b>{word_cnt}</b> tổng số từ chơi\n"
            f"<b>{letter_cnt}</b> tổng số chữ cái đã chơi"
        ),
        parse_mode=types.ParseMode.HTML,
        allow_sending_without_reply=True
    )


@cached(ttl=5)
async def get_global_stats() -> str:
    async def get_cnt_1() -> Tuple[int, int]:
        async with pool.acquire() as conn:
            group_cnt, game_cnt = await conn.fetchrow(
                "LỰA CHỌN COUNT(DISTINCT group_id), COUNT(*) TỪ trò chơi;"
            )
        return group_cnt, game_cnt

    async def get_cnt_2() -> Tuple[int, int, int]:
        async with pool.acquire() as conn:
            player_cnt, word_cnt, letter_cnt = await conn.fetchrow(
                "LỰA CHỌN COUNT(*), SUM(word_count), SUM(letter_count) TỪ người chơi;"
            )
            return player_cnt, word_cnt, letter_cnt

    get_cnt_1_task = asyncio.create_task(get_cnt_1())
    get_cnt_2_task = asyncio.create_task(get_cnt_2())
    group_cnt, game_cnt = await get_cnt_1_task
    player_cnt, word_cnt, letter_cnt = await get_cnt_2_task

    return (
        "\U0001f4ca thống kê toàn cầu\n"
        f"*{group_cnt}* các nhóm\n"
        f"*{player_cnt}* người chơi\n"
        f"*{game_cnt}* trò chơi đã chơi\n"
        f"*{word_cnt}* tổng số từ chơi\n"
        f"*{letter_cnt}* tổng số chữ cái đã chơi"
    )


@dp.message_handler(commands="globalstats")
async def cmd_globalstats(message: types.Message) -> None:
    await message.reply(await get_global_stats(), allow_sending_without_reply=True)


@dp.message_handler(is_owner=True, commands=["trend", "trends"])
async def cmd_trends(message: types.Message) -> None:
    try:
        days = int(message.get_args() or 14)
        assert days > 1, "smh"
    except (ValueError, AssertionError) as e:
        await message.reply(f"`{e.__class__.__name__}: {str(e)}`", allow_sending_without_reply=True)
        return

    t = time.time()  # Measure time used to generate graphs
    today = datetime.now().date()

    async def get_daily_games() -> Dict[str, Any]:
        async with pool.acquire() as conn:
            return dict(
                await conn.fetch(
                    """\
                    LỰA CHỌN start_time::DATE d, COUNT(start_time::DATE)
                        TỪ trò chơi
                        TẠI start_time::DATE >= $1
                        GROUP BY d
                        ORDER BY d;""",
                    today - timedelta(days=days - 1)
                )
            )

    async def get_active_players() -> Dict[str, Any]:
        async with pool.acquire() as conn:
            return dict(
                await conn.fetch(
                    """\
                    LỰA CHỌN game.start_time::DATE d, COUNT(DISTINCT gameplayer.user_id)
                        TỪ game thủ
                        INNER THAM GIA trò chơi BẬT gameplayer.game_id = game.id
                        TẠI game.start_time::DATE >= $1
                        GROUP BY d
                        ORDER BY d;""",
                    today - timedelta(days=days - 1)
                )
            )

    async def get_active_groups() -> Dict[str, Any]:
        async with pool.acquire() as conn:
            return dict(
                await conn.fetch(
                    """\
                    LỰA CHỌN start_time::DATE d, COUNT(DISTINCT group_id)
                        TỪ trò chơi
                        TẠI game.start_time::DATE >= $1
                        GROUP BY d
                        ORDER BY d;""",
                    today - timedelta(days=days - 1)
                )
            )

    async def get_cumulative_groups() -> Dict[str, Any]:
        async with pool.acquire() as conn:
            return dict(
                await conn.fetch(
                    """\
                    LỰA CHỌN *
                        TỪ (
                            LỰA CHỌN d, SUM(count) HẾT ( ĐẶT HÀNG THEO d)
                                TỪ (
                                    LỰA CHỌN d, COUNT(group_id)
                                        TỪ (
                                            LỰA CHỌN DISTINCT group_id, MIN(start_time::DATE) d
                                                TỪ trò chơi
                                                GROUP BY group_id
                                        ) gd
                                        GROUP BY d
                                ) dg
                        ) ds
                        TẠI d >= $1;""",
                    today - timedelta(days=days - 1)
                )
            )

    async def get_cumulative_players() -> Dict[str, Any]:
        async with pool.acquire() as conn:
            return dict(
                await conn.fetch(
                    """\
                    LỰA CHỌN *
                        TỪ (
                            LỰA CHỌN d, SUM(count) HẾT ( ĐẶT HÀNG THEO d)
                                TỪ (
                                    LỰA CHỌN d, COUNT(user_id)
                                        TỪ (
                                            LỰA CHỌN DISTINCT user_id, MIN(start_time::DATE) d
                                                TỪ game thủ
                                                INNER THAM GIA trò chơi BẬT game_id = game.id
                                                GROUP BY user_id
                                        ) ud
                                        GROUP BY d
                                ) du
                        ) ds
                        TẠI d >= $1;""",
                    today - timedelta(days=days - 1)
                )
            )

    async def get_game_mode_play_cnt() -> List[Record]:
        async with pool.acquire() as conn:
            return await conn.fetch(
                """\
                LỰA CHỌN COUNT(game_mode), game_mode
                    TỪ trò chơi
                    TẠI start_time::DATE >= $1
                    GROUP BY game_mode
                    ORDER BY count;""",
                today - timedelta(days=days - 1)
            )

    # Execute multiple db queries at once for speed
    (
        daily_games,
        active_players,
        active_groups,
        cumulative_groups,
        cumulative_players,
        game_mode_play_cnt
    ) = await asyncio.gather(
        get_daily_games(),
        get_active_players(),
        get_active_groups(),
        get_cumulative_groups(),
        get_cumulative_players(),
        get_game_mode_play_cnt()
    )

    # Handle the possible issue of no games played in a day,
    # so there are no gaps in the cumulative graphs
    # (probably never happens)

    dt = today - timedelta(days=days)
    for i in range(days):
        dt += timedelta(days=1)
        if dt not in cumulative_groups:
            if i == 0:
                async with pool.acquire() as conn:
                    cumulative_groups[dt] = await conn.fetchval(
                        "LỰA CHỌN COUNT(DISTINCT group_id) TỪ trò chơi Ở TẠI start_time::DATE <= $1;", dt
                    )
            else:
                cumulative_groups[dt] = cumulative_groups[dt - timedelta(days=1)]

    dt = today - timedelta(days=days)
    for i in range(days):
        dt += timedelta(days=1)
        if dt not in cumulative_players:
            if i == 0:
                async with pool.acquire() as conn:
                    cumulative_players[dt] = await conn.fetchval(
                        """\
                        LỰA CHỌN COUNT(DISTINCT user_id)
                            TỪ gameplayer
                            INNER THAM GIA trò chơi BẬT game_id = game.id
                            TẠI start_time <= $1;""",
                        dt
                    )
            else:
                cumulative_players[dt] = cumulative_players[dt - timedelta(days=1)]

    while os.path.exists("trends.jpg"):  # Another /trend command has not finished processing
        await asyncio.sleep(0.1)

    # Draw graphs

    plt.figure(figsize=(15, 8))
    plt.subplots_adjust(hspace=0.4)
    plt.suptitle(f"Xu hướng trong quá khứ {days} Ngày", size=25)

    tp = [today - timedelta(days=i) for i in range(days - 1, -1, -1)]
    f = DateFormatter("%b %d" if days < 180 else "%b" if days < 335 else "%b %Y")

    sp = plt.subplot(231)
    sp.xaxis.set_major_formatter(f)
    sp.yaxis.set_major_locator(MaxNLocator(integer=True))  # Force y-axis intervals to be integral
    plt.setp(sp.xaxis.get_majorticklabels(), rotation=45, horizontalalignment="right")
    plt.title("Trò chơi đã chơi", size=18)
    plt.plot(tp, [daily_games.get(i, 0) for i in tp])
    plt.ylim(ymin=0)

    sp = plt.subplot(232)
    sp.xaxis.set_major_formatter(f)
    sp.yaxis.set_major_locator(MaxNLocator(integer=True))
    plt.setp(sp.xaxis.get_majorticklabels(), rotation=45, horizontalalignment="right")
    plt.title("Nhóm hoạt động", size=18)
    plt.plot(tp, [active_groups.get(i, 0) for i in tp])
    plt.ylim(ymin=0)

    sp = plt.subplot(233)
    sp.xaxis.set_major_formatter(f)
    sp.yaxis.set_major_locator(MaxNLocator(integer=True))
    plt.setp(sp.xaxis.get_majorticklabels(), rotation=45, horizontalalignment="right")
    plt.title("Người chơi tích cực", size=18)
    plt.plot(tp, [active_players.get(i, 0) for i in tp])
    plt.ylim(ymin=0)

    plt.subplot(234)
    labels = [i[1] for i in game_mode_play_cnt]
    colors = [
        "dark maroon",
        "dark peach",
        "orange",
        "leather",
        "mustard",
        "teal",
        "french blue",
        "booger",
        "pink"
    ]
    total_games = sum(i[0] for i in game_mode_play_cnt)
    slices, text = plt.pie(
        [i[0] for i in game_mode_play_cnt],
        labels=[
            f"{i[0] / total_games:.1%} ({i[0]})" if i[0] / total_games >= 0.03 else ""
            for i in game_mode_play_cnt
        ],
        colors=["xkcd:" + c for c in colors[len(colors) - len(game_mode_play_cnt):]],
        startangle=90
    )
    plt.legend(slices, labels, title="Chế độ trò chơi đã chơi", fontsize="x-small", loc="best")
    plt.axis("equal")

    sp = plt.subplot(235)
    sp.xaxis.set_major_formatter(f)
    sp.yaxis.set_major_locator(MaxNLocator(integer=True))
    plt.setp(sp.xaxis.get_majorticklabels(), rotation=45, horizontalalignment="right")
    plt.title("Nhóm tích lũy", size=18)
    plt.plot(tp, [cumulative_groups[i] for i in tp])

    sp = plt.subplot(236)
    sp.xaxis.set_major_formatter(f)
    sp.yaxis.set_major_locator(MaxNLocator(integer=True))
    plt.setp(sp.xaxis.get_majorticklabels(), rotation=45, horizontalalignment="right")
    plt.title("Người chơi tích lũy", size=18)
    plt.plot(tp, [cumulative_players[i] for i in tp])

    # Save the plot as a jpg and send it
    plt.savefig("trends.jpg", bbox_inches="tight")
    plt.close("all")
    async with aiofiles.open("trends.jpg", "rb") as f:
        await message.reply_photo(f, caption=f"Thời gian thế hệ: `{time.time() - t:.3f}s`")
    await aiofiles.os.remove("trends.jpg")
