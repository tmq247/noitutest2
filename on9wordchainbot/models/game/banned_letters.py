import random
from datetime import datetime
from string import ascii_lowercase
from typing import List, Optional

from aiogram import types

from .classic import ClassicGame
from ...utils import get_random_word


class BannedLettersGame(ClassicGame):
    name = "trò chơi chữ bị cấm"
    command = "startbl"

    __slots__ = ("banned_letters",)

    def __init__(self, group_id: int) -> None:
        super().__init__(group_id)
        self.banned_letters: List[str] = []

    async def send_turn_message(self) -> None:
        await self.send_message(
            (
                f"Lượt: {self.players_in_game[0].mention} (Next: {self.players_in_game[1].name})\n"
                f"Từ của bạn phải bắt đầu bằng <i>{self.current_word[-1].upper()}</i>, "
                f"<b>exclude</b> <i>{', '.join(c.upper() for c in self.banned_letters)}</i> và "
                f"bao gồm <b>at least {self.min_letters_limit} "
                f"thư{'' if self.min_letters_limit == 1 else 's'}</b>.\n"
                f"Bạn có <b>{self.time_limit}s</b> to answer.\n"
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
            banned_letters=self.banned_letters,
            exclude_words=self.used_words
        )

    async def additional_answer_checkers(self, word: str, message: types.Message) -> bool:
        used_banned_letters = sorted(set(word) & set(self.banned_letters))
        if used_banned_letters:
            await message.reply(
                f"_{word.capitalize()}_ chứa các chữ cái bị cấm "
                f"({', '.join(c.upper() for c in used_banned_letters)}).",
                allow_sending_without_reply=True
            )
            return False
        return True

    def set_banned_letters(self) -> None:
        self.banned_letters.clear()  # Mode may occur multiple times in mixed elimination

        # Set banned letters (maximum one vowel)
        if self.current_word:  # Mixed Elimination
            alphabets = sorted(set(ascii_lowercase) - {self.current_word[-1]})
        else:
            alphabets = list(ascii_lowercase)
        for _ in range(random.randint(2, 4)):
            self.banned_letters.append(random.choice(alphabets))
            if self.banned_letters[-1] in "aeiou":
                alphabets = [c for c in alphabets if c not in "aeiou"]
            else:
                alphabets.remove(self.banned_letters[-1])
        self.banned_letters.sort()

    async def running_initialization(self) -> None:
        self.set_banned_letters()

        # Random starting word
        self.current_word = get_random_word(
            min_len=self.min_letters_limit, banned_letters=self.banned_letters
        )
        self.used_words.add(self.current_word)
        self.start_time = datetime.now().replace(microsecond=0)

        await self.send_message(
            (
                f"từ đầu tiên là <i>{self.current_word.capitalize()}</i>.\n"
                f"Chữ bị cấm: <i>{', '.join(c.upper() for c in self.banned_letters)}</i>\n\n"
                "Lượt khác:\n"
                + "\n".join(p.mention for p in self.players_in_game)
            ),
            parse_mode=types.ParseMode.HTML
        )
