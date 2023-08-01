import random
from datetime import datetime
from string import ascii_lowercase

from aiogram import types

from .classic import ClassicGame


class ChosenFirstLetterGame(ClassicGame):
    name = "Trò chơi chữ cái đầu tiên được chọn"
    command = "startcfl"

    async def running_initialization(self) -> None:
        # Instead of storing the last used word like in other game modes,
        # self.current_word stores in the chosen first letter which is constant throughout the game
        self.current_word = random.choice(ascii_lowercase)
        self.start_time = datetime.now().replace(microsecond=0)

        await self.send_message(
            (
                f"Chữ cái đầu tiên được chọn là <i>{self.current_word.upper()}</i>.\n\n"
                "LƯỢt khác:\n"
                + "\n".join(p.mention for p in self.players_in_game)
            ),
            parse_mode=types.ParseMode.HTML
        )
