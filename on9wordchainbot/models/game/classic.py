import asyncio
import random
from datetime import datetime
from typing import Any, List, Optional, Set

from aiocache import cached
from aiogram import types
from aiogram.utils.exceptions import BadRequest

from ..player import Player
from ... import GlobalState, bot, on9bot, pool
from ...constants import GameSettings, GameState, OWNER_ID
from ...utils import ADD_ON9BOT_TO_GROUP_KEYBOARD, check_word_existence, get_random_word, send_admin_group


class ClassicGame:
    name = "classic game"
    command = "startclassic"

    __slots__ = (
        "group_id", "players", "players_in_game", "state", "start_time", "end_time",
        "extended_user_ids", "min_players", "max_players", "time_left", "time_limit",
        "min_letters_limit", "current_word", "longest_word", "longest_word_sender_id",
        "answered", "accepting_answers", "turns", "used_words", "join_lock"
    )

    def __init__(self, group_id: int) -> None:
        self.group_id = group_id
        self.players: List[Player] = []
        self.players_in_game: List[Player] = []
        self.state = GameState.JOINING
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        # Store user ids rather than Player object since players may quit then join to extend again
        self.extended_user_ids: Set[int] = set()

        # Game settings
        self.min_players = GameSettings.MIN_PLAYERS
        self.max_players = GameSettings.MAX_PLAYERS
        self.time_left = GameSettings.JOINING_PHASE_SECONDS
        self.time_limit = GameSettings.MAX_TURN_SECONDS
        self.min_letters_limit = GameSettings.MIN_WORD_LENGTH_LIMIT

        # Game attributes
        self.current_word: Optional[str] = None
        self.longest_word = ""
        self.longest_word_sender_id: Optional[int] = None  # TODO: Change to Player object instead of id
        self.answered = False
        self.accepting_answers = False
        self.turns = 0
        self.used_words: Set[str] = set()

        self.join_lock = asyncio.Lock()  # Prevent same user / vp joining as multiple players

    def user_in_game(self, user_id: int) -> bool:
        return any(p.user_id == user_id for p in self.players)

    async def send_message(self, *args: Any, **kwargs: Any) -> types.Message:
        return await bot.send_message(
            self.group_id, *args, disable_web_page_preview=True,
            allow_sending_without_reply=True, **kwargs
        )

    @cached(ttl=15)
    async def is_admin(self, user_id: int) -> bool:
        user = await bot.get_chat_member(self.group_id, user_id)
        return user.is_chat_admin()

    async def join(self, message: types.Message) -> None:
        async with self.join_lock:
            if self.state != GameState.JOINING or len(self.players) >= self.max_players:
                return

            # Try to detect game not starting
            if self.time_left < 0:
                asyncio.create_task(self.scan_for_stale_timer())
                return

            # Check if user already joined
            user = message.from_user
            if self.user_in_game(user.id):
                return

            player = await Player.create(user)
            self.players.append(player)

            await self.send_message(
                f"{player.name} joined. There {'is' if len(self.players) == 1 else 'are'} now "
                f"{len(self.players)} player{'' if len(self.players) == 1 else 's'}.",
                parse_mode=types.ParseMode.HTML
            )

            # Start game when max players reached
            if len(self.players) >= self.max_players:
                self.time_left = -99999

    async def forcejoin(self, message: types.Message) -> None:
        async with self.join_lock:
            if self.state == GameState.KILLGAME or len(self.players) >= self.max_players:
                return

            if message.reply_to_message:
                user = message.reply_to_message.from_user
            else:
                user = message.from_user

            # Check if user already joined
            if self.user_in_game(user.id):
                return

            player = await Player.create(user)
            self.players.append(player)
            if self.state == GameState.RUNNING:
                self.players_in_game.append(player)

            await self.send_message(
                f"{player.name} was forced to join. There {'is' if len(self.players) == 1 else 'are'} now "
                f"{len(self.players)} player{'' if len(self.players) == 1 else 's'}.",
                parse_mode=types.ParseMode.HTML
            )

            # Start game when max players reached
            if len(self.players) >= self.max_players:
                self.time_left = -99999

    async def flee(self, message: types.Message) -> None:
        async with self.join_lock:
            if self.state != GameState.JOINING:
                return

            # Find player to remove
            user_id = message.from_user.id
            for i in range(len(self.players)):
                if self.players[i].user_id == user_id:
                    player = self.players.pop(i)
                    break
            else:
                return

            await self.send_message(
                f"{player.name} fled. There {'is' if len(self.players) == 1 else 'are'} now "
                f"{len(self.players)} player{'' if len(self.players) == 1 else 's'}.",
                parse_mode=types.ParseMode.HTML
            )

    async def forceflee(self, message: types.Message) -> None:
        async with self.join_lock:
            # Player to be fled = Sender of replies message
            if self.state != GameState.JOINING or not message.reply_to_message:
                return

            # Find player to remove
            user_id = message.reply_to_message.from_user.id
            for i in range(len(self.players)):
                if self.players[i].user_id == user_id:
                    player = self.players.pop(i)
                    break
            else:
                return

            await self.send_message(
                f"{player.name} buộc phải chạy trốn. Ở đó {'is' if len(self.players) == 1 else 'are'} ngay "
                f"{len(self.players)} người chơi {'' if len(self.players) == 1 else 's'}.",
                parse_mode=types.ParseMode.HTML
            )

    async def addvp(self, message: types.Message) -> None:
        async with self.join_lock:
            if self.state != GameState.JOINING or len(self.players) >= self.max_players:
                return

            # Check if On9Bot already joined
            if any(p.is_vp for p in self.players):
                return

            # Check if vp adder is player/admin/owner
            if (
                message.from_user.id != OWNER_ID
                and not self.user_in_game(message.from_user.id)
                and not await self.is_admin(message.from_user.id)
            ):
                await self.send_message("Tưởng tượng không chơi")
                return

            try:
                vp = await bot.get_chat_member(self.group_id, on9bot.id)
                # VP must be chat member
                assert vp.is_chat_member() or vp.is_chat_admin()
            except (BadRequest, AssertionError):
                await self.send_message(
                    f"Thêm vào [On9Bot](tg://user?id={on9bot.id}) ở đây để chơi như một người chơi ảo.",
                    reply_markup=ADD_ON9BOT_TO_GROUP_KEYBOARD
                )
                return

            vp = await Player.vp()
            self.players.append(vp)

            await on9bot.send_message(self.group_id, "/join@" + (await bot.me).username)
            await self.send_message(
                (
                    f"{vp.name} tham gia. Ở đó {'is' if len(self.players) == 1 else 'are'} ngay "
                    f"{len(self.players)} người chơi{'' if len(self.players) == 1 else 's'}."
                ),
                parse_mode=types.ParseMode.HTML
            )

            # Start game when max players reached
            if len(self.players) >= self.max_players:
                self.time_left = -99999

    async def remvp(self, message: types.Message) -> None:
        async with self.join_lock:
            if self.state != GameState.JOINING:
                return

            # Check if On9Bot has joined
            if not any(p.is_vp for p in self.players):
                return

            # Check if vp remover is player/admin
            if (
                message.from_user.id != OWNER_ID
                and not self.user_in_game(message.from_user.id)
                and not await self.is_admin(message.from_user.id)
            ):
                await self.send_message("giả lập không chơi")
                return

            for i in range(len(self.players)):
                if self.players[i].is_vp:
                    vp = self.players.pop(i)
                    break
            else:
                return

            await on9bot.send_message(self.group_id, "/flee@" + (await bot.me).username)
            await self.send_message(
                (
                    f"{vp.name} bỏ trốn. Ở đó {'is' if len(self.players) == 1 else 'are'} ngay "
                    f"{len(self.players)} người chơi{'' if len(self.players) == 1 else 's'}."
                ),
                parse_mode=types.ParseMode.HTML
            )

    async def extend(self, message: types.Message) -> None:
        if self.state != GameState.JOINING:
            return

        # Check if extender is player/admin/owner
        if (
            message.from_user.id != OWNER_ID
            and not self.user_in_game(message.from_user.id)
            and not await self.is_admin(message.from_user.id)
        ):
            await self.send_message("Giả lập không chơi")
            return

        # Each player can only extend once and only for 30 seconds except admins
        if await self.is_admin(message.from_user.id):
            arg = message.text.partition(" ")[2]

            # Check if arg is a valid negative integer
            try:
                n = int(arg)
                is_neg = n < 0
                n = abs(n)
            except ValueError:
                n = 30
                is_neg = False
        elif message.from_user.id in self.extended_user_ids:
            await self.send_message("Bạn chỉ có thể gia hạn một lần")
            return
        else:
            self.extended_user_ids.add(message.from_user.id)
            n = 30
            is_neg = False

        if is_neg:
            # Reduce joining phase time (admins only)
            if not await self.is_admin(message.from_user.id):
                await self.send_message("Hãy tưởng tượng không phải là quản trị viên")
                return

            if n >= self.time_left:
                # Start game immediately
                self.time_left = -99999
            else:
                self.time_left -= n
                await self.send_message(
                    f"Giai đoạn tham gia đã được giảm bởi {n}s.\n"
                    f"Bạn có {self.time_left}s để /join."
                )
        else:
            # Extend joining phase time
            # Max joining phase duration is capped
            added_duration = min(n, GameSettings.MAX_JOINING_PHASE_SECONDS - self.time_left)
            self.time_left += added_duration
            await self.send_message(
                f"Giai đoạn gia nhập đã được mở rộng bởi {added_duration}s.\n"
                f"Bạn có {self.time_left}s để /join."
            )

    async def send_turn_message(self) -> None:
        await self.send_message(
            (
                f"Lượt: {self.players_in_game[0].mention} (Next: {self.players_in_game[1].name})\n"
                f"Từ của bạn phải bắt đầu bằng <i>{self.current_word[-1].upper()}</i> và "
                f"bao gồm <b>at least {self.min_letters_limit} letters</b>.\n"
                f"Bạn có <b>{self.time_limit}s</b> để trả lời.\n"
                f"Người chơi còn lại: {len(self.players_in_game)}/{len(self.players)}\n"
                f"Tổng số từ: {self.turns}"
            ),
            parse_mode=types.ParseMode.HTML
        )

        # Reset per-turn attributes
        self.answered = False
        self.accepting_answers = True
        self.time_left = self.time_limit

        if self.players_in_game[0].is_vp:
            await self.vp_answer()

    def get_random_valid_answer(self) -> Optional[str]:
        return get_random_word(
            min_len=self.min_letters_limit,
            prefix=self.current_word[-1],
            exclude_words=self.used_words
        )

    async def vp_answer(self) -> None:
        # Wait before answering to prevent exceeding 20 msg/min message limit
        # Also simulate thinking/input time like human players, wowzers
        await asyncio.sleep(random.uniform(5, 8))

        word = self.get_random_valid_answer()

        if not word:  # No valid words to choose from
            await on9bot.send_message(self.group_id, "/forceskip bey")
            self.time_left = 0
            return

        await on9bot.send_message(self.group_id, word.capitalize())

        self.post_turn_processing(word)
        await self.send_post_turn_message(word)

    async def additional_answer_checkers(self, word: str, message: types.Message) -> bool:
        # To be overridden by other game modes
        # True/False: valid/invalid answer
        return True

    async def handle_answer(self, message: types.Message) -> None:
        # Prevent circular imports
        from .elimination import EliminationGame

        word = message.text.lower()

        # Check if answer is invalid
        if not word.startswith(self.current_word[-1]):
            await message.reply(
                f"_{word.capitalize()}_ không bắt đầu với _{self.current_word[-1].upper()}_.",
                allow_sending_without_reply=True
            )
            return
        # No minimum letters limit for elimination game modes
        if not isinstance(self, EliminationGame) and len(word) < self.min_letters_limit:
            await message.reply(
                f"_{word.capitalize()}_ có ít hơn {self.min_letters_limit} letters.",
                allow_sending_without_reply=True
            )
            return
        if word in self.used_words:
            await message.reply(f"_{word.capitalize()}_ đã được dùng.", allow_sending_without_reply=True)
            return
        if not check_word_existence(word):
            await message.reply(
                f"_{word.capitalize()}_ không có trong danh sách các từ của tôi.",
                allow_sending_without_reply=True
            )
            return
        if not await self.additional_answer_checkers(word, message):
            return

        self.post_turn_processing(word)
        await self.send_post_turn_message(word)

    def post_turn_processing(self, word: str) -> None:
        # Prevent circular imports
        from .chosen_first_letter import ChosenFirstLetterGame

        # Update attributes
        self.used_words.add(word)
        self.turns += 1

        # self.current_word is constant for ChosenFirstLetterGame
        if not isinstance(self, ChosenFirstLetterGame):
            self.current_word = word

        self.players_in_game[0].word_count += 1
        self.players_in_game[0].letter_count += len(word)
        # If both words have the same length, it will (probably) default to the first argument
        self.players_in_game[0].longest_word = max(word, self.players_in_game[0].longest_word, key=len)

        if len(word) > len(self.longest_word):
            self.longest_word = word
            self.longest_word_sender_id = self.players_in_game[0].user_id

        # Set per-turn attributes
        self.answered = True
        self.accepting_answers = False

    async def send_post_turn_message(self, word: str) -> None:
        text = f"_{word.capitalize()}_ được chấp nhận.\n\n"
        # Reduce limits if possible every set number of turns
        if self.turns % GameSettings.TURNS_BETWEEN_LIMITS_CHANGE == 0:
            if self.time_limit > GameSettings.MIN_TURN_SECONDS:
                self.time_limit -= GameSettings.TURN_SECONDS_REDUCTION_PER_LIMIT_CHANGE
                text += (
                    f"Giới hạn thời gian giảm từ "
                    f"*{self.time_limit + GameSettings.TURN_SECONDS_REDUCTION_PER_LIMIT_CHANGE}s* "
                    f"ĐẾN *{self.time_limit}s*.\n"
                )
            if self.min_letters_limit < GameSettings.MAX_WORD_LENGTH_LIMIT:
                self.min_letters_limit += GameSettings.WORD_LENGTH_LIMIT_INCREASE_PER_LIMIT_CHANGE
                text += (
                    f"Các chữ cái tối thiểu trên mỗi từ tăng từ "
                    f"*{self.min_letters_limit - GameSettings.WORD_LENGTH_LIMIT_INCREASE_PER_LIMIT_CHANGE}* "
                    f"ĐẾN *{self.min_letters_limit}*.\n"
                )
        await self.send_message(text)

    async def running_initialization(self) -> None:
        # Random starting word
        self.current_word = get_random_word(min_len=self.min_letters_limit)
        self.used_words.add(self.current_word)
        self.start_time = datetime.now().replace(microsecond=0)

        await self.send_message(
            (
                f"Từ đầu tiên là <i>{self.current_word.capitalize()}</i>.\n\n"
                "Lượt khác:\n"
                + "\n".join(p.mention for p in self.players_in_game)
            ),
            parse_mode=types.ParseMode.HTML
        )

    async def running_phase_tick(self) -> bool:
        # Return values
        # True: Game has ended
        # False: Game is still ongoing
        if self.answered:
            # Move player who just answered to the end of queue
            self.players_in_game.append(self.players_in_game.pop(0))
        else:
            self.time_left -= 1
            if self.time_left > 0:
                return False

            # Timer ran out
            self.accepting_answers = False
            await self.send_message(
                f"{self.players_in_game[0].mention} đã hết thời gian! Họ đã bị loại.",
                parse_mode=types.ParseMode.HTML
            )
            del self.players_in_game[0]

            if len(self.players_in_game) == 1:
                await self.handle_game_end()
                return True

        await self.send_turn_message()
        return False

    async def handle_game_end(self) -> None:
        # Calculate game length
        self.end_time = datetime.now().replace(microsecond=0)
        td = self.end_time - self.start_time
        game_len_str = f"{int(td.total_seconds()) // 3600:02}{str(td)[-6:]}"

        winner = self.players_in_game[0].mention if self.players_in_game else "No one"
        text = f"{winner} đã thắng trò chơi {len(self.players)} người chơi!\n"
        text += f"Tổng số từ: {self.turns}\n"
        if self.longest_word:
            longest_word_sender_name = [p for p in self.players if p.user_id == self.longest_word_sender_id][0].name
            text += f"Từ dài nhất: <i>{self.longest_word.capitalize()}</i> từ {longest_word_sender_name}\n"
        text += f"Thời lượng trò chơi: <code>{game_len_str}</code>"
        await self.send_message(text, parse_mode=types.ParseMode.HTML)

        GlobalState.games.pop(self.group_id, None)

    async def update_db(self) -> None:
        async with pool.acquire() as conn:
            # Insert game instance
            await conn.execute(
                """\
                CHÈN VÀO trò chơi (group_id, players, game_mode, winner, start_time, end_time)
                    VALUES ($1, $2, $3, $4, $5, $6);""",
                self.group_id,
                len(self.players),
                self.__class__.__name__,
                self.players_in_game[0].user_id if self.players_in_game else None,
                self.start_time,
                self.end_time
            )
            # Get game id
            game_id = await conn.fetchval(
                "CHỌN id TỪ trò chơi Ở TẠI group_id = $1 AND start_time = $2;",
                self.group_id,
                self.start_time
            )
        for player in self.players:  # Update db players in parallel
            asyncio.create_task(self.update_db_player(game_id, player))

    async def update_db_player(self, game_id: int, player: Player) -> None:
        async with pool.acquire() as conn:
            player_exists = bool(await conn.fetchval("CHỌN id TỪ người chơi Ở TẠI user_id = $1;", player.user_id))
            if player_exists:  # Update player in db
                await conn.execute(
                    """\
                   CẬP NHẬT người chơi
                    SET game_count = game_count + 1,
                        win_count = win_count + $1,
                        word_count = word_count + $2,
                        letter_count = letter_count + $3,
                        longest_word = CASE WHEN longest_word IS NULL THEN $4::TEXT
                                            WHEN $4::TEXT IS NULL THEN longest_word
                                            WHEN LENGTH($4::TEXT) > LENGTH(longest_word) THEN $4::TEXT
                                            ELSE longest_word
                                       END
                    WHERE user_id = $5;""",
                    int(player in self.players_in_game),  # Support no winner in some game modes
                    player.word_count,
                    player.letter_count,
                    player.longest_word or None,
                    player.user_id
                )
            else:  # New player, create player in db
                await conn.execute(
                    """\
                    CHÈN VÀO trình phát (user_id, game_count, win_count, word_count, letter_count, longest_word)
                        VALUES ($1, 1, $2, $3, $4, $5::TEXT);""",
                    player.user_id,
                    int(player in self.players_in_game),  # No winner in some game modes
                    player.word_count,
                    player.letter_count,
                    player.longest_word or None
                )

            # Create gameplayer in db
            await conn.execute(
                """\
                CHÈN VÀO người chơi (user_id, group_id, game_id, won, word_count, letter_count, longest_word)
                    VALUES ($1, $2, $3, $4, $5, $6, $7);""",
                player.user_id,
                self.group_id,
                game_id,
                player in self.players_in_game,
                player.word_count,
                player.letter_count,
                player.longest_word or None
            )

    async def scan_for_stale_timer(self) -> None:
        # Check if game timer is stuck
        timer = self.time_left
        for _ in range(5):
            await asyncio.sleep(1)
            if timer != self.time_left and timer >= 0:
                return  # Timer not stuck
            if self.state == GameState.KILLGAME or self.group_id not in GlobalState.games:
                return  # Game already killed

        await send_admin_group(f"Đã phát hiện bộ đếm thời gian cũ/âm tính kéo dài trong nhóm `{self.group_id}`. Game terminated.")
        try:
            await self.send_message("Hẹn giờ trò chơi bị trục trặc. Trò chơi đã kết thúc.")
        except:
            pass

        GlobalState.games.pop(self.group_id, None)

    async def main_loop(self, message: types.Message) -> None:
        # Attempt to fix issue of stuck game with negative timer.
        negative_timer = 0
        try:
            await self.send_message(
                f"A{'n' if self.name[0] in 'aeiou' else ''} {self.name} đang bắt đầu.\n"
                f"{self.min_players}-{self.max_players} thời gian người chơi còn.\n"
                f"{self.time_left}s để /join."
            )
            await self.join(message)

            while True:
                await asyncio.sleep(1)
                if self.state == GameState.JOINING:
                    if self.time_left > 0:
                        self.time_left -= 1
                        if self.time_left in (15, 30, 60):
                            await self.send_message(f"{self.time_left}s left to /join.")
                    elif len(self.players) < self.min_players:
                        await self.send_message("Không đủ người chơi. Trò chơi đã kết thúc.")
                        del GlobalState.games[self.group_id]
                        return
                    else:
                        self.state = GameState.RUNNING
                        await self.send_message("Trò chơi đang bắt đầu...")

                        random.shuffle(self.players)
                        self.players_in_game = self.players[:]

                        await self.running_initialization()
                        await self.send_turn_message()
                elif self.state == GameState.RUNNING:
                    # Check for prolonged negative timer
                    if self.time_left < 0:
                        negative_timer += 1
                    if negative_timer >= 5:
                        raise ValueError("Hẹn giờ âm kéo dài.")

                    if await self.running_phase_tick():  # True: Game ended
                        await self.update_db()
                        return
                elif self.state == GameState.KILLGAME:
                    await self.send_message("Trò chơi kết thúc bất ngờ.")
                    GlobalState.games.pop(self.group_id, None)
                    return
        except Exception as e:
            GlobalState.games.pop(self.group_id, None)
            try:
                await self.send_message(
                    f"Trò chơi đã kết thúc do lỗi sau:\n`{e.__class__.__name__}: {e}`.\n"
                    "Chủ sở hữu của tôi sẽ được thông báo."
                )
            except:
                pass
            raise
